"""Parse EREF 2024 tipping fee table from PDF into a structured CSV.

Phase 1 target:
- Table A2. State and Regional Average Tip Fees, from October 2024 Survey

Output columns:
- Region/State
- Average tipping Fee
- Standard Deviation
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import pdfplumber


SCRIPT_DIR = Path(__file__).resolve().parent
PDF_PATH = SCRIPT_DIR / "2025-EREF-Report-MSWLF-Tipping-Fees-2024-FINAL-xtdyli.pdf"
OUTPUT_CSV = SCRIPT_DIR / "EREF_2024_Tipping_Fees_Parsed.csv"

TABLE_MARKER = "Table A2. State and Regional Average Tip Fees, from October 2024 Survey"
NEXT_TABLE_MARKER = "Table A3"

# Handles both "+-" and the plus-minus symbol.
FEE_PATTERN = re.compile(
	r"\$?\s*(?P<avg>\d+(?:\.\d+)?)\s*\(\s*(?:\+\-|\+/\-|\u00b1)\s*(?P<std>\d+(?:\.\d+)?)\s*\)"
)

# Used when parsing raw text lines from the PDF.
LINE_PATTERN = re.compile(
	r"^(?P<region>[A-Za-z0-9][A-Za-z0-9\s\-\.,&'/()*]+?)\s+\$?\s*"
	r"(?P<avg>\d+(?:\.\d+)?)\s*\(\s*(?:\+\-|\+/\-|\u00b1)\s*(?P<std>\d+(?:\.\d+)?)\s*\)\s*$"
)

SKIP_REGION_PATTERNS = (
	"region/state",
	"average tip fee",
	"standard deviation",
	"state and regional average",
	"table a2",
	"source:",
	"n=",
)


def normalize_whitespace(value: str) -> str:
	return re.sub(r"\s+", " ", value).strip()


def parse_fee_text(text: str) -> Optional[tuple[float, float]]:
	match = FEE_PATTERN.search(text)
	if not match:
		return None
	return float(match.group("avg")), float(match.group("std"))


def should_skip_region(region: str) -> bool:
	candidate = region.lower()
	if not candidate:
		return True
	return any(token in candidate for token in SKIP_REGION_PATTERNS)


def clean_region(value: str) -> str:
	cleaned = normalize_whitespace(value)
	cleaned = re.sub(r"\*+$", "", cleaned).strip()
	cleaned = re.sub(r"\[[^\]]+\]$", "", cleaned).strip()
	return cleaned


def parse_row_from_cells(cells: Iterable[object]) -> Optional[tuple[str, float, float]]:
	text_cells = [normalize_whitespace(str(cell)) for cell in cells if cell is not None]
	text_cells = [cell for cell in text_cells if cell]
	if not text_cells:
		return None

	row_text = " | ".join(text_cells)
	fee = parse_fee_text(row_text)
	if fee is None:
		return None

	region = ""
	for cell in text_cells:
		fee_in_cell = parse_fee_text(cell)
		# Prefer the cell immediately before the fee-containing cell.
		if fee_in_cell is not None:
			idx = text_cells.index(cell)
			if idx > 0:
				candidate = clean_region(text_cells[idx - 1])
				if candidate and not should_skip_region(candidate):
					region = candidate
					break

	if not region:
		for cell in text_cells:
			if parse_fee_text(cell) is None:
				candidate = clean_region(cell)
				if candidate and not should_skip_region(candidate):
					region = candidate
					break

	if not region:
		region = clean_region(FEE_PATTERN.sub("", row_text))

	if should_skip_region(region):
		return None

	return region, fee[0], fee[1]


def extract_from_table_objects(page: pdfplumber.page.Page) -> list[tuple[str, float, float]]:
	results: list[tuple[str, float, float]] = []
	table_settings = {
		"vertical_strategy": "lines",
		"horizontal_strategy": "lines",
		"intersection_tolerance": 5,
	}

	tables = page.extract_tables(table_settings=table_settings) or []
	if not tables:
		tables = page.extract_tables() or []

	for table in tables:
		for row in table:
			parsed = parse_row_from_cells(row)
			if parsed:
				results.append(parsed)

	return results


def extract_from_text_lines(page_text: str) -> list[tuple[str, float, float]]:
	results: list[tuple[str, float, float]] = []
	for raw_line in page_text.splitlines():
		line = normalize_whitespace(raw_line)
		if not line:
			continue
		match = LINE_PATTERN.match(line)
		if not match:
			continue

		region = clean_region(match.group("region"))
		if should_skip_region(region):
			continue

		avg = float(match.group("avg"))
		std = float(match.group("std"))
		results.append((region, avg, std))

	return results


def extract_ordered_table_lines(page_text: str) -> list[tuple[str, float, float]]:
	"""Parse rows in visual order from page text, limited to Table A2 body.

	This reliably preserves the source order and captures starred state labels.
	"""
	results: list[tuple[str, float, float]] = []
	lines = page_text.splitlines()
	in_body = False

	for raw_line in lines:
		line = normalize_whitespace(raw_line)
		if not line:
			continue

		if TABLE_MARKER in line:
			in_body = True
			continue

		if not in_body:
			continue

		if line.startswith("Analysis of MSW Landfill Tipping Fees"):
			break
		if line.startswith("a ") or line.startswith("b ") or line.startswith("c ") or line.startswith("d "):
			break
		if line.startswith("Region/State"):
			continue

		match = LINE_PATTERN.match(line)
		if not match:
			continue

		region = clean_region(match.group("region"))
		if should_skip_region(region):
			continue

		avg = float(match.group("avg"))
		std = float(match.group("std"))
		results.append((region, avg, std))

	return results


def deduplicate_keep_order(
	rows: Iterable[tuple[str, float, float]],
) -> list[tuple[str, float, float]]:
	seen: set[str] = set()
	output: list[tuple[str, float, float]] = []
	for region, avg, std in rows:
		key = region.lower()
		if key in seen:
			continue
		seen.add(key)
		output.append((region, avg, std))
	return output


def main() -> int:
	print("Searching pages for Table A2...")

	if not PDF_PATH.exists():
		print(f"Source PDF not found: {PDF_PATH}")
		return 1

	all_rows: list[tuple[str, float, float]] = []
	found_table = False
	in_table_section = False

	with pdfplumber.open(PDF_PATH) as pdf:
		for page_index, page in enumerate(pdf.pages, start=1):
			page_text = page.extract_text() or ""

			if not in_table_section and TABLE_MARKER in page_text:
				in_table_section = True
				found_table = True
				print(f"Table A2 found on page {page_index}.")

			if in_table_section and NEXT_TABLE_MARKER in page_text and TABLE_MARKER not in page_text:
				print(f"Reached {NEXT_TABLE_MARKER}; stopping Table A2 extraction.")
				break

			if not in_table_section:
				continue

			ordered_rows = extract_ordered_table_lines(page_text)
			table_rows = extract_from_table_objects(page)
			text_rows = extract_from_text_lines(page_text)
			# Keep ordered text rows first, then supplement with table/object extraction.
			page_rows = deduplicate_keep_order([*ordered_rows, *table_rows, *text_rows])

			if page_rows:
				print(f"Parsed {len(page_rows)} rows from page {page_index}.")
				all_rows.extend(page_rows)

	if not found_table:
		print("Table A2 was not found in the PDF.")
		return 1

	rows = deduplicate_keep_order(all_rows)
	if not rows:
		print("Table A2 was found, but no valid rows were parsed.")
		return 1

	df = pd.DataFrame(rows, columns=["Region/State", "Average tipping Fee", "Standard Deviation"])
	df["Average tipping Fee"] = pd.to_numeric(df["Average tipping Fee"], errors="coerce")
	df["Standard Deviation"] = pd.to_numeric(df["Standard Deviation"], errors="coerce")
	df = df.dropna(subset=["Average tipping Fee", "Standard Deviation"])

	df.to_csv(OUTPUT_CSV, index=False)
	print(f"CSV exported successfully: {OUTPUT_CSV}")
	print(f"Rows exported: {len(df)}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
