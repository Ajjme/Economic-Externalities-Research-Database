"""Parse NY DEC 2025 Social Cost of GHG tables (A1-A12) into a single long table.

Outputs:
- scghg_ny_combined.csv
- scghg_ny_combined.parquet

Expected final shape:
- 12 gases
- 31 years (2020-2050)
- 3 discount rates (2.5, 2.0, 1.5)
- 1,116 total rows
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

try:
	import pdfplumber
except ImportError as exc:
	raise ImportError(
		"Missing dependency 'pdfplumber'. Install it with: pip install pdfplumber"
	) from exc


SOURCE_DOCUMENT = "NY DEC 2025 Value of Carbon Guidance - SCGHG Appendix"
EXPECTED_GASES = [
	"CO2",
	"CH4",
	"N2O",
	"HFC-125",
	"HFC-134a",
	"HFC-143a",
	"HFC-32",
	"HFC-23",
	"HFC-227ea",
	"HFC-236fa",
	"HFC-245fa",
	"SF6",
]
TABLE_TO_GAS = {
	"A1": "CO2",
	"A2": "CH4",
	"A3": "N2O",
	"A4": "HFC-125",
	"A5": "HFC-134a",
	"A6": "HFC-143a",
	"A7": "HFC-32",
	"A8": "HFC-23",
	"A9": "HFC-227ea",
	"A10": "HFC-236fa",
	"A11": "HFC-245fa",
	"A12": "SF6",
}

CAPTION_PATTERN = re.compile(r"Table\s+A(?P<table_num>\d+)\s*:\s*(?P<body>.+)", re.IGNORECASE)
GAS_NAME_PATTERN = re.compile(r"Social cost of\s+(?P<gas_name>.+?),\s*2020-2050", re.IGNORECASE)
UNIT_PATTERN = re.compile(r"\(in\s+(?P<unit_text>[^)]+)\)", re.IGNORECASE)
ROW_PATTERN = re.compile(
	r"^\s*(?P<year>\d{4})\s+(?P<v25>[\d,]+)\s+(?P<v20>[\d,]+)\s+(?P<v15>[\d,]+)\s*$"
)


def parse_args() -> argparse.Namespace:
	base_dir = Path(__file__).resolve().parent
	default_pdf_path = base_dir / "New_York_SCGHG.pdf"
	default_output_dir = base_dir.parent.parent / "Outputs"

	parser = argparse.ArgumentParser(
		description="Extract NY DEC 2025 SCGHG tables (A1-A12) into a combined long-format dataset."
	)
	parser.add_argument(
		"--pdf-path",
		type=Path,
		default=default_pdf_path,
		help="Path to New_York_SCGHG.pdf",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=default_output_dir,
		help="Destination directory for scghg_ny_combined.csv/parquet",
	)
	return parser.parse_args()


def _normalize_whitespace(text: str) -> str:
	return re.sub(r"\s+", " ", text).strip()


def _normalize_caption_artifacts(text: str) -> str:
	"""Repair common PDF text artifacts for chemical formulas and wrapped tokens."""
	normalized = _normalize_whitespace(text)
	repairs = {
		"(CO )": "(CO2)",
		"(CH )": "(CH4)",
		"(N O)": "(N2O)",
		"metric ton CO ) 2": "metric ton CO2)",
		"metric ton CH ) 4": "metric ton CH4)",
		"metric ton N O) 2 2": "metric ton N2O)",
	}
	for bad, good in repairs.items():
		normalized = normalized.replace(bad, good)

	# Page 13 line-wrap artifact: "metric ton SF6)" can split as "metric ton SF6 )".
	normalized = normalized.replace("SF6 )", "SF6)")
	return _normalize_whitespace(normalized)


def _extract_caption_from_lines(lines: list[str]) -> tuple[str | None, str | None]:
	"""Return (table_id, caption_text) for pages that contain a data table caption."""
	caption_idx = None
	for idx, line in enumerate(lines):
		if CAPTION_PATTERN.search(line):
			caption_idx = idx
			break

	if caption_idx is None:
		return None, None

	# Data pages include the table body header; list-of-tables pages do not.
	has_discount_header = any("Discount Rate" in ln for ln in lines)
	if not has_discount_header:
		return None, None

	caption_lines: list[str] = []
	for line in lines[caption_idx:]:
		if "Discount Rate" in line:
			break
		caption_lines.append(line)

	caption_text = _normalize_caption_artifacts(" ".join(caption_lines))
	cap_match = CAPTION_PATTERN.search(caption_text)
	if not cap_match:
		return None, None

	table_id = f"A{int(cap_match.group('table_num'))}"
	return table_id, caption_text


def _to_float(value: str) -> float:
	return float(value.replace(",", ""))


def _parse_rows_from_text_lines(lines: list[str]) -> list[dict[str, float]]:
	rows: list[dict[str, float]] = []
	for line in lines:
		match = ROW_PATTERN.match(line)
		if not match:
			continue

		year = int(match.group("year"))
		if year < 2020 or year > 2050:
			continue

		rows.append(
			{
				"year": year,
				"2.5": _to_float(match.group("v25")),
				"2.0": _to_float(match.group("v20")),
				"1.5": _to_float(match.group("v15")),
			}
		)
	return rows


def _parse_rows_from_pdf_table(page: pdfplumber.page.Page) -> list[dict[str, float]]:
	"""Try structured table extraction first; this PDF often needs text fallback."""
	table = page.extract_table()
	if not table:
		return []

	rows: list[dict[str, float]] = []
	for raw_row in table:
		if not raw_row:
			continue
		joined = " ".join(str(cell).strip() for cell in raw_row if cell is not None and str(cell).strip())
		match = ROW_PATTERN.match(joined)
		if not match:
			continue

		year = int(match.group("year"))
		if year < 2020 or year > 2050:
			continue

		rows.append(
			{
				"year": year,
				"2.5": _to_float(match.group("v25")),
				"2.0": _to_float(match.group("v20")),
				"1.5": _to_float(match.group("v15")),
			}
		)
	return rows


def _parse_caption_fields(caption_text: str, table_id: str) -> tuple[str, str, str]:
	gas_code = TABLE_TO_GAS.get(table_id)
	if gas_code is None:
		raise ValueError(f"Unexpected table ID '{table_id}' not in expected A1-A12 mapping.")

	gas_name_match = GAS_NAME_PATTERN.search(caption_text)
	gas_name = gas_name_match.group("gas_name").strip() if gas_name_match else gas_code

	unit_match = UNIT_PATTERN.search(caption_text)
	unit_text = unit_match.group("unit_text").strip() if unit_match else "2020 dollars per metric ton"

	unit_text = _normalize_whitespace(unit_text)
	unit = re.sub(r"^2020\s+dollars", "2020 USD", unit_text, flags=re.IGNORECASE)
	unit = re.sub(r"\s+", " ", unit).strip()

	# Keep unit generic as requested (e.g., "2020 USD per metric ton").
	unit = re.sub(r"\s+[^\s)]+\)?$", "", unit) if "per metric ton" in unit else unit
	if "2020 USD per metric ton" not in unit:
		unit = "2020 USD per metric ton"

	return gas_code, gas_name, unit


def extract_combined_long_table(pdf_path: Path) -> tuple[pd.DataFrame, list[int], list[int]]:
	records: list[dict[str, object]] = []
	pages_with_caption_no_table: list[int] = []
	pages_with_table_no_caption: list[int] = []

	with pdfplumber.open(pdf_path) as pdf:
		for page_index, page in enumerate(pdf.pages, start=1):
			text = page.extract_text() or ""
			lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

			table_id, caption_text = _extract_caption_from_lines(lines)
			rows_from_table = _parse_rows_from_pdf_table(page)
			rows_from_text = _parse_rows_from_text_lines(lines)
			rows = rows_from_table if rows_from_table else rows_from_text

			has_caption = table_id is not None and caption_text is not None
			has_rows = len(rows) > 0

			if has_caption and not has_rows:
				pages_with_caption_no_table.append(page_index)
				continue
			if has_rows and not has_caption:
				pages_with_table_no_caption.append(page_index)
				continue
			if not has_caption and not has_rows:
				continue

			gas_code, gas_name, unit = _parse_caption_fields(caption_text, table_id)

			# Deduplicate by year in case both extraction methods capture overlapping rows.
			rows_by_year = {int(row["year"]): row for row in rows}
			for year in sorted(rows_by_year):
				row = rows_by_year[year]
				for discount_str, discount_rate in (("2.5", 2.5), ("2.0", 2.0), ("1.5", 1.5)):
					records.append(
						{
							"gas": gas_code,
							"gas_name": gas_name,
							"year": int(year),
							"discount_rate": float(discount_rate),
							"sc_value": float(row[discount_str]),
							"unit": unit,
							"source_table": table_id,
							"source_document": SOURCE_DOCUMENT,
						}
					)

	combined = pd.DataFrame(
		records,
		columns=[
			"gas",
			"gas_name",
			"year",
			"discount_rate",
			"sc_value",
			"unit",
			"source_table",
			"source_document",
		],
	)
	return combined, pages_with_caption_no_table, pages_with_table_no_caption


def validate_combined_table(df: pd.DataFrame) -> None:
	if df.empty:
		raise ValueError("No rows were extracted from the PDF.")

	gases_found = sorted(df["gas"].dropna().unique().tolist())
	if gases_found != sorted(EXPECTED_GASES):
		missing = sorted(set(EXPECTED_GASES) - set(gases_found))
		extra = sorted(set(gases_found) - set(EXPECTED_GASES))
		raise ValueError(
			"Validation failed for gases captured. "
			f"Missing: {missing or 'none'}. Extra: {extra or 'none'}."
		)

	rows_per_gas = df.groupby("gas").size()
	bad_gases = rows_per_gas[rows_per_gas != 93]
	if not bad_gases.empty:
		details = ", ".join(f"{gas}: {count}" for gas, count in bad_gases.items())
		raise ValueError(
			"Validation failed: each gas must have 93 rows (31 years x 3 discount rates). "
			f"Mismatches -> {details}"
		)

	expected_total_rows = 12 * 31 * 3
	if len(df) != expected_total_rows:
		raise ValueError(
			f"Validation failed: expected {expected_total_rows} total rows, found {len(df)}."
		)

	year_min = int(df["year"].min())
	year_max = int(df["year"].max())
	if year_min != 2020 or year_max != 2050:
		raise ValueError(
			"Validation failed: expected years 2020-2050. "
			f"Observed range {year_min}-{year_max}."
		)

	if sorted(df["discount_rate"].unique().tolist()) != [1.5, 2.0, 2.5]:
		raise ValueError(
			"Validation failed: expected discount_rate values [1.5, 2.0, 2.5]."
		)


def write_outputs(df: pd.DataFrame, output_dir: Path) -> tuple[Path, Path]:
	output_dir.mkdir(parents=True, exist_ok=True)
	csv_path = output_dir / "scghg_ny_combined.csv"
	parquet_path = output_dir / "scghg_ny_combined.parquet"

	df.to_csv(csv_path, index=False)
	try:
		df.to_parquet(parquet_path, index=False)
	except Exception as exc:
		raise RuntimeError(
			"Failed to write Parquet output. Install a parquet engine such as pyarrow: "
			"pip install pyarrow"
		) from exc

	return csv_path, parquet_path


def main() -> int:
	args = parse_args()
	pdf_path = args.pdf_path.expanduser().resolve()
	output_dir = args.output_dir.expanduser().resolve()

	if not pdf_path.exists():
		raise FileNotFoundError(f"PDF not found: {pdf_path}")

	combined, pages_caption_no_table, pages_table_no_caption = extract_combined_long_table(pdf_path)
	validate_combined_table(combined)
	csv_path, parquet_path = write_outputs(combined, output_dir)

	unique_gases = sorted(combined["gas"].unique().tolist())
	print(f"Unique gases found ({len(unique_gases)}): {unique_gases}")
	print(f"Total rows: {len(combined)}")
	print(f"Pages with caption but no parsed table: {pages_caption_no_table or 'none'}")
	print(f"Pages with parsed table but no caption: {pages_table_no_caption or 'none'}")
	print(f"Wrote CSV: {csv_path}")
	print(f"Wrote Parquet: {parquet_path}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
