"""Build raw and summary CRRC cool-roof datasets for CADENCE economics analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


CRRC_DOWNLOAD_URL = "https://portal.coolroofs.org/directory/roof/download"

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_OUTPUT_PATH = REPO_ROOT / "data" / "raw" / "cool_roofs_raw.csv"
SUMMARY_OUTPUT_PATH = REPO_ROOT / "data" / "processed" / "cool_roofs_summary.csv"

RAW_COLUMNS = [
    "Manufacturer",
    "Product Name",
    "Product Type",
    "Material",
    "Color",
    "Initial Solar Reflectance",
    "3-Year Solar Reflectance",
    "Initial Thermal Emittance",
    "3-Year Thermal Emittance",
    "Initial SRI",
    "3-Year SRI",
    "CRRC Product ID",
    "Date Collected",
]

METRIC_COLUMNS = [
    "Initial Solar Reflectance",
    "3-Year Solar Reflectance",
    "Initial Thermal Emittance",
    "3-Year Thermal Emittance",
    "Initial SRI",
    "3-Year SRI",
]


def download_crrc_directory_csv() -> str:
    response = requests.get(CRRC_DOWNLOAD_URL, timeout=60)
    response.raise_for_status()
    return response.text


def normalize_raw_products(csv_text: str, collected_date: str) -> pd.DataFrame:
    source = pd.read_csv(pd.io.common.StringIO(csv_text), dtype=str)

    # The export includes explanatory rows after the header. Keep only valid product IDs.
    product_rows = source[
        source["CRRC Product ID"].fillna("").str.match(r"^\d{4}-\d{4}", na=False)
    ].copy()

    product_rows["Product Name"] = (
        product_rows["Brand"].fillna("").str.strip()
        + " "
        + product_rows["Model"].fillna("").str.strip()
    ).str.strip()

    product_rows["Product Type"] = product_rows["Primary Product Type"].fillna("")
    product_rows["Material"] = product_rows["Product Class"].fillna("")
    product_rows["Date Collected"] = collected_date

    rename_map = {
        "3 Year Solar Reflectance": "3-Year Solar Reflectance",
        "3 Year Thermal Emittance": "3-Year Thermal Emittance",
        "3 Year SRI": "3-Year SRI",
    }
    product_rows = product_rows.rename(columns=rename_map)

    raw_df = product_rows[RAW_COLUMNS].copy()

    for col in METRIC_COLUMNS:
        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")

    return raw_df


def build_summary(raw_df: pd.DataFrame) -> pd.DataFrame:
    grouped = raw_df.groupby(["Product Type", "Color"], dropna=False)

    summary = grouped.size().rename("Number of products").to_frame()

    metric_stats = grouped[METRIC_COLUMNS].agg(["mean", "median", "std", "min", "max"])
    metric_stats.columns = [f"{metric} {stat}" for metric, stat in metric_stats.columns]

    summary = summary.join(metric_stats).reset_index()
    return summary


def write_outputs(raw_df: pd.DataFrame, summary_df: pd.DataFrame) -> None:
    RAW_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    raw_df.to_csv(RAW_OUTPUT_PATH, index=False)
    summary_df.to_csv(SUMMARY_OUTPUT_PATH, index=False)


def main() -> int:
    collected_date = datetime.now(timezone.utc).date().isoformat()
    csv_text = download_crrc_directory_csv()
    raw_df = normalize_raw_products(csv_text, collected_date)
    summary_df = build_summary(raw_df)
    write_outputs(raw_df, summary_df)

    print(f"Saved raw dataset to {RAW_OUTPUT_PATH} ({len(raw_df)} rows).")
    print(f"Saved summary dataset to {SUMMARY_OUTPUT_PATH} ({len(summary_df)} groups).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())