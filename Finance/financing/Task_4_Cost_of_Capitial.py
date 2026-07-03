"""
Task 4: Download and parse Damodaran global WACC data.

Note: Damodaran replaces this file in place each January. Re-running this
script next year will silently pull the new year's data unless we pin a
snapshot copy.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests


WACC_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/waccGlobal.xls"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_CSV = Path("/data/economics/cost_of_capital/damodaran_wacc_2026.csv")
FALLBACK_OUTPUT_CSV = REPO_ROOT / "data" / "economics" / "cost_of_capital" / "damodaran_wacc_2026.csv"


def _normalize_col_name(value: str) -> str:
	cleaned = value.strip().lower()
	cleaned = cleaned.replace("#", "num")
	cleaned = cleaned.replace("%", "pct")
	cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
	return re.sub(r"_+", "_", cleaned).strip("_")


def _pick_column(columns: list[str], patterns: list[str], required: bool = True) -> str | None:
	for pattern in patterns:
		regex = re.compile(pattern)
		for col in columns:
			if regex.search(col):
				return col
	if required:
		raise KeyError(f"Could not find a column matching any of: {patterns}")
	return None


def _download_bytes(url: str) -> bytes:
	response = requests.get(url, timeout=60)
	response.raise_for_status()
	return response.content


def _read_raw_table(content: bytes) -> pd.DataFrame:
	# The upstream file extension is .xls, but annual formatting can vary.
	try:
		raw = pd.read_excel(BytesIO(content), engine="openpyxl", header=None)
	except Exception:
		raw = pd.read_excel(BytesIO(content), header=None)

	header_row = None
	preview = raw.head(80)
	for row_idx in preview.index:
		row_values = [str(v).strip().lower() for v in preview.loc[row_idx].tolist()]
		has_industry = any(v in {"industry name", "industry"} for v in row_values)
		has_firms = any("number of firms" in v or v == "firms" for v in row_values)
		if has_industry and has_firms:
			header_row = int(row_idx)
			break

	if header_row is None:
		raise ValueError("Could not locate the table header row in Damodaran WACC workbook")

	headers = raw.iloc[header_row].fillna("").astype(str).str.strip()
	df = raw.iloc[header_row + 1 :].copy()
	df.columns = headers
	df = df.dropna(how="all")
	return df


def _extract_columns(raw_df: pd.DataFrame) -> pd.DataFrame:
	renamed = {col: _normalize_col_name(str(col)) for col in raw_df.columns}
	df = raw_df.rename(columns=renamed).copy()

	available = list(df.columns)

	industry_col = _pick_column(available, [r"^industry$", r"industry"])
	firms_col = _pick_column(available, [r"num.*firms", r"number.*firms", r"^firms$"])
	beta_col = _pick_column(available, [r"^beta$", r"levered.*beta", r"beta"])
	coe_col = _pick_column(available, [r"cost.*equity", r"^ke$", r"equity.*cost"])
	cod_col = _pick_column(available, [r"cost.*debt", r"^kd$", r"debt.*cost"])
	wacc_col = _pick_column(available, [r"^wacc$", r"cost.*capital", r"weighted.*average.*cost"])

	out = pd.DataFrame(
		{
			"industry": df[industry_col],
			"num_firms": pd.to_numeric(df[firms_col], errors="coerce"),
			"beta": pd.to_numeric(df[beta_col], errors="coerce"),
			"cost_of_equity": pd.to_numeric(df[coe_col], errors="coerce"),
			"cost_of_debt": pd.to_numeric(df[cod_col], errors="coerce"),
			"wacc": pd.to_numeric(df[wacc_col], errors="coerce"),
		}
	)

	out = out.dropna(subset=["industry"])
	out["industry"] = out["industry"].astype(str).str.strip()
	out = out[out["industry"] != ""]

	# Remove repeated header/footer rows if present.
	out = out[out["industry"].str.lower() != "industry"]
	return out.reset_index(drop=True)


def main() -> None:
	content = _download_bytes(WACC_URL)
	raw_df = _read_raw_table(content)
	final_df = _extract_columns(raw_df)

	output_path = OUTPUT_CSV
	try:
		output_path.parent.mkdir(parents=True, exist_ok=True)
		final_df.to_csv(output_path, index=False)
	except OSError:
		output_path = FALLBACK_OUTPUT_CSV
		output_path.parent.mkdir(parents=True, exist_ok=True)
		final_df.to_csv(output_path, index=False)
		print(f"Could not write to {OUTPUT_CSV}; wrote to {output_path.resolve()} instead.")

	print(final_df.head(10).to_string(index=False))


if __name__ == "__main__":
	main()
