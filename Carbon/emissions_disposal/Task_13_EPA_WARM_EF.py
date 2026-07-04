"""Compile roofing end-of-life emission factors from EPA GHG Hub Table 9.

This script extracts Scope 3 Category 5/12 factors (Table 9), maps vetted
roofing materials to EPA/WARM proxy materials, and writes a clean lookup table.
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd


TABLE9_REQUIRED_HEADERS = ("material", "recycled", "landfilled", "combusted")
TABLE9_DEFAULT_HEADER_ROW_1_INDEXED = 432
TABLE9_SCAN_LIMIT_ROWS = 450
DISPLAY_NA = "NA — not published in Table 9"


def _candidate_workbook_paths(xlsx_path: Path) -> list[Path]:
	"""Generate plausible workbook locations for future annual Hub releases."""
	script_dir = Path(__file__).resolve().parent
	repo_root = Path(__file__).resolve().parents[2]
	stem_candidates = [
		xlsx_path.name,
		xlsx_path.name.replace("emissions", "emission"),
		xlsx_path.name.replace("emission", "emissions"),
		"ghg-emission-factors-hub-2025.xlsx",
		"ghg-emissions-factors-hub-2025.xlsx",
	]

	search_dirs = [
		xlsx_path.parent,
		script_dir,
		repo_root / "data",
		repo_root / "Carbon" / "emissions_disposal",
	]

	candidates: list[Path] = []
	seen: set[Path] = set()
	for directory in search_dirs:
		for stem in stem_candidates:
			candidate = (directory / stem).resolve()
			if candidate not in seen:
				candidates.append(candidate)
				seen.add(candidate)
	return candidates


def _resolve_input_workbook_path(xlsx_path: Path) -> Path:
	"""Resolve the workbook path, allowing for nearby filename drift."""
	if xlsx_path.exists():
		return xlsx_path

	for candidate in _candidate_workbook_paths(xlsx_path):
		if candidate.exists():
			return candidate

	tried_paths = "\n".join(f"- {path}" for path in _candidate_workbook_paths(xlsx_path))
	raise FileNotFoundError(
		"Input workbook not found. Tried the following locations:\n"
		f"{tried_paths}"
	)


ROOFING_TO_WARM_PROXY = {
	"Asphalt Shingles (3-tab/architectural)": "Asphalt Shingles",
	"Built-up Roofing (BUR) / Modified Bitumen": "Asphalt Concrete",
	"Clay Tile": "Clay Bricks",
	"Concrete Tile": "Concrete",
	"Slate": "Concrete",
	"Steel Roofing (standing seam/corrugated/metal shingle)": "Structural Steel",
	"Aluminum Roofing/Flashing": "Aluminum Ingot",
	"Copper Roofing/Flashing": "Copper Wire",
	"Wood Shakes/Shingles": "Dimensional Lumber",
	"TPO Membrane": "PP (Polypropylene)",
	"EPDM Rubber Membrane": "Tires",
	"PVC Single-ply Membrane": "PVC",
	"Fiberglass Shingle Mat/Insulation": "Fiberglass Insulation",
	"Gypsum Roof Cover Board": "Drywall",
}


MATERIAL_NOTES = {
	"Slate": "No dedicated slate/stone category in WARM; proxied to Concrete as nearest inert mineral C&D material.",
	"Copper Roofing/Flashing": "WARM has no sheet-copper category; Copper Wire is the only copper proxy available.",
	"TPO Membrane": "No dedicated TPO line item in Table 9; PP (Polypropylene) is the closest thermoplastic proxy.",
	"EPDM Rubber Membrane": "No dedicated EPDM line item in Table 9; Tires is the closest rubber proxy.",
	"Clay Tile": "No dedicated clay roofing tile category in WARM; proxied to Clay Bricks as nearest ceramic mineral proxy.",
	"Wood Shakes/Shingles": "No dedicated wood roofing shakes category in WARM; proxied to Dimensional Lumber.",
	"PVC Single-ply Membrane": "No dedicated PVC roofing membrane category in WARM; proxied to PVC material line.",
	"Gypsum Roof Cover Board": "No dedicated roof cover board line in WARM; proxied to Drywall as the closest gypsum product.",
}


def _normalize_text(value: object) -> str:
	"""Normalize text for robust case/whitespace-insensitive matching."""
	if value is None or (isinstance(value, float) and np.isnan(value)):
		return ""
	return " ".join(str(value).strip().lower().split())


def _match_required_columns(columns: pd.Index) -> dict[str, str]:
	"""Map required canonical headers to actual Table 9 columns.

	Matching is case-insensitive and whitespace-insensitive, and allows
	additional unit text in the source header names.
	"""
	normalized_to_actual: dict[str, str] = {}
	for col in columns:
		normalized = _normalize_text(col)
		normalized_to_actual[normalized] = str(col)

	matches: dict[str, str] = {}
	for required in TABLE9_REQUIRED_HEADERS:
		for normalized, actual in normalized_to_actual.items():
			if required in normalized:
				matches[required] = actual
				break

	missing = [key for key in TABLE9_REQUIRED_HEADERS if key not in matches]
	if missing:
		raise ValueError(
			"Unable to map required Table 9 columns. "
			f"Missing: {missing}. Available headers: {list(columns)}"
		)

	return matches


def _find_header_row_in_preview(preview_df: pd.DataFrame) -> int | None:
	"""Find the header row index by scanning for Material/Landfilled labels."""
	for row_idx, row in preview_df.iterrows():
		normalized_cells = [_normalize_text(cell) for cell in row.tolist()]
		has_material = any("material" in cell for cell in normalized_cells)
		has_landfilled = any("landfilled" in cell for cell in normalized_cells)
		if has_material and has_landfilled:
			return int(row_idx)
	return None


def _resolve_table_9_sheet_and_header(xlsx_path: Path) -> tuple[str, int]:
	"""Resolve the sheet and header row for Table 9 with fallback scanning.

	The function first tries row 432 (1-indexed) across sheets. If this does not
	yield the expected columns, it scans the first ~450 rows in each sheet for a
	row containing both "Material" and "Landfilled".
	"""
	header_row_zero_indexed = TABLE9_DEFAULT_HEADER_ROW_1_INDEXED - 1
	excel_file = pd.ExcelFile(xlsx_path, engine="openpyxl")

	for sheet in excel_file.sheet_names:
		try:
			trial_df = pd.read_excel(
				xlsx_path,
				sheet_name=sheet,
				header=header_row_zero_indexed,
				nrows=5,
				engine="openpyxl",
			)
			_match_required_columns(trial_df.columns)
			return sheet, header_row_zero_indexed
		except Exception:
			continue

	for sheet in excel_file.sheet_names:
		preview_df = pd.read_excel(
			xlsx_path,
			sheet_name=sheet,
			header=None,
			nrows=TABLE9_SCAN_LIMIT_ROWS,
			engine="openpyxl",
			dtype=str,
		)
		candidate_header = _find_header_row_in_preview(preview_df)
		if candidate_header is None:
			continue

		try:
			trial_df = pd.read_excel(
				xlsx_path,
				sheet_name=sheet,
				header=candidate_header,
				nrows=5,
				engine="openpyxl",
			)
			_match_required_columns(trial_df.columns)
			return sheet, candidate_header
		except Exception:
			continue

	raise ValueError(
		"Could not locate Table 9 headers in workbook. "
		f"Tried default row {TABLE9_DEFAULT_HEADER_ROW_1_INDEXED} and scanned "
		f"first {TABLE9_SCAN_LIMIT_ROWS} rows for 'Material' + 'Landfilled' "
		f"across sheets: {excel_file.sheet_names}."
	)


def load_table_9(xlsx_path: Path) -> pd.DataFrame:
	"""Load and clean EPA Hub Table 9 into canonical columns.

	Args:
		xlsx_path: Path to the EPA GHG Emission Factors Hub workbook.

	Returns:
		DataFrame with columns:
		["material", "recycled_mt_per_ton", "landfilled_mt_per_ton",
		 "combusted_mt_per_ton"]
	"""
	xlsx_path = _resolve_input_workbook_path(xlsx_path)

	sheet_name, header_row = _resolve_table_9_sheet_and_header(xlsx_path)
	raw_df = pd.read_excel(
		xlsx_path,
		sheet_name=sheet_name,
		header=header_row,
		engine="openpyxl",
	)

	column_map = _match_required_columns(raw_df.columns)
	table9_df = raw_df[
		[
			column_map["material"],
			column_map["recycled"],
			column_map["landfilled"],
			column_map["combusted"],
		]
	].rename(
		columns={
			column_map["material"]: "material",
			column_map["recycled"]: "recycled_mt_per_ton",
			column_map["landfilled"]: "landfilled_mt_per_ton",
			column_map["combusted"]: "combusted_mt_per_ton",
		}
	)

	table9_df["material"] = (
		table9_df["material"]
		.astype("string")
		.fillna("")
		.str.strip()
	)
	table9_df = table9_df[table9_df["material"] != ""].copy()

	for numeric_col in (
		"recycled_mt_per_ton",
		"landfilled_mt_per_ton",
		"combusted_mt_per_ton",
	):
		cleaned = table9_df[numeric_col].astype("string").str.strip()
		cleaned = cleaned.mask(cleaned.str.upper().isin({"", "NA", "N/A", "-"}))
		table9_df[numeric_col] = pd.to_numeric(cleaned, errors="coerce")

	# Drop metadata/source rows that can appear below the table body.
	is_source_row = table9_df["material"].str.lower().str.startswith("source:")
	has_any_factor = table9_df[
		["recycled_mt_per_ton", "landfilled_mt_per_ton", "combusted_mt_per_ton"]
	].notna().any(axis=1)
	table9_df = table9_df[~is_source_row & has_any_factor].copy()

	if table9_df.empty:
		raise ValueError("Table 9 loaded but no material rows were found after cleaning.")

	first_material = table9_df["material"].iloc[0]
	last_material = table9_df["material"].iloc[-1]
	print(
		"Loaded Table 9 from "
		f"sheet '{sheet_name}' (header row {header_row + 1}) with "
		f"{len(table9_df)} rows."
	)
	print(f"Sanity check materials: first='{first_material}', last='{last_material}'")

	return table9_df.reset_index(drop=True)


def _build_material_lookup(table9_df: pd.DataFrame) -> dict[str, pd.Series]:
	"""Build normalized material-name lookup for fast proxy matching."""
	lookup: dict[str, pd.Series] = {}
	for _, row in table9_df.iterrows():
		lookup[_normalize_text(row["material"])] = row
	return lookup


def warn_on_unmatched_proxies(table9_df: pd.DataFrame, proxy_map: dict[str, str]) -> None:
	"""Warn when a proxy material in mapping is not found in Table 9 material names."""
	material_lookup = _build_material_lookup(table9_df)
	unique_proxies = sorted(set(proxy_map.values()))
	for proxy in unique_proxies:
		if _normalize_text(proxy) not in material_lookup:
			warnings.warn(
				"Proxy material not found in Table 9 (case-insensitive check): "
				f"'{proxy}'. Please verify annual naming changes.",
				stacklevel=2,
			)


def _missing_factor_note(factor_name: str, combusted_value: float | None) -> str:
	"""Build a standard fallback note when a required factor is missing."""
	if pd.notna(combusted_value):
		return (
			f"No {factor_name} factor available; consider Combusted EF of "
			f"{combusted_value:.6g} as fallback."
		)
	return (
		f"No {factor_name} factor available; no Combusted EF fallback exists in "
		"Table 9."
	)


def build_roofing_ef_table(
	table9_df: pd.DataFrame, proxy_map: dict[str, str]
) -> pd.DataFrame:
	"""Build compiled roofing end-of-life EF table from Table 9 proxy mapping."""
	material_lookup = _build_material_lookup(table9_df)
	rows: list[dict[str, object]] = []

	for roofing_material, proxy_material in proxy_map.items():
		proxy_row = material_lookup.get(_normalize_text(proxy_material))
		notes: list[str] = []

		if proxy_row is None:
			recycled_value = np.nan
			landfilled_value = np.nan
			combusted_value = np.nan
			notes.append(
				f"Proxy '{proxy_material}' was not matched in Table 9; verify EPA naming drift."
			)
		else:
			recycled_value = proxy_row["recycled_mt_per_ton"]
			landfilled_value = proxy_row["landfilled_mt_per_ton"]
			combusted_value = proxy_row["combusted_mt_per_ton"]

		landfilled_cell: float | str
		recycled_cell: float | str

		if pd.isna(landfilled_value):
			landfilled_cell = DISPLAY_NA
			notes.append(_missing_factor_note("landfilling", combusted_value))
		else:
			landfilled_cell = float(landfilled_value)

		if pd.isna(recycled_value):
			recycled_cell = DISPLAY_NA
			notes.append(_missing_factor_note("recycling", combusted_value))
		else:
			recycled_cell = float(recycled_value)

		if roofing_material in MATERIAL_NOTES:
			notes.append(MATERIAL_NOTES[roofing_material])

		rows.append(
			{
				"Roofing Material Type": roofing_material,
				"Closest WARM/Hub Proxy": proxy_material,
				"Landfilling EF (MT CO2e/short ton)": landfilled_cell,
				"Recycling/Processing EF (MT CO2e/short ton)": recycled_cell,
				"Notes": " ".join(notes),
			}
		)

	return pd.DataFrame(
		rows,
		columns=[
			"Roofing Material Type",
			"Closest WARM/Hub Proxy",
			"Landfilling EF (MT CO2e/short ton)",
			"Recycling/Processing EF (MT CO2e/short ton)",
			"Notes",
		],
	)


def add_unit_converted_columns(
	roofing_df: pd.DataFrame, table9_df: pd.DataFrame, proxy_map: dict[str, str]
) -> pd.DataFrame:
	"""Add kg CO2e/lb columns derived from MT CO2e/short ton source factors."""
	material_lookup = _build_material_lookup(table9_df)

	landfilled_kg_per_lb: list[float | np.floating | None] = []
	recycled_kg_per_lb: list[float | np.floating | None] = []

	for roofing_material in roofing_df["Roofing Material Type"]:
		proxy = proxy_map[roofing_material]
		proxy_row = material_lookup.get(_normalize_text(proxy))

		if proxy_row is None:
			landfilled_kg_per_lb.append(np.nan)
			recycled_kg_per_lb.append(np.nan)
			continue

		landfilled_mt = proxy_row["landfilled_mt_per_ton"]
		recycled_mt = proxy_row["recycled_mt_per_ton"]
		landfilled_kg_per_lb.append(float(landfilled_mt) * 0.5 if pd.notna(landfilled_mt) else np.nan)
		recycled_kg_per_lb.append(float(recycled_mt) * 0.5 if pd.notna(recycled_mt) else np.nan)

	output_df = roofing_df.copy()
	output_df["Landfilling EF (kg CO2e/lb)"] = landfilled_kg_per_lb
	output_df["Recycling/Processing EF (kg CO2e/lb)"] = recycled_kg_per_lb
	return output_df


def parse_args() -> argparse.Namespace:
	"""Parse command line arguments for workbook and output locations."""
	script_dir = Path(__file__).resolve().parent
	repo_root = Path(__file__).resolve().parents[2]
	default_xlsx_path = script_dir / "ghg-emission-factors-hub-2025.xlsx"
	default_output_dir = repo_root / "Outputs"

	parser = argparse.ArgumentParser(
		description=(
			"Extract EPA GHG Hub Table 9 factors and compile roofing "
			"end-of-life emission factor lookup table."
		)
	)
	parser.add_argument(
		"--xlsx-path",
		type=Path,
		default=default_xlsx_path,
		help="Path to EPA GHG Emission Factors Hub workbook.",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=default_output_dir,
		help="Directory to write roofing_eol_emission_factors.csv.",
	)
	return parser.parse_args()


def main() -> None:
	"""Run Table 9 extraction, roofing proxy compilation, and output export."""
	args = parse_args()
	xlsx_path = args.xlsx_path.resolve()
	output_dir = args.output_dir.resolve()

	table9_df = load_table_9(xlsx_path)
	warn_on_unmatched_proxies(table9_df, ROOFING_TO_WARM_PROXY)

	roofing_df = build_roofing_ef_table(table9_df, ROOFING_TO_WARM_PROXY)
	roofing_df = add_unit_converted_columns(roofing_df, table9_df, ROOFING_TO_WARM_PROXY)

	print("\nCompiled Roofing EOL Emission Factors:\n")
	try:
		print(roofing_df.to_markdown(index=False))
	except ImportError:
		warnings.warn(
			"Package 'tabulate' is not installed; printing plain text table instead of markdown.",
			stacklevel=2,
		)
		print(roofing_df.to_string(index=False))

	output_dir.mkdir(parents=True, exist_ok=True)
	output_path = output_dir / "roofing_eol_emission_factors.csv"
	roofing_df.to_csv(output_path, index=False)
	print(f"\nWrote CSV: {output_path}")


if __name__ == "__main__":
	main()
