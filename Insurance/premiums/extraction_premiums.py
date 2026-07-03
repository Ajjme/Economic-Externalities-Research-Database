from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber


PDF_PATH = Path(
    "/Users/andrewjohnson/Documents/GitHub/Economic-Externalities-Research-Database/Insurance/premiums/data/publication-hmr-zu-homeowners-report code.pdf"
)
OUTPUT_CSV = Path(
    "/Users/andrewjohnson/Documents/GitHub/Economic-Externalities-Research-Database/Insurance/premiums/data/naic_2022_avg_premium_clean.csv"
)

GEOGRAPHIES = [
    "Countrywide",
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "Dist. of Columbia",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
]

TABLE_4_RANGES = [
    "$149,999 and Under",
    "$150,000 to $199,999",
    "$200,000 to $224,999",
    "$225,000 to $249,999",
    "$250,000 to $274,999",
    "$275,000 to $299,999",
    "$300,000 to $324,999",
    "$325,000 to $349,999",
    "$350,000 to $399,999",
    "$400,000 to $449,999",
    "$450,000 to $499,999",
    "$500,000 to $599,999",
    "$600,000 to $699,999",
    "$700,000 to $999,999",
    "$1,000,000 and Over",
    "Total",
]

TABLE_5_RANGES = [
    "$9,999 and Under",
    "$10,000 to $14,999",
    "$15,000 to $19,999",
    "$20,000 to $24,999",
    "$25,000 to $29,999",
    "$30,000 to $34,999",
    "$35,000 to $39,999",
    "$40,000 to $49,999",
    "$50,000 to $59,999",
    "$60,000 to $69,999",
    "$70,000 to $79,999",
    "$80,000 to $99,999",
    "$100,000 to $124,999",
    "$125,000 to $199,999",
    "$200,000 and Over",
    "Total",
]

TABLE_SORT = {"Table 4": 0, "Table 5": 1}
STATE_SORT = {name: idx for idx, name in enumerate(GEOGRAPHIES)}

GEOGRAPHY_ALIASES = {
    "District of Columbia": "Dist. of Columbia",
}

NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")
INT_FROM_LABEL_RE = re.compile(r"\$?(\d[\d,]*)")


@dataclass
class PageParseResult:
    rows: List[Dict[str, object]]
    issues: List[Dict[str, object]]


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_segment(
    segment: str,
    *,
    int_value: bool,
) -> Tuple[Optional[float], bool, bool]:
    """Return (parsed_value, has_star, parse_failed)."""
    text = segment.strip()
    if not text:
        return None, False, True
    if "*" in text:
        return None, True, False

    match = NUMBER_RE.search(text)
    if not match:
        return None, False, True

    raw = match.group(0).replace("$", "").replace(",", "")
    value = float(raw)
    if int_value:
        return int(round(value)), False, False
    return value, False, False


def parse_value_token(token: str, *, int_value: bool) -> Optional[float]:
    if token == "*":
        return None
    raw = token.replace("$", "").replace(",", "")
    value = float(raw)
    if int_value:
        return int(round(value))
    return value


def parse_metric_values_from_tail(
    tail: str,
    policy_forms: List[str],
    *,
    int_value: bool,
) -> Tuple[Dict[str, Optional[float]], List[str]]:
    """Parse Exposure/Premium row values while skipping pct tokens."""
    tokens = re.findall(r"\*|\$?\d[\d,]*(?:\.\d+)?", tail)
    values: Dict[str, Optional[float]] = {}
    failures: List[str] = []
    idx = 0

    for form in policy_forms:
        if idx >= len(tokens):
            values[form] = None
            failures.append(form)
            continue

        value_token = tokens[idx]
        idx += 1
        values[form] = parse_value_token(value_token, int_value=int_value)

        # Ignore pct token (commonly decimal like 12.9 or 100.0) when present.
        if idx < len(tokens) and "." in tokens[idx]:
            idx += 1

    return values, failures


def parse_bounds(label: str) -> Tuple[Optional[int], Optional[int]]:
    if label == "Total":
        return None, None

    values = [int(x.replace(",", "")) for x in INT_FROM_LABEL_RE.findall(label)]
    if "and Under" in label and values:
        return None, values[0]
    if "and Over" in label and values:
        return values[0], None
    if " to " in label and len(values) >= 2:
        return values[0], values[1]
    return None, None


def detect_geography(lines: List[str]) -> Optional[str]:
    line_set = {normalize_spaces(line) for line in lines}
    for raw_name, normalized_name in GEOGRAPHY_ALIASES.items():
        if raw_name in line_set:
            return normalized_name

    for geography in GEOGRAPHIES:
        if geography in line_set:
            return geography
    return None


