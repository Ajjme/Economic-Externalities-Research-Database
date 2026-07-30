"""Build county-level temporary housing relocation costs from HUD FMR API.

This script fetches county-level Fair Market Rent (FMR) values for all states,
converts monthly FMR to daily costs, and writes a CSV output:

Failure Costs/housing/temporary_housing_relocation_costs.csv
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from dotenv import load_dotenv


BASE_URL = "https://www.huduser.gov/hudapi/public/fmr"
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = SCRIPT_DIR / "temporary_housing_relocation_costs.csv"

BEDROOM_COLUMNS = [
	"Efficiency",
	"One-Bedroom",
	"Two-Bedroom",
	"Three-Bedroom",
	"Four-Bedroom",
]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Build county-level temporary relocation daily costs from HUD FMR data."
	)
	parser.add_argument(
		"--year",
		type=int,
		default=2025,
		help="FMR year to query. Default: 2025",
	)
	parser.add_argument(
		"--days-per-month",
		type=float,
		default=30.0,
		help="Divisor to convert monthly rent to daily rent. Default: 30.0",
	)
	parser.add_argument(
		"--primary-bedroom",
		choices=BEDROOM_COLUMNS,
		default="Two-Bedroom",
		help="Bedroom tier used for relocation_cost_per_day. Default: Two-Bedroom",
	)
	return parser.parse_args()


def build_session(api_key: str) -> requests.Session:
	session = requests.Session()
	session.headers.update(
		{
			"Authorization": f"Bearer {api_key}",
			"Accept": "application/json",
		}
	)
	return session


def request_json(
	session: requests.Session,
	url: str,
	params: dict[str, str] | None = None,
	max_retries: int = 3,
	backoff_seconds: float = 1.0,
) -> object:
	for attempt in range(1, max_retries + 1):
		try:
			response = session.get(url, params=params, timeout=60)
			response.raise_for_status()
			return response.json()
		except requests.RequestException:
			if attempt >= max_retries:
				raise
			time.sleep(backoff_seconds * attempt)

	# Defensive fallback; loop should always return or raise.
	raise RuntimeError("Failed to fetch JSON after retries")


def extract_data_list(payload: object) -> list[dict]:
	if isinstance(payload, list):
		return [item for item in payload if isinstance(item, dict)]

	if isinstance(payload, dict):
		data = payload.get("data")
		if isinstance(data, list):
			return [item for item in data if isinstance(item, dict)]

	return []


def extract_counties(payload: object) -> list[dict]:
	if not isinstance(payload, dict):
		return []

	data = payload.get("data")
	if not isinstance(data, dict):
		return []

	counties = data.get("counties")
	if isinstance(counties, list):
		return [item for item in counties if isinstance(item, dict)]

	return []


def to_float(value: object) -> float | None:
	if value is None or value == "":
		return None
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def records_from_counties(
	counties: Iterable[dict],
	state_code: str,
	state_name: str,
	year: int,
	days_per_month: float,
	primary_bedroom: str,
) -> list[dict[str, object]]:
	rows: list[dict[str, object]] = []

	for county in counties:
		fips_code = str(county.get("fips_code") or "").strip()
		if not fips_code:
			continue

		county_name = str(county.get("county_name") or "").strip()
		metro_name = str(county.get("metro_name") or "").strip()
		town_name = str(county.get("town_name") or "").strip()
		smallarea_status = str(county.get("smallarea_status") or "").strip()

		row: dict[str, object] = {
			"year": year,
			"state_code": state_code,
			"state_name": state_name,
			"county_name": county_name,
			"town_name": town_name,
			"metro_name": metro_name,
			"smallarea_status": smallarea_status,
			"hud_fips_code": fips_code,
			"county_fips": fips_code[:5] if len(fips_code) >= 5 else "",
		}

		for bedroom in BEDROOM_COLUMNS:
			monthly = to_float(county.get(bedroom))
			monthly_col = f"monthly_{bedroom.lower().replace('-', '_').replace(' ', '_')}"
			daily_col = f"daily_{bedroom.lower().replace('-', '_').replace(' ', '_')}"
			row[monthly_col] = monthly
			row[daily_col] = (monthly / days_per_month) if monthly is not None else None

		primary_monthly_col = (
			f"monthly_{primary_bedroom.lower().replace('-', '_').replace(' ', '_')}"
		)
		primary_daily_col = f"daily_{primary_bedroom.lower().replace('-', '_').replace(' ', '_')}"
		row["primary_bedroom"] = primary_bedroom
		row["relocation_cost_per_day"] = row.get(primary_daily_col)
		row["relocation_monthly_basis"] = row.get(primary_monthly_col)

		rows.append(row)

	return rows


def build_relocation_costs(year: int, days_per_month: float, primary_bedroom: str) -> pd.DataFrame:
	load_dotenv()
	api_key = os.getenv("HUD_API_KEY", "").strip()
	if not api_key:
		raise RuntimeError("HUD_API_KEY is missing. Add it to .env before running this script.")

	if days_per_month <= 0:
		raise ValueError("days_per_month must be greater than zero.")

	session = build_session(api_key)
	states_payload = request_json(session, f"{BASE_URL}/listStates")
	states = extract_data_list(states_payload)

	all_rows: list[dict[str, object]] = []
	for state in states:
		state_code = str(state.get("state_code") or "").strip()
		state_name = str(state.get("state_name") or "").strip()
		if not state_code:
			continue

		state_url = f"{BASE_URL}/statedata/{state_code}"
		state_payload = request_json(session, state_url, params={"year": str(year)})
		counties = extract_counties(state_payload)

		if not counties:
			print(f"No county data returned for {state_code} in {year}; skipping.")
			continue

		all_rows.extend(
			records_from_counties(
				counties=counties,
				state_code=state_code,
				state_name=state_name,
				year=year,
				days_per_month=days_per_month,
				primary_bedroom=primary_bedroom,
			)
		)

	df = pd.DataFrame(all_rows)
	if df.empty:
		return df

	df = df.sort_values(["state_code", "county_name", "town_name"], na_position="last").reset_index(drop=True)
	return df


def main() -> int:
	args = parse_args()

	try:
		df = build_relocation_costs(
			year=args.year,
			days_per_month=args.days_per_month,
			primary_bedroom=args.primary_bedroom,
		)
	except Exception as exc:
		print(f"Failed to build relocation costs: {exc}")
		return 1

	if df.empty:
		print("No county-level FMR rows were returned; no CSV written.")
		return 1

	OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
	df.to_csv(OUTPUT_PATH, index=False)
	print(f"Saved {len(df):,} rows to {OUTPUT_PATH}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
