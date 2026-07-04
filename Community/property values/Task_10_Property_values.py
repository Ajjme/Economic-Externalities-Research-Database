"""Build annual ACS property value extracts for all U.S. counties and tracts.

This pipeline downloads ACS 5-year estimates for the most recent stable years,
normalizes FIPS identifiers, computes owner-occupancy rates, and exports one
historical CSV for downstream Cadence Property Values ingestion.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "cadence_property_values_acs5.csv"

ACS_BASE_URL = "https://api.census.gov/data"
ACS_DATASET = "acs/acs5"
ACS_VARIABLES = {
	"median_home_value": "B25077_001E",
	"total_housing_units": "B25001_001E",
	"owner_occupied_units": "B25003_002E",
}


class NonRetryableAPIError(RuntimeError):
	"""Error type for requests that should not be retried."""


@dataclass(frozen=True)
class GeographyConfig:
	"""Request configuration for a Census geography level."""

	name: str
	for_clause: str
	in_clauses: tuple[str, ...]


GEOGRAPHIES: tuple[GeographyConfig, ...] = (
	GeographyConfig(name="county", for_clause="county:*", in_clauses=("state:*",)),
	GeographyConfig(
		name="tract",
		for_clause="tract:*",
		in_clauses=("state:*",),
	),
)


class CadencePropertyValuesPipeline:
	"""ETL pipeline for annual ACS property values at county and tract levels."""

	def __init__(
		self,
		output_path: Path = DEFAULT_OUTPUT_PATH,
		census_api_key: str | None = None,
		request_timeout: int = 60,
		max_retries: int = 5,
		backoff_seconds: float = 1.5,
	) -> None:
		self.output_path = output_path
		self.census_api_key = census_api_key
		self.request_timeout = request_timeout
		self.max_retries = max_retries
		self.backoff_seconds = backoff_seconds
		self.session = requests.Session()
		self.logger = logging.getLogger(self.__class__.__name__)

	def _request_json_with_retry(self, url: str, params: list[tuple[str, str]]) -> list[list[str]]:
		"""Call Census API with retries for rate limiting and transient failures."""

		for attempt in range(1, self.max_retries + 1):
			try:
				response = self.session.get(
					url,
					params=params,
					timeout=self.request_timeout,
					allow_redirects=False,
				)

				if (
					response.status_code in {301, 302, 307, 308}
					and "missing_key" in response.headers.get("Location", "")
				):
					raise NonRetryableAPIError(
						"Census API key is required. Set CENSUS_API_KEY in environment "
						"or pass --census-api-key."
					)
				if (
					response.status_code in {301, 302, 307, 308}
					and "invalid_key" in response.headers.get("Location", "")
				):
					raise NonRetryableAPIError(
						"Census API key is invalid. Replace CENSUS_API_KEY with a valid key "
						"or pass --census-api-key."
					)

				if response.status_code == 429 or 500 <= response.status_code < 600:
					raise requests.HTTPError(
						f"Retryable HTTP status {response.status_code}", response=response
					)

				response.raise_for_status()

				payload = response.json()
				if isinstance(payload, dict) and payload.get("error"):
					raise RuntimeError(f"Census API error: {payload['error']}")
				if not isinstance(payload, list):
					raise RuntimeError("Unexpected Census API response format.")
				return payload

			except NonRetryableAPIError:
				raise
			except (requests.RequestException, ValueError, RuntimeError) as exc:
				is_last = attempt == self.max_retries
				if is_last:
					self.logger.error("Request failed after %s attempts: %s", attempt, exc)
					raise

				sleep_seconds = self.backoff_seconds * (2 ** (attempt - 1))
				self.logger.warning(
					"Request attempt %s/%s failed (%s). Retrying in %.1fs.",
					attempt,
					self.max_retries,
					exc,
					sleep_seconds,
				)
				time.sleep(sleep_seconds)

		raise RuntimeError("Unreachable retry block.")

	def _is_year_available(self, year: int) -> bool:
		"""Check if ACS 5-year endpoint for a year is available and stable."""

		url = f"{ACS_BASE_URL}/{year}/{ACS_DATASET}"
		params = [("get", "NAME"), ("for", "us:1")]
		if self.census_api_key:
			params.append(("key", self.census_api_key))

		try:
			payload = self._request_json_with_retry(url=url, params=params)
			return len(payload) >= 2
		except NonRetryableAPIError:
			raise
		except Exception:
			return False

	def discover_available_years(self, target_year: int | None = None, years_back: int = 5) -> list[int]:
		"""Discover latest stable ACS 5-year releases and return last N years."""

		if years_back < 1:
			raise ValueError("years_back must be at least 1")

		stable_max_year = datetime.now(timezone.utc).year - 1
		if target_year is not None:
			stable_max_year = min(stable_max_year, target_year)

		available_years: list[int] = []
		for year in range(stable_max_year, 2008, -1):
			if self._is_year_available(year):
				available_years.append(year)
			if len(available_years) >= years_back:
				break

		if len(available_years) < years_back:
			raise RuntimeError(
				"Could not resolve enough ACS years. "
				f"Requested {years_back}, found {len(available_years)}."
			)

		return sorted(available_years)

	def fetch_data(self, year: int, geography: GeographyConfig) -> pd.DataFrame:
		"""Fetch one ACS year for one geography level."""

		url = f"{ACS_BASE_URL}/{year}/{ACS_DATASET}"
		variable_list = ["NAME", *ACS_VARIABLES.values()]

		params: list[tuple[str, str]] = [
			("get", ",".join(variable_list)),
			("for", geography.for_clause),
		]
		params.extend(("in", clause) for clause in geography.in_clauses)
		if self.census_api_key:
			params.append(("key", self.census_api_key))

		payload = self._request_json_with_retry(url=url, params=params)
		if len(payload) <= 1:
			self.logger.warning("No rows returned for %s %s.", year, geography.name)
			return pd.DataFrame()

		header, rows = payload[0], payload[1:]
		df = pd.DataFrame(rows, columns=header)
		df["year"] = year
		df["geography_level"] = geography.name
		return df

	@staticmethod
	def _clean_numeric(series: pd.Series) -> pd.Series:
		"""Convert ACS value strings to numeric while treating Census sentinels as NA."""

		cleaned = series.replace({"-666666666": pd.NA, "-222222222": pd.NA, "N": pd.NA})
		return pd.to_numeric(cleaned, errors="coerce")

	def transform_and_normalize(self, df: pd.DataFrame) -> pd.DataFrame:
		"""Normalize FIPS fields and derive analytical columns."""

		if df.empty:
			return df

		renamed = df.rename(columns={v: k for k, v in ACS_VARIABLES.items()}).copy()

		for value_col in ACS_VARIABLES:
			renamed[value_col] = self._clean_numeric(renamed[value_col])

		if "county" not in renamed.columns:
			renamed["county"] = ""
		if "tract" not in renamed.columns:
			renamed["tract"] = ""

		renamed["state"] = renamed["state"].fillna("").astype(str).str.zfill(2)
		renamed["county"] = (
			renamed["county"].fillna("").astype(str).str.strip().replace("", pd.NA).str.zfill(3)
		)
		renamed["tract"] = (
			renamed["tract"].fillna("").astype(str).str.strip().replace("", pd.NA).str.zfill(6)
		)

		renamed["state_fips"] = renamed["state"]
		renamed["county_fips"] = renamed["state"] + renamed["county"]
		renamed["tract_fips"] = renamed["state"] + renamed["county"] + renamed["tract"]

		renamed["fips"] = renamed["county_fips"].where(
			renamed["geography_level"] == "county", renamed["tract_fips"]
		)

		renamed["owner_occupancy_rate"] = (
			renamed["owner_occupied_units"] / renamed["total_housing_units"]
		)
		renamed.loc[
			(renamed["total_housing_units"].isna()) | (renamed["total_housing_units"] <= 0),
			"owner_occupancy_rate",
		] = pd.NA

		renamed = renamed.rename(columns={"NAME": "area_name"})

		output_columns = [
			"year",
			"geography_level",
			"fips",
			"state_fips",
			"county_fips",
			"tract_fips",
			"state",
			"county",
			"tract",
			"area_name",
			"median_home_value",
			"total_housing_units",
			"owner_occupied_units",
			"owner_occupancy_rate",
		]

		return renamed[output_columns]

	def fetch_fhfa_supplemental_stub(self, year: int) -> pd.DataFrame:
		"""Placeholder for optional FHFA-derived assessed/lot/distribution fields.

		TODO:
		- Pull FHFA or other approved supplemental sources for:
		  * median assessed value
		  * property value distribution bands
		  * median lot value
		- Normalize keys to county/tract FIPS and join to ACS output.
		"""

		self.logger.info("FHFA supplemental merge is not implemented for year %s (TODO).", year)
		return pd.DataFrame(columns=["year", "fips"])

	def merge_supplemental_data(self, base_df: pd.DataFrame) -> pd.DataFrame:
		"""Stub merge point for FHFA supplemental fields keyed by year + FIPS."""

		years = sorted(base_df["year"].dropna().astype(int).unique().tolist())
		supplemental_frames = [self.fetch_fhfa_supplemental_stub(year) for year in years]
		supplemental = pd.concat(supplemental_frames, ignore_index=True)

		if supplemental.empty or set(["year", "fips"]).difference(supplemental.columns):
			return base_df

		merged = base_df.merge(supplemental, how="left", on=["year", "fips"])
		return merged

	def run(self, target_year: int | None = None, years_back: int = 5) -> pd.DataFrame:
		"""Execute full extraction and normalization for county + tract geographies."""

		years = self.discover_available_years(target_year=target_year, years_back=years_back)
		self.logger.info("Resolved ACS years: %s", years)

		frames: list[pd.DataFrame] = []

		for year in years:
			for geography in GEOGRAPHIES:
				self.logger.info("Fetching ACS %s data for %s geography.", year, geography.name)
				try:
					raw = self.fetch_data(year=year, geography=geography)
				except Exception as exc:
					if geography.name == "tract":
						self.logger.warning(
							"Skipping tract data for %s due to fetch error: %s", year, exc
						)
						continue
					raise

				normalized = self.transform_and_normalize(raw)
				if normalized.empty:
					self.logger.warning(
						"No normalized rows for %s (%s).", year, geography.name
					)
					continue
				frames.append(normalized)

		if not frames:
			raise RuntimeError("Pipeline produced no data.")

		combined = pd.concat(frames, ignore_index=True)
		combined = self.merge_supplemental_data(combined)
		combined = combined.sort_values(["fips", "year", "geography_level"]).reset_index(drop=True)
		return combined

	def export_to_csv(self, df: pd.DataFrame) -> Path:
		"""Write final dataset to disk, ensuring parent directories exist."""

		self.output_path.parent.mkdir(parents=True, exist_ok=True)
		df.to_csv(self.output_path, index=False)
		self.logger.info("Exported %s rows to %s", len(df), self.output_path)
		return self.output_path


def build_parser() -> argparse.ArgumentParser:
	"""Create CLI parser for annual update execution."""

	parser = argparse.ArgumentParser(
		description="Download and normalize ACS county/tract property values for Cadence."
	)
	parser.add_argument(
		"--target-year",
		type=int,
		default=None,
		help="Optional max ACS year to include (e.g., 2024).",
	)
	parser.add_argument(
		"--years-back",
		type=int,
		default=5,
		help="Number of historical ACS years to pull (default: 5).",
	)
	parser.add_argument(
		"--output-file",
		type=Path,
		default=DEFAULT_OUTPUT_PATH,
		help="Output CSV path.",
	)
	parser.add_argument(
		"--census-api-key",
		default=None,
		help="Census API key (can also be set via CENSUS_API_KEY env var).",
	)
	parser.add_argument(
		"--log-level",
		default="INFO",
		choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
		help="Logging level (default: INFO).",
	)
	return parser


def main() -> int:
	"""CLI entrypoint."""

	load_dotenv()
	parser = build_parser()
	args = parser.parse_args()

	logging.basicConfig(
		level=getattr(logging, args.log_level),
		format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
	)

	census_api_key = args.census_api_key or os.getenv("CENSUS_API_KEY")
	pipeline = CadencePropertyValuesPipeline(
		output_path=args.output_file,
		census_api_key=census_api_key,
	)

	try:
		final_df = pipeline.run(target_year=args.target_year, years_back=args.years_back)
		pipeline.export_to_csv(final_df)
		return 0
	except Exception as exc:
		logging.getLogger("main").exception("Cadence property values pipeline failed: %s", exc)
		return 1


if __name__ == "__main__":
	raise SystemExit(main())
