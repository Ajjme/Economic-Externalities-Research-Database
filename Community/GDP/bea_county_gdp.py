"""BEA county GDP pipeline for CADENCE.

This module discovers BEA line codes at runtime, fetches county-level GDP and
population data, and writes a normalized county-year CSV for downstream use.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv


BASE_URL = "https://apps.bea.gov/api/data"
DATASET_NAME = "Regional"
TABLES = ("CAGDP1", "CAGDP2", "CAINC1")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
REFERENCE_DIR = SCRIPT_DIR / "reference"
SCHEMA_PATH = REFERENCE_DIR / "bea_line_codes.json"
OUTPUT_CSV = REFERENCE_DIR / "county_gdp.csv"
QUALITY_NOTES_PATH = REFERENCE_DIR / "county_gdp_data_quality_notes.md"

SERVICE_SUPERSECTORS = {
	"wholesale trade",
	"retail trade",
	"transportation and warehousing",
	"information",
	"finance and insurance",
	"real estate and rental and leasing",
	"professional scientific and technical services",
	"management of companies and enterprises",
	"administrative and support and waste management and remediation services",
	"educational services",
	"health care and social assistance",
	"arts entertainment and recreation",
	"accommodation and food services",
	"other services except government and government enterprises",
	"other services except government",
}


def _normalize_desc(text: str) -> str:
	clean = text.lower().strip()
	clean = re.sub(r"[^a-z0-9 ]+", " ", clean)
	return re.sub(r"\s+", " ", clean).strip()


def normalize_years_selector(years: str) -> str:
	"""Normalize year selector to values accepted by BEA Year parameter.

	BEA supports ALL, LAST5, LAST10, or comma-separated explicit years.
	This helper also supports user-friendly LASTN (e.g., LAST15) by expanding
	to an explicit comma-separated year list.
	"""
	value = str(years).strip().upper()
	if value in {"ALL", "LAST5", "LAST10"}:
		return value

	match = re.fullmatch(r"LAST(\d+)", value)
	if match:
		count = int(match.group(1))
		if count <= 0:
			raise ValueError("--years LASTN must have N >= 1")
		end_year = datetime.now(timezone.utc).year
		start_year = end_year - count + 1
		expanded = ",".join(str(y) for y in range(start_year, end_year + 1))
		logging.info("Expanded years selector %s to explicit list: %s", value, expanded)
		return expanded

	if re.fullmatch(r"\d{4}(\s*,\s*\d{4})*", value):
		return ",".join(part.strip() for part in value.split(","))

	raise ValueError(
		"Invalid --years value. Use ALL, LAST5, LAST10, LASTN (e.g., LAST15), "
		"or a comma-separated year list like 2015,2016,2017."
	)


@dataclass
class PipelineConfig:
	years: str
	refresh_schema: bool


class BEAClient:
	"""Single-threaded BEA API client with pacing and retry/backoff logic."""

	def __init__(self, api_key: str, request_delay_seconds: float = 0.7) -> None:
		self.api_key = api_key
		self.request_delay_seconds = request_delay_seconds
		self.session = requests.Session()
		self.last_request_time = 0.0
		self.bytes_window: deque[tuple[float, int]] = deque()
		self.error_window: deque[float] = deque()

	def _prune_windows(self) -> None:
		now = time.time()
		cutoff = now - 60
		while self.bytes_window and self.bytes_window[0][0] < cutoff:
			self.bytes_window.popleft()
		while self.error_window and self.error_window[0] < cutoff:
			self.error_window.popleft()

	def _sleep_for_limits_if_needed(self) -> None:
		self._prune_windows()
		bytes_last_minute = sum(size for _, size in self.bytes_window)
		if bytes_last_minute >= 100 * 1024 * 1024:
			wait_seconds = max(1.0, 60 - (time.time() - self.bytes_window[0][0]))
			logging.warning(
				"Approaching BEA 100 MB/min limit, sleeping %.1f seconds", wait_seconds
			)
			time.sleep(wait_seconds)

		if len(self.error_window) >= 30:
			wait_seconds = max(1.0, 60 - (time.time() - self.error_window[0]))
			logging.warning(
				"Approaching BEA 30 errors/min limit, sleeping %.1f seconds", wait_seconds
			)
			time.sleep(wait_seconds)

	def _pace_request(self) -> None:
		elapsed = time.time() - self.last_request_time
		if elapsed < self.request_delay_seconds:
			time.sleep(self.request_delay_seconds - elapsed)

	def _record_response(self, response: requests.Response) -> None:
		now = time.time()
		content_length = len(response.content or b"")
		self.bytes_window.append((now, content_length))
		self._prune_windows()

	def _record_error(self) -> None:
		self.error_window.append(time.time())
		self._prune_windows()

	def get_json(self, method: str, params: dict[str, Any], max_retries: int = 5) -> dict[str, Any] | None:
		base_params = {
			"UserID": self.api_key,
			"method": method,
			"ResultFormat": "JSON",
		}
		base_params.update(params)

		for attempt in range(max_retries + 1):
			self._sleep_for_limits_if_needed()
			self._pace_request()
			try:
				response = self.session.get(BASE_URL, params=base_params, timeout=90)
				self.last_request_time = time.time()
				self._record_response(response)
			except requests.RequestException as exc:
				self._record_error()
				if attempt >= max_retries:
					logging.warning("Request failed after %s retries: %s", max_retries, exc)
					return None
				sleep_seconds = min(60.0, 2**attempt)
				logging.warning(
					"Connection error for method=%s (attempt %s/%s), sleeping %.1fs: %s",
					method,
					attempt + 1,
					max_retries + 1,
					sleep_seconds,
					exc,
				)
				time.sleep(sleep_seconds)
				continue

			if response.status_code == 429:
				self._record_error()
				retry_after_header = response.headers.get("Retry-After", "60").strip()
				try:
					retry_after_seconds = float(retry_after_header)
				except ValueError:
					retry_after_seconds = 60.0

				if attempt >= max_retries:
					logging.warning(
						"HTTP 429 persisted after %s retries for method=%s params=%s",
						max_retries,
						method,
						params,
					)
					return None

				logging.warning(
					"HTTP 429 for method=%s (attempt %s/%s), sleeping %.1fs",
					method,
					attempt + 1,
					max_retries + 1,
					retry_after_seconds,
				)
				time.sleep(retry_after_seconds)
				continue

			if 500 <= response.status_code <= 599:
				self._record_error()
				if attempt >= max_retries:
					logging.warning(
						"HTTP %s persisted after %s retries for method=%s params=%s",
						response.status_code,
						max_retries,
						method,
						params,
					)
					return None

				sleep_seconds = min(60.0, 2**attempt)
				logging.warning(
					"HTTP %s for method=%s (attempt %s/%s), sleeping %.1fs",
					response.status_code,
					method,
					attempt + 1,
					max_retries + 1,
					sleep_seconds,
				)
				time.sleep(sleep_seconds)
				continue

			if response.status_code >= 400:
				message = response.text.strip()
				raise RuntimeError(
					f"BEA request failed with status {response.status_code} for method={method}: {message}"
				)

			try:
				payload: dict[str, Any] = response.json()
			except ValueError as exc:
				self._record_error()
				raise RuntimeError(f"Invalid JSON response from BEA: {exc}") from exc

			error = payload.get("BEAAPI", {}).get("Error")
			if error:
				raise RuntimeError(f"BEA API error: {error}")

			return payload

		return None


def load_bea_api_key() -> str:
	load_dotenv(REPO_ROOT / ".env")
	load_dotenv()
	api_key = os.getenv("BEA_API_KEY", "").strip()
	if api_key:
		return api_key

	raise RuntimeError(
		"BEA_API_KEY is missing. Add it to your .env file. Sign up for a free BEA API key at "
		"https://apps.bea.gov/api/signup/"
	)


def _extract_results(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
	results = payload.get("BEAAPI", {}).get("Results", {})
	if isinstance(results, list):
		return []
	items = results.get(key, [])
	if isinstance(items, dict):
		return [items]
	if isinstance(items, list):
		return items
	return []


def fetch_parameter_list(client: BEAClient) -> list[dict[str, Any]]:
	payload = client.get_json(
		"GetParameterList",
		{
			"datasetname": DATASET_NAME,
		},
	)
	if payload is None:
		raise RuntimeError("Could not fetch BEA Regional parameter list.")
	return _extract_results(payload, "Parameter")


def fetch_line_code_mapping(client: BEAClient, table_name: str) -> dict[str, str]:
	payload = client.get_json(
		"GetParameterValuesFiltered",
		{
			"datasetname": DATASET_NAME,
			"TargetParameter": "LineCode",
			"TableName": table_name,
		},
	)
	if payload is None:
		raise RuntimeError(f"Could not fetch line codes for {table_name}.")

	values = _extract_results(payload, "ParamValue")
	mapping: dict[str, str] = {}
	for row in values:
		key = str(row.get("Key", "")).strip()
		desc = str(row.get("Desc", "")).strip()
		if not key or not desc:
			continue
		mapping[key] = desc
	return mapping


def load_or_refresh_schema(client: BEAClient, refresh_schema: bool) -> dict[str, Any]:
	if SCHEMA_PATH.exists() and not refresh_schema:
		with SCHEMA_PATH.open("r", encoding="utf-8") as infile:
			return json.load(infile)

	REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
	parameter_list = fetch_parameter_list(client)
	table_mappings = {table: fetch_line_code_mapping(client, table) for table in TABLES}

	schema = {
		"fetched_at_utc": datetime.now(timezone.utc).isoformat(),
		"dataset": DATASET_NAME,
		"parameter_list": parameter_list,
		"tables": table_mappings,
	}

	with SCHEMA_PATH.open("w", encoding="utf-8") as outfile:
		json.dump(schema, outfile, indent=2, sort_keys=True)

	logging.info("Saved BEA line-code schema to %s", SCHEMA_PATH)
	return schema


def _score_desc(desc: str, required_terms: list[str], bonus_terms: list[str] | None = None) -> int:
	normalized = _normalize_desc(desc)
	if not all(term in normalized for term in required_terms):
		return -1
	score = len(required_terms)
	if bonus_terms:
		for term in bonus_terms:
			if term in normalized:
				score += 1
	return score


def find_best_line_code(
	mapping: dict[str, str],
	required_terms: list[str],
	bonus_terms: list[str] | None = None,
	required: bool = True,
) -> str | None:
	best_key: str | None = None
	best_score = -1
	for key, desc in mapping.items():
		score = _score_desc(desc, required_terms=required_terms, bonus_terms=bonus_terms)
		if score > best_score:
			best_score = score
			best_key = key

	if best_key is None and required:
		raise RuntimeError(
			"Could not identify a required BEA line code with required terms "
			f"{required_terms}"
		)
	return best_key


def resolve_line_codes(schema: dict[str, Any]) -> dict[str, Any]:
	tables: dict[str, dict[str, str]] = schema["tables"]
	cagdp1 = tables["CAGDP1"]
	cagdp2 = tables["CAGDP2"]
	cainc1 = tables["CAINC1"]

	cagdp1_current = find_best_line_code(
		cagdp1,
		required_terms=["current", "gross domestic product"],
		bonus_terms=["dollar", "gdp"],
	)
	cagdp1_real = find_best_line_code(
		cagdp1,
		required_terms=["real", "gross domestic product"],
		bonus_terms=["chained", "gdp"],
	)
	cagdp1_growth = find_best_line_code(
		cagdp1,
		required_terms=["percent", "change", "real", "gdp"],
		bonus_terms=["all industry total", "prior"],
		required=False,
	)

	cagdp2_total = find_best_line_code(
		cagdp2,
		required_terms=["all industry total"],
		bonus_terms=["gdp"],
	)

	population_line = find_best_line_code(
		cainc1,
		required_terms=["population"],
		bonus_terms=["midperiod", "mid-year"],
	)
	per_capita_income_line = find_best_line_code(
		cainc1,
		required_terms=["per capita", "personal income"],
	)

	sector_groupings: dict[str, list[str]] = {
		"manufacturing_share": [],
		"construction_share": [],
		"government_share": [],
		"service_sector_share": [],
	}

	for line_code, desc in cagdp2.items():
		desc_text = str(desc)
		label_part = desc_text.split(":", 1)[-1] if ":" in desc_text else desc_text
		label_without_codes = re.sub(r"\([^)]*\)", "", label_part)
		sector_label = _normalize_desc(label_without_codes)
		norm = _normalize_desc(desc_text)

		if "manufacturing" in sector_label:
			sector_groupings["manufacturing_share"].append(line_code)
		if "construction" in sector_label:
			sector_groupings["construction_share"].append(line_code)
		if "government and government enterprises" in sector_label and "except" not in sector_label:
			sector_groupings["government_share"].append(line_code)
		if sector_label in SERVICE_SUPERSECTORS:
			sector_groupings["service_sector_share"].append(line_code)

	return {
		"cagdp1": {
			"current_dollar_line": cagdp1_current,
			"real_line": cagdp1_real,
			"percent_change_line": cagdp1_growth,
		},
		"cagdp2": {
			"all_line_codes": sorted(cagdp2.keys(), key=lambda x: int(x)),
			"all_industry_total_line": cagdp2_total,
			"sector_groupings": sector_groupings,
		},
		"cainc1": {
			"population_line": population_line,
			"per_capita_income_line": per_capita_income_line,
		},
	}


def print_sector_groupings(
	sector_groupings: dict[str, list[str]],
	cagdp2_mapping: dict[str, str],
) -> None:
	print("Resolved CAGDP2 sector groupings:")
	for group_name, line_codes in sector_groupings.items():
		print(f"\n- {group_name} ({len(line_codes)} line codes)")
		for code in sorted(line_codes, key=lambda x: int(x)):
			desc = cagdp2_mapping.get(code, "")
			print(f"  {code}: {desc}")


def _parse_geo_fips(value: Any) -> str:
	raw = str(value).strip().strip('"').strip("'")
	digits = re.sub(r"\D", "", raw)
	if not digits:
		return ""
	return digits.zfill(5)[-5:]


def _parse_state_abbr(county_name: str) -> str:
	if not isinstance(county_name, str):
		return ""
	parts = [part.strip() for part in county_name.split(",")]
	if len(parts) < 2:
		return ""
	candidate = parts[-1].upper()
	return candidate if re.fullmatch(r"[A-Z]{2}", candidate) else ""


def _parse_data_value(raw_value: Any) -> tuple[float, bool]:
	if raw_value is None:
		return math.nan, False

	raw = str(raw_value).strip()
	if raw in {"(D)", "(NA)"}:
		return math.nan, True

	raw = raw.replace(",", "")
	try:
		return float(raw), False
	except ValueError:
		return math.nan, False


def _apply_unit_multiplier(value: float, unit_mult: Any) -> float:
	if pd.isna(value):
		return float("nan")
	try:
		exp = int(str(unit_mult).strip())
	except ValueError:
		exp = 0
	return float(value * (10**exp))


def _extract_data_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
	return _extract_results(payload, "Data")


def fetch_table_line_data(
	client: BEAClient,
	table_name: str,
	line_code: str,
	years: str,
	line_desc: str,
) -> tuple[pd.DataFrame, int]:
	payload = client.get_json(
		"GetData",
		{
			"datasetname": DATASET_NAME,
			"TableName": table_name,
			"LineCode": line_code,
			"GeoFips": "COUNTY",
			"Year": years,
		},
	)

	if payload is None:
		logging.warning("Skipping %s line %s (%s) after retries", table_name, line_code, line_desc)
		return pd.DataFrame(), 0

	rows = _extract_data_rows(payload)
	parsed: list[dict[str, Any]] = []
	suppressed_count = 0

	for row in rows:
		geo_fips = _parse_geo_fips(row.get("GeoFips", row.get("GeoFIPS", "")))
		if not geo_fips:
			continue

		year_raw = str(row.get("TimePeriod", "")).strip()
		if not re.fullmatch(r"\d{4}", year_raw):
			continue

		value, is_suppressed = _parse_data_value(row.get("DataValue"))
		if is_suppressed:
			suppressed_count += 1
		scaled_value = _apply_unit_multiplier(value, row.get("UNIT_MULT", "0"))

		county_name = str(row.get("GeoName", "")).strip()
		parsed.append(
			{
				"county_fips": geo_fips,
				"county_name": county_name,
				"state_abbr": _parse_state_abbr(county_name),
				"year": int(year_raw),
				"table": table_name,
				"line_code": str(line_code),
				"line_desc": line_desc,
				"value": scaled_value,
			}
		)

	df = pd.DataFrame(parsed)
	logging.info("%s line %s (%s): %s rows", table_name, line_code, line_desc, len(df))
	return df, suppressed_count


def verify_cagdp2_line_code_rules(parameter_list: list[dict[str, Any]]) -> None:
	line_code_meta: dict[str, Any] | None = None
	for param in parameter_list:
		if str(param.get("ParameterName", "")).lower() == "linecode":
			line_code_meta = param
			break

	if line_code_meta is None:
		logging.warning("Could not find LineCode metadata in Regional GetParameterList response.")
		return

	multiple = str(line_code_meta.get("MultipleAcceptedFlag", "")).strip()
	all_value = str(line_code_meta.get("AllValue", "")).strip()
	logging.info(
		"Regional LineCode metadata: MultipleAcceptedFlag=%s, AllValue=%s",
		multiple,
		all_value or "<none>",
	)


def _build_series(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
	if df.empty:
		return pd.DataFrame(columns=["county_fips", "county_name", "state_abbr", "year", column_name])
	series = df[["county_fips", "county_name", "state_abbr", "year", "value"]].copy()
	series = series.rename(columns={"value": column_name})
	return series


def normalize_county_table(
	cagdp1_frames: list[pd.DataFrame],
	cagdp1_codes: dict[str, str | None],
	cagdp2_df: pd.DataFrame,
	cagdp2_total_line: str,
	sector_groupings: dict[str, list[str]],
	population_df: pd.DataFrame,
) -> pd.DataFrame:
	base_columns = ["county_fips", "county_name", "state_abbr", "year"]

	current_df = pd.DataFrame(columns=base_columns + ["gdp_current_dollars"])
	real_df = pd.DataFrame(columns=base_columns + ["gdp_real_chained_dollars"])

	for frame in cagdp1_frames:
		if frame.empty:
			continue
		line_code = str(frame["line_code"].iloc[0])
		if line_code == cagdp1_codes["current_dollar_line"]:
			current_df = _build_series(frame, "gdp_current_dollars")
		elif line_code == cagdp1_codes["real_line"]:
			real_df = _build_series(frame, "gdp_real_chained_dollars")

	pop_series = _build_series(population_df, "population")

	out = pd.merge(current_df, real_df, on=base_columns, how="outer")
	out = pd.merge(out, pop_series, on=base_columns, how="outer")

	if not cagdp2_df.empty:
		total_df = cagdp2_df[cagdp2_df["line_code"] == str(cagdp2_total_line)].copy()
		total_df = _build_series(total_df, "cagdp2_all_industry_total")
		out = pd.merge(out, total_df, on=base_columns, how="outer")

		for share_col, line_codes in sector_groupings.items():
			if not line_codes:
				out[share_col] = np.nan
				continue

			group_df = cagdp2_df[cagdp2_df["line_code"].isin(line_codes)].copy()
			if group_df.empty:
				out[share_col] = np.nan
				continue

			group_sum = (
				group_df.groupby(base_columns, dropna=False)["value"]
				.sum(min_count=1)
				.reset_index()
				.rename(columns={"value": f"{share_col}_numerator"})
			)
			out = pd.merge(out, group_sum, on=base_columns, how="left")
			out[share_col] = np.where(
				(out["cagdp2_all_industry_total"].notna()) & (out["cagdp2_all_industry_total"] != 0),
				out[f"{share_col}_numerator"] / out["cagdp2_all_industry_total"],
				np.nan,
			)
			out = out.drop(columns=[f"{share_col}_numerator"])
	else:
		for share_col in sector_groupings:
			out[share_col] = np.nan

	out = out.sort_values(["county_fips", "year"]).reset_index(drop=True)
	out["gdp_growth_pct"] = (
		out.groupby("county_fips", dropna=False)["gdp_real_chained_dollars"].pct_change() * 100.0
	)
	out["gdp_per_capita"] = np.where(
		(out["population"].notna()) & (out["population"] != 0),
		out["gdp_current_dollars"] / out["population"],
		np.nan,
	)
	out["gdp_per_capita_is_estimated"] = True

	out = out[
		[
			"county_fips",
			"county_name",
			"state_abbr",
			"year",
			"gdp_current_dollars",
			"gdp_real_chained_dollars",
			"gdp_growth_pct",
			"population",
			"gdp_per_capita",
			"gdp_per_capita_is_estimated",
			"manufacturing_share",
			"construction_share",
			"government_share",
			"service_sector_share",
		]
	]

	return out.sort_values(["county_fips", "year"]).reset_index(drop=True)


def write_quality_notes(
	output_df: pd.DataFrame,
	suppressed_count: int,
	notes_path: Path,
) -> None:
	share_cols = [
		"manufacturing_share",
		"construction_share",
		"government_share",
		"service_sector_share",
	]
	share_sum = output_df[share_cols].sum(axis=1, min_count=1)
	over_one = output_df.loc[share_sum > 1.0 + 1e-9, ["county_fips", "county_name", "year"] + share_cols]

	row_count = len(output_df)
	county_count = output_df["county_fips"].nunique(dropna=True)

	lines = [
		"# County GDP Data Quality Notes",
		"",
		f"Generated: {datetime.now(timezone.utc).isoformat()} UTC",
		"",
		"## Share sanity checks",
	]

	if over_one.empty:
		lines.append("No county-year rows had industry shares summing to more than 1.0.")
	else:
		lines.append(
			f"Found {len(over_one)} county-year rows where the four industry shares sum to > 1.0."
		)
		lines.append("")
		lines.append("Sample rows (first 25):")
		lines.append("")
		lines.append("| county_fips | county_name | year | manufacturing_share | construction_share | government_share | service_sector_share |")
		lines.append("|---|---|---:|---:|---:|---:|---:|")
		for _, row in over_one.head(25).iterrows():
			lines.append(
				"| "
				f"{row['county_fips']} | {row['county_name']} | {int(row['year'])} | "
				f"{row['manufacturing_share']:.6f} | {row['construction_share']:.6f} | "
				f"{row['government_share']:.6f} | {row['service_sector_share']:.6f} |"
			)

	lines.extend(
		[
			"",
			"## Suppressed values",
			f"Encountered {suppressed_count} BEA cells with `(D)` or `(NA)` and treated them as missing values.",
			"",
			"## Connecticut geographic comparability note",
			(
				"Connecticut's most recent BEA county-level vintages use planning regions instead of "
				"the state's legacy counties. Older vintages that use the same county_fips labels in CT "
				"may not be spatially comparable to newer vintages."
			),
			"",
			"## Basic sanity counts",
			f"Total row count: {row_count}",
			f"Distinct county_fips count: {county_count}",
			"Expected distinct county_fips is typically about 3,100-3,150 before/without CT planning-region transition handling.",
		]
	)

	notes_path.parent.mkdir(parents=True, exist_ok=True)
	notes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pipeline(config: PipelineConfig) -> int:
	api_key = load_bea_api_key()
	client = BEAClient(api_key=api_key, request_delay_seconds=0.7)

	schema = load_or_refresh_schema(client, refresh_schema=config.refresh_schema)
	resolved = resolve_line_codes(schema)

	cagdp2_mapping: dict[str, str] = schema["tables"]["CAGDP2"]
	print_sector_groupings(resolved["cagdp2"]["sector_groupings"], cagdp2_mapping)

	verify_cagdp2_line_code_rules(schema.get("parameter_list", []))

	suppressed_total = 0

	cagdp1_frames: list[pd.DataFrame] = []
	for key in ["current_dollar_line", "real_line", "percent_change_line"]:
		line_code = resolved["cagdp1"].get(key)
		if not line_code:
			continue
		desc = schema["tables"]["CAGDP1"].get(str(line_code), "")
		df, suppressed = fetch_table_line_data(client, "CAGDP1", str(line_code), config.years, desc)
		suppressed_total += suppressed
		cagdp1_frames.append(df)

	cagdp2_frames: list[pd.DataFrame] = []
	for line_code in resolved["cagdp2"]["all_line_codes"]:
		desc = schema["tables"]["CAGDP2"].get(str(line_code), "")
		df, suppressed = fetch_table_line_data(client, "CAGDP2", str(line_code), config.years, desc)
		suppressed_total += suppressed
		if not df.empty:
			cagdp2_frames.append(df)

	population_line = str(resolved["cainc1"]["population_line"])
	population_desc = schema["tables"]["CAINC1"].get(population_line, "")
	population_df, suppressed = fetch_table_line_data(
		client,
		"CAINC1",
		population_line,
		config.years,
		population_desc,
	)
	suppressed_total += suppressed

	cagdp2_df = pd.concat(cagdp2_frames, ignore_index=True) if cagdp2_frames else pd.DataFrame()
	out_df = normalize_county_table(
		cagdp1_frames=cagdp1_frames,
		cagdp1_codes=resolved["cagdp1"],
		cagdp2_df=cagdp2_df,
		cagdp2_total_line=str(resolved["cagdp2"]["all_industry_total_line"]),
		sector_groupings=resolved["cagdp2"]["sector_groupings"],
		population_df=population_df,
	)

	REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
	out_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
	write_quality_notes(out_df, suppressed_count=suppressed_total, notes_path=QUALITY_NOTES_PATH)

	if out_df.empty:
		logging.warning("Output dataframe is empty. Check API responses and filters.")
		return 1

	min_year = int(out_df["year"].min())
	max_year = int(out_df["year"].max())
	county_count = out_df["county_fips"].nunique(dropna=True)

	fully_missing = (
		out_df.groupby("county_fips", dropna=False)
		.agg(
			all_current_missing=("gdp_current_dollars", lambda s: s.isna().all()),
			all_real_missing=("gdp_real_chained_dollars", lambda s: s.isna().all()),
		)
		.reset_index()
	)
	fully_missing = fully_missing[
		fully_missing["all_current_missing"] & fully_missing["all_real_missing"]
	]["county_fips"].tolist()

	logging.info("Wrote normalized county GDP to %s", OUTPUT_CSV)
	logging.info("Wrote data quality notes to %s", QUALITY_NOTES_PATH)
	logging.info(
		"Final summary: rows=%s, counties=%s, years=%s-%s, suppressed_cells=%s",
		len(out_df),
		county_count,
		min_year,
		max_year,
		suppressed_total,
	)
	if fully_missing:
		logging.warning(
			"Counties fully missing GDP data across all years (%s): %s",
			len(fully_missing),
			", ".join(sorted(fully_missing)),
		)

	return 0


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Download and normalize BEA county GDP data.")
	parser.add_argument(
		"--years",
		default="ALL",
		help=(
			"Year selector passed to BEA (examples: ALL, LAST15, LAST10, LAST5, "
			"or comma-separated years like 2019,2020,2021)."
		),
	)
	parser.add_argument(
		"--refresh-schema",
		action="store_true",
		help="Refresh BEA line-code schema even if reference/bea_line_codes.json exists.",
	)
	return parser.parse_args()


def main() -> int:
	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
	args = parse_args()
	config = PipelineConfig(
		years=normalize_years_selector(str(args.years).strip()),
		refresh_schema=bool(args.refresh_schema),
	)
	return run_pipeline(config)


if __name__ == "__main__":
	raise SystemExit(main())