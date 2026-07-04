"""Extract EPA SC-GHG 2023 Table A.5.1 to a CADENCE-ready CSV.

Source:
EPA, "Report on the Social Cost of Greenhouse Gases," 2023,
Table A.5.1 (printed pages 154-155; pdfplumber pages 159-160).

Units (all values are in 2020 USD):
- `scc_co2_*`: USD per metric ton CO2.
- `scc_ch4_*`: USD per metric ton CH4.
- `scc_n2o_*`: USD per metric ton N2O.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber


COLUMNS = [
	"emission_year",
	"scc_co2_2.5pct",
	"scc_co2_2.0pct",
	"scc_co2_1.5pct",
	"scc_ch4_2.5pct",
	"scc_ch4_2.0pct",
	"scc_ch4_1.5pct",
	"scc_n2o_2.5pct",
	"scc_n2o_2.0pct",
	"scc_n2o_1.5pct",
]

PAGE_INDICES = (159, 160)
EXPECTED_YEARS = list(range(2020, 2081))


def parse_args() -> argparse.Namespace:
	base_dir = Path(__file__).parent
	default_pdf = base_dir / "Epa_scghg_2023_report_final.pdf"
	default_output = base_dir / "table_a5_1_scghg_unrounded_2020_2080.csv"

	parser = argparse.ArgumentParser(
		description="Extract Table A.5.1 (unrounded SC-GHG values, 2020-2080) from EPA SC-GHG 2023 PDF."
	)
	parser.add_argument(
		"--pdf-path",
		type=Path,
		default=default_pdf,
		help="Path to Epa_scghg_2023_report_final.pdf",
	)
	parser.add_argument(
		"--output",
		type=Path,
		default=default_output,
		help="Output CSV path",
	)
	return parser.parse_args()


ROW_PATTERN = re.compile(
	r"^\s*(\d{4})\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$"
)


def _to_int(value: str) -> int:
	return int(value.replace(",", "").strip())


def _line_to_row(line: str) -> dict[str, int] | None:
	match = ROW_PATTERN.match(line)
	if not match:
		return None

	year = int(match.group(1))
	if year < 2020 or year > 2080:
		return None

	nums = [_to_int(match.group(i)) for i in range(2, 11)]
	return {
		"emission_year": year,
		"scc_co2_2.5pct": nums[0],
		"scc_co2_2.0pct": nums[1],
		"scc_co2_1.5pct": nums[2],
		"scc_ch4_2.5pct": nums[3],
		"scc_ch4_2.0pct": nums[4],
		"scc_ch4_1.5pct": nums[5],
		"scc_n2o_2.5pct": nums[6],
		"scc_n2o_2.0pct": nums[7],
		"scc_n2o_1.5pct": nums[8],
	}


def _extract_rows_from_table(page: pdfplumber.page.Page) -> list[dict[str, int]]:
	table = page.extract_table()
	if not table:
		return []

	rows: list[dict[str, int]] = []
	for raw_row in table:
		if not raw_row:
			continue
		joined = " ".join(str(cell).strip() for cell in raw_row if cell is not None and str(cell).strip())
		if not joined:
			continue
		parsed = _line_to_row(joined)
		if parsed:
			rows.append(parsed)
	return rows


def _extract_rows_from_text(page: pdfplumber.page.Page) -> list[dict[str, int]]:
	text = page.extract_text() or ""
	rows: list[dict[str, int]] = []
	for line in text.splitlines():
		parsed = _line_to_row(line)
		if parsed:
			rows.append(parsed)
	return rows


def extract_table_a51(pdf_path: Path) -> list[dict[str, int]]:
	all_rows: list[dict[str, int]] = []

	with pdfplumber.open(pdf_path) as pdf:
		for page_idx in PAGE_INDICES:
			page = pdf.pages[page_idx]
			rows = _extract_rows_from_table(page)

			# Some pages may not expose table gridlines reliably; fallback to text parsing.
			if not rows:
				rows = _extract_rows_from_text(page)

			if not rows:
				raise ValueError(
					f"Could not parse any data rows from pdfplumber page index {page_idx}."
				)

			all_rows.extend(rows)

	# Deduplicate by year in case extraction method captures duplicates.
	rows_by_year = {row["emission_year"]: row for row in all_rows}
	sorted_rows = [rows_by_year[year] for year in sorted(rows_by_year)]
	return sorted_rows


def validate_rows(rows: list[dict[str, int]]) -> None:
	years = [row["emission_year"] for row in rows]
	if len(rows) != 61:
		raise ValueError(
			f"Validation failed: expected 61 rows (2020-2080), found {len(rows)} rows."
		)
	if years != EXPECTED_YEARS:
		missing = sorted(set(EXPECTED_YEARS) - set(years))
		extra = sorted(set(years) - set(EXPECTED_YEARS))
		raise ValueError(
			"Validation failed: emission_year is not a contiguous 2020-2080 sequence. "
			f"Missing years: {missing or 'none'}. Extra years: {extra or 'none'}."
		)


def main() -> int:
	args = parse_args()
	pdf_path = args.pdf_path.expanduser().resolve()
	output_path = args.output.expanduser().resolve()

	if not pdf_path.exists():
		raise FileNotFoundError(f"PDF not found: {pdf_path}")

	rows = extract_table_a51(pdf_path)
	validate_rows(rows)

	df = pd.DataFrame(rows, columns=COLUMNS)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	df.to_csv(output_path, index=False)

	print(
		f"Wrote {len(df)} rows ({df['emission_year'].min()}-{df['emission_year'].max()}) to {output_path}"
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
