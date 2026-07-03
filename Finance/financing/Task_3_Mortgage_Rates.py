import csv
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

try:
	from dotenv import load_dotenv
except ImportError:
	load_dotenv = None


FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {
	"MORTGAGE30US": "30-year fixed",
	"MORTGAGE15US": "15-year fixed",
}
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = REPO_ROOT / "data" / "economics" / "mortgage_rates" / "fred_mortgage_rates.csv"


def fetch_series_observations(api_key: str, series_id: str) -> list:
	params = {
		"series_id": series_id,
		"api_key": api_key,
		"file_type": "json",
	}
	url = f"{FRED_BASE_URL}?{urlencode(params)}"

	with urlopen(url, timeout=30) as response:
		payload = json.load(response)

	return payload.get("observations", [])


def parse_rows(series_id: str, loan_type: str, observations: list) -> list:
	rows = []
	for obs in observations:
		value = obs.get("value")
		if value in (None, "."):
			continue

		rows.append(
			{
				"date": obs.get("date"),
				"loan_type": loan_type,
				"interest_rate": float(value),
				"series_id": series_id,
			}
		)
	return rows


def write_csv(rows: list, output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)

	fieldnames = ["date", "loan_type", "interest_rate"]
	with output_path.open("w", newline="", encoding="utf-8") as csv_file:
		writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
		writer.writeheader()
		for row in rows:
			writer.writerow(
				{
					"date": row["date"],
					"loan_type": row["loan_type"],
					"interest_rate": row["interest_rate"],
				}
			)


def print_recent(rows: list) -> None:
	for series_id, loan_type in SERIES.items():
		series_rows = [row for row in rows if row["series_id"] == series_id]
		recent = sorted(series_rows, key=lambda item: item["date"], reverse=True)[:5]

		print(f"\n{series_id} ({loan_type}) - 5 most recent weekly observations")
		for row in recent:
			print(f"{row['date']}: {row['interest_rate']:.2f}%")


def main() -> None:
	if load_dotenv is not None:
		load_dotenv()

	api_key = os.getenv("FRED_API_KEY")
	if not api_key:
		raise RuntimeError("FRED_API_KEY is not set. Add it to your environment or .env file.")

	all_rows = []

	# FRED release 190 (Primary Mortgage Market Survey) includes additional series
	# such as ARM and HELOC; we are intentionally only fetching fixed-rate series here.
	for series_id, loan_type in SERIES.items():
		observations = fetch_series_observations(api_key, series_id)
		all_rows.extend(parse_rows(series_id, loan_type, observations))

	all_rows.sort(key=lambda row: (row["date"], row["series_id"]))
	write_csv(all_rows, OUTPUT_PATH)

	print(f"Saved {len(all_rows)} rows to {OUTPUT_PATH}")
	print_recent(all_rows)


if __name__ == "__main__":
	main()
