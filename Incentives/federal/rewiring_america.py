"""Deep-dive sampler for Rewiring America incentives programs by ZIP code.

This script tests multiple filter scenarios against:
- GET /api/v1/incentives/programs

It writes one flattened CSV row per returned program, with scenario metadata so you can
compare how filters (authority_types, utility, gas_utility, language) change results.

# this code gives us the programs available for a given zip code, and the authority types that are available for that zip code
# this can be a pop up for the user to do personal research for an area but I am not going to see if roofing is in this data

"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "rewiring"
OUTPUT_CSV = OUTPUT_DIR / "incentives_programs_deep_dive_sample.csv"
RAW_DIR = OUTPUT_DIR / "incentives_programs_deep_dive_raw"
BASE_URL = "https://api.rewiringamerica.org"
PROGRAMS_PATH = "/api/v1/incentives/programs"
UTILITIES_PATH = "/api/v1/utilities"

# Start with a small sample set. Replace or expand for broader runs.
TEST_ZIPS = [
    "20001",  # Washington, DC
    "30301",  # Atlanta, GA
    "94102",  # San Francisco, CA
]


@dataclass
class Scenario:
    name: str
    language: str | None = None
    authority_types: list[str] | None = None
    utility: str | None = None
    gas_utility: str | None = None


def build_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def get_json(
    session: requests.Session,
    path: str,
    headers: dict[str, str],
    params: dict[str, Any],
    timeout: int = 60,
) -> tuple[int, dict[str, Any] | list[Any] | str]:
    response = session.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=timeout)
    status = response.status_code

    try:
        return status, response.json()
    except ValueError:
        return status, response.text


def fetch_utilities_for_zip(
    session: requests.Session, headers: dict[str, str], zip_code: str
) -> tuple[list[str], list[str], dict[str, Any] | list[Any] | str, int]:
    status, payload = get_json(
        session=session,
        path=UTILITIES_PATH,
        headers=headers,
        params={"zip": zip_code},
    )

    utility_ids: list[str] = []
    gas_utility_ids: list[str] = []

    if isinstance(payload, dict):
        utilities = payload.get("utilities", {}) or {}
        gas_utilities = payload.get("gas_utilities", {}) or {}
        utility_ids = sorted(str(k) for k in utilities.keys())
        gas_utility_ids = sorted(str(k) for k in gas_utilities.keys())

    return utility_ids, gas_utility_ids, payload, status


def build_scenarios(zip_code: str, utility_ids: list[str], gas_utility_ids: list[str]) -> list[Scenario]:
    scenarios: list[Scenario] = [
        Scenario(name="base_en", language="en"),
        Scenario(name="base_es", language="es"),
        Scenario(name="authority_federal", authority_types=["federal"]),
        Scenario(name="authority_state", authority_types=["state"]),
        Scenario(name="authority_county", authority_types=["county"]),
        Scenario(name="authority_city", authority_types=["city"]),
    ]

    if utility_ids:
        scenarios.append(
            Scenario(
                name="authority_utility_first_id",
                authority_types=["utility"],
                utility=utility_ids[0],
            )
        )

    if gas_utility_ids:
        scenarios.append(
            Scenario(
                name="authority_gas_utility_first_id",
                authority_types=["gas_utility"],
                gas_utility=gas_utility_ids[0],
            )
        )

    # Useful baseline for locations without gas service.
    scenarios.append(
        Scenario(
            name="authority_gas_utility_none",
            authority_types=["gas_utility"],
            gas_utility="none",
        )
    )

    # Tag scenario names with ZIP for easier raw file tracing.
    for idx, scenario in enumerate(scenarios):
        scenarios[idx] = Scenario(
            name=f"{zip_code}__{scenario.name}",
            language=scenario.language,
            authority_types=scenario.authority_types,
            utility=scenario.utility,
            gas_utility=scenario.gas_utility,
        )

    return scenarios


def scenario_to_params(zip_code: str, scenario: Scenario) -> dict[str, Any]:
    params: dict[str, Any] = {"zip": zip_code}

    if scenario.language:
        params["language"] = scenario.language
    if scenario.authority_types:
        params["authority_types"] = ",".join(scenario.authority_types)
    if scenario.utility:
        params["utility"] = scenario.utility
    if scenario.gas_utility:
        params["gas_utility"] = scenario.gas_utility

    return params


def write_raw_json(raw_path: Path, payload: dict[str, Any] | list[Any] | str) -> None:
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(payload, str):
        raw_path.write_text(payload, encoding="utf-8")
        return

    raw_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def flatten_program_rows(
    *,
    zip_code: str,
    scenario: Scenario,
    status_code: int,
    payload: dict[str, Any] | list[Any] | str,
    raw_file: Path,
) -> list[dict[str, Any]]:
    base = {
        "zip": zip_code,
        "scenario_name": scenario.name,
        "http_status": status_code,
        "language": scenario.language or "",
        "authority_types": ",".join(scenario.authority_types or []),
        "utility_filter": scenario.utility or "",
        "gas_utility_filter": scenario.gas_utility or "",
        "raw_json_file": str(raw_file.relative_to(REPO_ROOT)),
    }

    if not isinstance(payload, dict):
        row = dict(base)
        row.update(
            {
                "response_error_type": "non_json_or_non_object",
                "response_error_message": str(payload)[:400],
                "location_state": "",
                "location_city": "",
                "location_county_fips": "",
                "coverage_state": "",
                "program_key": "",
                "program_name": "",
                "program_url": "",
                "program_authority_type": "",
                "program_authority_id": "",
                "authority_name": "",
                "program_count_in_response": 0,
            }
        )
        return [row]

    if "detail" in payload:
        detail = payload.get("detail")
        row = dict(base)
        row.update(
            {
                "response_error_type": detail.get("type", "api_error")
                if isinstance(detail, dict)
                else "api_error",
                "response_error_message": detail.get("msg", "")
                if isinstance(detail, dict)
                else str(detail),
                "location_state": "",
                "location_city": "",
                "location_county_fips": "",
                "coverage_state": "",
                "program_key": "",
                "program_name": "",
                "program_url": "",
                "program_authority_type": "",
                "program_authority_id": "",
                "authority_name": "",
                "program_count_in_response": 0,
            }
        )
        return [row]

    location = payload.get("location", {}) or {}
    coverage = payload.get("coverage", {}) or {}
    authorities = payload.get("authorities", {}) or {}
    programs = payload.get("programs", {}) or {}

    if not programs:
        row = dict(base)
        row.update(
            {
                "response_error_type": "",
                "response_error_message": "",
                "location_state": location.get("state", ""),
                "location_city": location.get("city", ""),
                "location_county_fips": location.get("county_fips", ""),
                "coverage_state": coverage.get("state", ""),
                "program_key": "",
                "program_name": "",
                "program_url": "",
                "program_authority_type": "",
                "program_authority_id": "",
                "authority_name": "",
                "program_count_in_response": 0,
            }
        )
        return [row]

    rows: list[dict[str, Any]] = []
    for program_key, program in programs.items():
        authority_id = str(program.get("authority", ""))
        authority_obj = authorities.get(authority_id, {}) if isinstance(authorities, dict) else {}

        row = dict(base)
        row.update(
            {
                "response_error_type": "",
                "response_error_message": "",
                "location_state": location.get("state", ""),
                "location_city": location.get("city", ""),
                "location_county_fips": location.get("county_fips", ""),
                "coverage_state": coverage.get("state", ""),
                "program_key": program_key,
                "program_name": program.get("name", ""),
                "program_url": program.get("url", ""),
                "program_authority_type": program.get("authority_type", ""),
                "program_authority_id": authority_id,
                "authority_name": authority_obj.get("name", "")
                if isinstance(authority_obj, dict)
                else "",
                "program_count_in_response": len(programs),
            }
        )
        rows.append(row)

    return rows


def main() -> int:
    load_dotenv(Path(__file__).with_name(".env"))
    load_dotenv()

    api_key = os.getenv("REWIRING_AMERICA_API_KEY")
    if not api_key:
        print("REWIRING_AMERICA_API_KEY is missing. Add it to Incentives/federal/.env")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    headers = build_headers(api_key)
    session = requests.Session()

    all_rows: list[dict[str, Any]] = []

    for zip_code in TEST_ZIPS:
        utility_ids, gas_utility_ids, utilities_payload, utilities_status = fetch_utilities_for_zip(
            session=session,
            headers=headers,
            zip_code=zip_code,
        )

        utilities_raw_path = RAW_DIR / f"{zip_code}__utilities_lookup.json"
        write_raw_json(utilities_raw_path, utilities_payload)
        print(
            f"[{zip_code}] utilities_lookup: status={utilities_status}, "
            f"electric_ids={len(utility_ids)}, gas_ids={len(gas_utility_ids)}"
        )

        scenarios = build_scenarios(
            zip_code=zip_code,
            utility_ids=utility_ids,
            gas_utility_ids=gas_utility_ids,
        )

        for scenario in scenarios:
            params = scenario_to_params(zip_code, scenario)
            status_code, payload = get_json(
                session=session,
                path=PROGRAMS_PATH,
                headers=headers,
                params=params,
            )

            raw_path = RAW_DIR / f"{scenario.name}.json"
            write_raw_json(raw_path, payload)

            rows = flatten_program_rows(
                zip_code=zip_code,
                scenario=scenario,
                status_code=status_code,
                payload=payload,
                raw_file=raw_path,
            )
            all_rows.extend(rows)

            print(
                f"[{zip_code}] {scenario.name}: status={status_code}, rows_added={len(rows)}"
            )

    fieldnames = [
        "zip",
        "scenario_name",
        "http_status",
        "language",
        "authority_types",
        "utility_filter",
        "gas_utility_filter",
        "location_state",
        "location_city",
        "location_county_fips",
        "coverage_state",
        "program_key",
        "program_name",
        "program_url",
        "program_authority_type",
        "program_authority_id",
        "authority_name",
        "program_count_in_response",
        "response_error_type",
        "response_error_message",
        "raw_json_file",
    ]

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {OUTPUT_CSV}")
    print(f"Saved raw scenario payloads under {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
