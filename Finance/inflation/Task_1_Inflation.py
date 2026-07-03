"""Download FRED inflation series and a CBO long-term economic CSV."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_OUTPUT_DIR = Path("/data/economics/inflation")
FALLBACK_OUTPUT_DIR = REPO_ROOT / "data" / "economics" / "inflation"
FRED_SERIES = ["CPIAUCSL", "CPILFESL", "PCEPI"]
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
CBO_RAW_URL = (
	"https://raw.githubusercontent.com/US-CBO/cbo-data/main/"
	"data/economic/long_term_economic/rates_2026-02.csv"
)


def resolve_output_dir() -> Path:
	try:
		PRIMARY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
		return PRIMARY_OUTPUT_DIR
	except OSError:
		FALLBACK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
		print(
			f"Could not write to {PRIMARY_OUTPUT_DIR}; using {FALLBACK_OUTPUT_DIR} instead."
		)
		return FALLBACK_OUTPUT_DIR


def download_cbo_long_term_rates(session: requests.Session) -> Path:
	output_dir = resolve_output_dir()
	output_path = output_dir / "cbo_longterm_raw.csv"
	response = session.get(CBO_RAW_URL, timeout=30)
	response.raise_for_status()
	output_path.write_bytes(response.content)
	print(f"Saved CBO long-term economic CSV to {output_path}")
	return output_path


def fetch_fred_series(session: requests.Session, series_id: str, api_key: str) -> pd.DataFrame:
	response = session.get(
		FRED_URL,
		params={
			"series_id": series_id,
			"api_key": api_key,
			"file_type": "json",
		},
		timeout=30,
	)
	if response.status_code != 200:
		try:
			payload = response.json()
			message = payload.get("error_message") or payload.get("error_code") or response.text
		except ValueError:
			message = response.text
		raise RuntimeError(f"FRED request failed for {series_id}: {message}")

	payload = response.json()
	observations = payload.get("observations", [])

	df = pd.DataFrame(observations)
	if df.empty:
		return pd.DataFrame(columns=["date", "series_id", "value"])

	df = df.loc[:, ["date", "value"]].copy()
	df["series_id"] = series_id
	df["value"] = pd.to_numeric(df["value"], errors="coerce")
	return df[["date", "series_id", "value"]]


def main() -> int:
	load_dotenv()
	session = requests.Session()

	output_dir = resolve_output_dir()
	fred_output = output_dir / "fred_inflation.csv"

	download_cbo_long_term_rates(session)

	api_key = os.getenv("FRED_API_KEY")
	if not api_key:
		print("FRED_API_KEY is missing; skipping FRED inflation downloads.")
		return 1

	frames = []
	try:
		for series_id in FRED_SERIES:
			df = fetch_fred_series(session, series_id, api_key)
			frames.append(df)
			print(f"\nLast 5 observations for {series_id}:")
			print(df.tail(5).to_string(index=False))

		combined = pd.concat(frames, ignore_index=True)
		combined = combined.sort_values(["series_id", "date"]).reset_index(drop=True)
		combined.to_csv(fred_output, index=False)
		print(f"\nSaved combined FRED inflation data to {fred_output}")
		return 0
	except RuntimeError as exc:
		print(str(exc))
		return 1


if __name__ == "__main__":
	raise SystemExit(main())