def build_column_spans(header_line: str, policy_forms: List[str]) -> Dict[str, Dict[str, int]]:
    value_starts: List[int] = []
    pct_starts: List[int] = []
    cursor = 0

    for form in policy_forms:
        value_idx = header_line.find(form, cursor)
        if value_idx < 0:
            raise ValueError(f"Policy form '{form}' not found in header line")

        pct_idx = header_line.find("%", value_idx + len(form))
        if pct_idx < 0:
            raise ValueError(f"Percent column for '{form}' not found in header line")

        value_starts.append(value_idx)
        pct_starts.append(pct_idx)
        cursor = pct_idx + 1

    spans: Dict[str, Dict[str, int]] = {}
    for i, form in enumerate(policy_forms):
        next_value_start = value_starts[i + 1] if i + 1 < len(policy_forms) else len(header_line)
        spans[form] = {
            "value_start": value_starts[i],
            "pct_start": pct_starts[i],
            "next_value_start": next_value_start,
        }
    return spans


def parse_page(
    page,
    page_num: int,
    source_table: str,
    policy_forms: List[str],
    expected_ranges: List[str],
) -> PageParseResult:
    text = page.extract_text(layout=True) or ""
    lines = [line.rstrip("\n") for line in text.splitlines() if line.strip()]
    rows: List[Dict[str, object]] = []
    issues: List[Dict[str, object]] = []

    geography = detect_geography(lines)
    if geography is None:
        issues.append(
            {
                "page": page_num,
                "state": "UNKNOWN",
                "source_table": source_table,
                "reason": "Geography not found",
            }
        )
        return PageParseResult(rows=rows, issues=issues)

    header_idx = None
    for i, line in enumerate(lines):
        compact = normalize_spaces(line)
        if "Range" in compact and all(form in compact for form in policy_forms):
            header_idx = i
            break

    if header_idx is None:
        issues.append(
            {
                "page": page_num,
                "state": geography,
                "source_table": source_table,
                "reason": "Header line not found",
            }
        )
        return PageParseResult(rows=rows, issues=issues)

    try:
        spans = build_column_spans(lines[header_idx], policy_forms)
    except ValueError as exc:
        issues.append(
            {
                "page": page_num,
                "state": geography,
                "source_table": source_table,
                "reason": str(exc),
            }
        )
        return PageParseResult(rows=rows, issues=issues)

    range_idx = 0
    metrics: Optional[Dict[str, Dict[str, Optional[float]]]] = None

    for line in lines[header_idx + 1 :]:
        compact = normalize_spaces(line)
        if "National Association of Insurance Commissioners" in compact:
            break

        m = re.search(r"\b(Exposure|Premium|Average)\b", line)
        if not m:
            continue

        metric = m.group(1)
        if range_idx >= len(expected_ranges):
            issues.append(
                {
                    "page": page_num,
                    "state": geography,
                    "source_table": source_table,
                    "reason": "More rows parsed than expected ranges",
                }
            )
            break

        if metric == "Exposure":
            metrics = {
                "exposure": {},
                "premium": {},
                "avg": {},
            }

        if metrics is None:
            issues.append(
                {
                    "page": page_num,
                    "state": geography,
                    "source_table": source_table,
                    "reason": f"{metric} encountered before Exposure",
                }
            )
            continue

        if metric == "Average":
            # Average rows do not include pct values. Parse by the full form span
            # (value start to next form's value start) to preserve alignment when
            # one form has a missing/blank average.
            for form in policy_forms:
                span = spans[form]
                avg_segment = line[span["value_start"] : span["next_value_start"]]
                value, _, failed = parse_segment(avg_segment, int_value=True)
                metrics["avg"][form] = None if failed else int(value)

        if metric == "Exposure":
            values, failures = parse_metric_values_from_tail(
                line[m.end() :], policy_forms, int_value=False
            )
            for form in policy_forms:
                metrics["exposure"][form] = values.get(form)
            for form in failures:
                issues.append(
                    {
                        "page": page_num,
                        "state": geography,
                        "source_table": source_table,
                        "reason": f"Exposure parse failed for {form}",
                    }
                )

        elif metric == "Premium":
            values, failures = parse_metric_values_from_tail(
                line[m.end() :], policy_forms, int_value=True
            )
            for form in policy_forms:
                parsed_value = values.get(form)
                metrics["premium"][form] = int(parsed_value) if parsed_value is not None else None
            for form in failures:
                issues.append(
                    {
                        "page": page_num,
                        "state": geography,
                        "source_table": source_table,
                        "reason": f"Premium parse failed for {form}",
                    }
                )

        if metric == "Average":
            insurance_range = expected_ranges[range_idx]
            min_val, max_val = parse_bounds(insurance_range)

            for form in policy_forms:
                rows.append(
                    {
                        "state": geography,
                        "policy_form": form,
                        "insurance_range": insurance_range,
                        "insurance_range_min": min_val,
                        "insurance_range_max": max_val,
                        "exposure_house_years": metrics["exposure"].get(form),
                        "premium_dollars": metrics["premium"].get(form),
                        "avg_premium_dollars": metrics["avg"].get(form),
                        "source_table": source_table,
                        "data_year": 2022,
                        "_page_num": page_num,
                    }
                )

            range_idx += 1
            metrics = None

    if range_idx != len(expected_ranges):
        issues.append(
            {
                "page": page_num,
                "state": geography,
                "source_table": source_table,
                "reason": f"Expected {len(expected_ranges)} ranges but parsed {range_idx}",
            }
        )

    return PageParseResult(rows=rows, issues=issues)


