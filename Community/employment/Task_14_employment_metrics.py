"""Download county-level BLS QCEW employment anchors for housing and roofing."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd


TARGET_NAICS_CODES = ("2361", "23816")
ROOFING_SUBSLICES = ("238161", "238162", "238163")
BLS_QCEW_URL_TEMPLATE = "https://data.bls.gov/cew/data/api/{year}/{quarter}/industry/{naics_code}.csv"

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "Outputs" / "bls_qcew_housing_roofing_anchors.csv"

COUNTY_REQUIRED_COLUMNS = {
	"area_fips",
	"own_code",
	"industry_code",
	"year",
	"qtr",
	"qtrly_estabs",
	"month3_emplvl",
	"total_qtrly_wages",
}

OUTPUT_COLUMNS = [
	"area_fips",
	"own_code",
	"industry_code",
	"year",
	"qtr",
	"qtrly_estabs_count",
	"month3_emplvl",
	"total_qtrly_wages",
]


def build_bls_url(year: str, quarter: str, naics_code: str) -> str:
	return BLS_QCEW_URL_TEMPLATE.format(year=year, quarter=quarter, naics_code=naics_code)


def fetch_qcew_slice(year: str, quarter: str, naics_code: str) -> pd.DataFrame:
	url = build_bls_url(year, quarter, naics_code)

	try:
		return pd.read_csv(url, dtype=str)
	except HTTPError as exc:
		if exc.code == 404:
			print(f"Skipping {naics_code} for {year} Q{quarter}: BLS returned 404 (not published yet).")
			return pd.DataFrame()
		raise
	except (TimeoutError, URLError, OSError) as exc:
		print(f"Skipping {naics_code} for {year} Q{quarter}: failed to download {url} ({exc}).")
		return pd.DataFrame()


def filter_county_rows(source: pd.DataFrame) -> pd.DataFrame:
	missing_columns = COUNTY_REQUIRED_COLUMNS.difference(source.columns)
	if missing_columns:
		raise ValueError(f"Missing expected BLS columns: {sorted(missing_columns)}")

	county_rows = source.copy()
	county_rows["area_fips"] = county_rows["area_fips"].fillna("").astype(str).str.strip()

	county_mask = (
		county_rows["area_fips"].str.fullmatch(r"\d{5}", na=False)
		& ~county_rows["area_fips"].isin({"00000"})
		& ~county_rows["area_fips"].str.endswith("000")
	)

	county_rows = county_rows.loc[
		county_mask,
		[
			"area_fips",
			"own_code",
			"industry_code",
			"year",
			"qtr",
			"qtrly_estabs",
			"month3_emplvl",
			"total_qtrly_wages",
		],
	].copy()

	county_rows = county_rows.rename(columns={"qtrly_estabs": "qtrly_estabs_count"})

	numeric_columns = ["qtrly_estabs_count", "month3_emplvl", "total_qtrly_wages"]
	for column in numeric_columns:
		county_rows[column] = pd.to_numeric(county_rows[column], errors="coerce")

	for column in ["own_code", "industry_code", "year", "qtr"]:
		county_rows[column] = county_rows[column].fillna("").astype(str).str.strip()

	return county_rows[OUTPUT_COLUMNS]


def build_county_anchors(year: str, quarter: str) -> pd.DataFrame:
	frames: list[pd.DataFrame] = []
	seen_codes: set[str] = set()

	for naics_code in (*TARGET_NAICS_CODES, *ROOFING_SUBSLICES):
		if naics_code in seen_codes:
			continue
		seen_codes.add(naics_code)

		source = fetch_qcew_slice(year, quarter, naics_code)
		if source.empty:
			continue

		county_rows = filter_county_rows(source)
		if county_rows.empty:
			print(f"No county rows found for {naics_code} in {year} Q{quarter}.")
			continue

		frames.append(county_rows)

	if not frames:
		return pd.DataFrame(columns=OUTPUT_COLUMNS)

	return pd.concat(frames, ignore_index=True)


def write_output(df: pd.DataFrame) -> Path:
	OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
	df.to_csv(OUTPUT_PATH, index=False)
	return OUTPUT_PATH


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Download county-level BLS QCEW employment anchors for residential construction and roofing."
	)
	parser.add_argument("--year", default="2025", help="Target BLS QCEW year, e.g. 2025")
	parser.add_argument("--quarter", default="3", help="Target BLS QCEW quarter, e.g. 3")
	return parser.parse_args()


def main() -> int:
	args = parse_args()

	anchors = build_county_anchors(str(args.year), str(args.quarter))
	if anchors.empty:
		print(f"No county-level anchors were downloaded for {args.year} Q{args.quarter}.")
		return 1

	output_path = write_output(anchors)
	print(f"Saved {len(anchors):,} county rows to {output_path}.")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