def sort_key(row: Dict[str, object]) -> Tuple[int, int, str, int, int]:
    min_val = row["insurance_range_min"]
    null_last = 1 if min_val is None else 0
    min_sort = min_val if min_val is not None else 0
    return (
        TABLE_SORT[row["source_table"]],
        STATE_SORT[row["state"]],
        str(row["policy_form"]),
        null_last,
        int(min_sort),
    )


def write_csv(rows: List[Dict[str, object]], output_path: Path) -> None:
    fieldnames = [
        "state",
        "policy_form",
        "insurance_range",
        "insurance_range_min",
        "insurance_range_max",
        "exposure_house_years",
        "premium_dollars",
        "avg_premium_dollars",
        "source_table",
        "data_year",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})


def collect_unexpected_nulls(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in rows:
        exposure_null = row["exposure_house_years"] is None
        premium_null = row["premium_dollars"] is None
        avg_null = row["avg_premium_dollars"] is None

        if avg_null and not (exposure_null or premium_null):
            out.append(
                {
                    "page": row["_page_num"],
                    "state": row["state"],
                    "table": row["source_table"],
                    "policy": row["policy_form"],
                    "insurance_range": row["insurance_range"],
                    "reason": "Average is null",
                }
            )

    return out


def main() -> None:
    all_rows: List[Dict[str, object]] = []
    parse_issues: List[Dict[str, object]] = []

    with pdfplumber.open(PDF_PATH) as pdf:
        # Table 4 page pairing: each geography occupies exactly 2 consecutive pages.
        # Page A in each pair has DW/HO-1/HO-2/HO-3; page B has HO-5/HO-8/Total.
        table4_start = 34
        for geo_idx in range(len(GEOGRAPHIES)):
            page_a = table4_start + (geo_idx * 2)
            page_b = page_a + 1

            a_result = parse_page(
                page=pdf.pages[page_a - 1],
                page_num=page_a,
                source_table="Table 4",
                policy_forms=["DW", "HO-1", "HO-2", "HO-3"],
                expected_ranges=TABLE_4_RANGES,
            )
            b_result = parse_page(
                page=pdf.pages[page_b - 1],
                page_num=page_b,
                source_table="Table 4",
                policy_forms=["HO-5", "HO-8", "Total"],
                expected_ranges=TABLE_4_RANGES,
            )

            all_rows.extend(a_result.rows)
            all_rows.extend(b_result.rows)
            parse_issues.extend(a_result.issues)
            parse_issues.extend(b_result.issues)

        table5_start = 139
        for geo_idx in range(len(GEOGRAPHIES)):
            page_num = table5_start + geo_idx
            result = parse_page(
                page=pdf.pages[page_num - 1],
                page_num=page_num,
                source_table="Table 5",
                policy_forms=["HO-4", "HO-6", "Total"],
                expected_ranges=TABLE_5_RANGES,
            )
            all_rows.extend(result.rows)
            parse_issues.extend(result.issues)

    all_rows.sort(key=sort_key)
    write_csv(all_rows, OUTPUT_CSV)

    expected_count = (52 * 7 * 16) + (52 * 3 * 16)
    unexpected_nulls = collect_unexpected_nulls(all_rows)

    spot_value = None
    for row in all_rows:
        if (
            row["source_table"] == "Table 4"
            and row["state"] == "Countrywide"
            and row["policy_form"] == "HO-3"
            and row["insurance_range"] == "Total"
        ):
            spot_value = row["avg_premium_dollars"]
            break

    print(f"Wrote CSV: {OUTPUT_CSV}")
    print(f"Total row count: {len(all_rows)} (expected {expected_count})")

    if parse_issues:
        print("\nRows/pages needing manual review (parse failures):")
        for item in parse_issues:
            print(
                f"- page={item['page']} state={item['state']} table={item['source_table']} reason={item['reason']}"
            )
    else:
        print("\nNo parse-failure issues detected.")

    if unexpected_nulls:
        print("\nRows needing manual review (unexpected nulls):")
        for item in unexpected_nulls:
            print(
                f"- page={item['page']} state={item['state']} table={item['table']} "
                f"policy={item['policy']} range={item['insurance_range']} reason={item['reason']}"
            )
    else:
        print("\nNo unexpected nulls detected.")

    ok = spot_value == 1569
    print(
        f"\nSpot-check Countrywide/Table 4/HO-3/Total avg_premium_dollars: {spot_value} "
        f"(expected 1569) -> {'PASS' if ok else 'FAIL'}"
    )


if __name__ == "__main__":
    main()
