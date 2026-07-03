# Rewiring America API - Raw Sample Capture

This folder contains unmodified raw JSON responses captured from the Rewiring America API on 2026-07-03.

Documentation source used:
- https://docs.rewiringamerica.org/introduction
- https://docs.rewiringamerica.org/api
- https://docs.rewiringamerica.org/api/incentives
- https://docs.rewiringamerica.org/api/finance
- https://docs.rewiringamerica.org/api/electrification-tools
- https://docs.rewiringamerica.org/api/residential-electrification-model

## Authentication Method

- Header: `Authorization: Bearer <API_KEY>`
- API key loaded from local `.env`:
  - `REWIRING_AMERICA_API_KEY=...`

## Available Endpoints

1. GET `/api/v1/calculator`
2. GET `/api/v1/utilities`
3. GET `/api/v1/incentives/programs`
4. GET `/api/v1/finance/loan-programs` (BETA)
5. POST `/api/v2/etools/health-impacts`
6. GET `/api/v1/rem/address`

## Required Parameters

### 1) GET /api/v1/calculator
- Required:
  - `owner_status` (`homeowner` | `renter`)
  - `household_income` (integer)
  - `household_size` (integer)
- Location requirement:
  - exactly one of `zip` or `address`
- Common optional filters:
  - `authority_types`, `utility`, `gas_utility`, `items`, `tax_filing`, `language`, `include_beta_states`

### 2) GET /api/v1/utilities
- Required location:
  - exactly one of `zip` or `address`
- Optional:
  - `language`

### 3) GET /api/v1/incentives/programs
- Required location:
  - exactly one of `zip` or `address`
- Common optional filters:
  - `authority_types`, `utility`, `gas_utility`, `language`

### 4) GET /api/v1/finance/loan-programs (BETA)
- Required location:
  - exactly one of `zip` or `address`
- Optional:
  - `language`

### 5) POST /api/v2/etools/health-impacts
- Required body fields:
  - `metrics` (string[])
  - `upgrade` (string[])
- Optional body fields:
  - `state_fips` (string[])
  - `county_fips` (string[])
  - `group_by` (string[])

### 6) GET /api/v1/rem/address
- Required:
  - `upgrade` (enum)
  - `address` (string)
  - `heating_fuel` (enum)
- Optional:
  - `water_heater_fuel`

## Response Schemas (Observed Top-Level)

### /api/v1/calculator
- Top-level keys observed:
  - `is_under_80_ami`
  - `is_under_150_ami`
  - `is_over_150_ami`
  - `authorities`
  - `coverage`
  - `location`
  - `data_partners`
  - `incentives`

### /api/v1/utilities
- Top-level keys observed:
  - `location`
  - `utilities`
  - optional `gas_utilities`
  - optional `gas_utility_affects_incentives`

### /api/v1/incentives/programs
- Top-level keys observed:
  - `authorities`
  - `coverage`
  - `location`
  - `programs`

### /api/v1/finance/loan-programs
- Response is an array of loan program objects.
- Common object keys documented include:
  - `id`, `loan_program_key`, `name`, `description`, `website_url`, `status`, `financial_authority`, `eligible_project_types`, `is_national`, `created_at`, `updated_at`, etc.

### /api/v2/etools/health-impacts
- Top-level keys observed:
  - `data` (array)

### /api/v1/rem/address
- Top-level keys observed:
  - `fuel_results`
  - `rates`
  - `emissions_factors`
  - `sampling_details`
  - `estimate_type`

## Pagination

- No pagination parameters (`page`, `limit`, `offset`, cursor tokens) were documented on these endpoints.
- No pagination response metadata was observed in these sample payloads.

## Rate Limits

- No explicit rate-limit values were found in the docs pages above.
- No rate-limit headers (for example `x-ratelimit-*`, `retry-after`) were present in sampled responses.
- Treat limits as undocumented unless Rewiring America provides additional guidance.

## Geographic Filters

- `zip` or `address` is the main geographic input pattern across incentives/utility/finance endpoints.
- Health impacts endpoint supports geographic slicing via `state_fips` and `county_fips` in request body.
- Utility and program endpoints can be further refined with utility IDs returned by `/api/v1/utilities`.

## Example API Calls

### Calculator
```bash
curl --get 'https://api.rewiringamerica.org/api/v1/calculator' \
  -H "Authorization: Bearer $REWIRING_AMERICA_API_KEY" \
  --data-urlencode 'owner_status=homeowner' \
  --data-urlencode 'household_income=90000' \
  --data-urlencode 'household_size=2' \
  --data-urlencode 'zip=20001'
```

### Utilities
```bash
curl --get 'https://api.rewiringamerica.org/api/v1/utilities' \
  -H "Authorization: Bearer $REWIRING_AMERICA_API_KEY" \
  --data-urlencode 'zip=20001'
```

### Incentive Programs
```bash
curl --get 'https://api.rewiringamerica.org/api/v1/incentives/programs' \
  -H "Authorization: Bearer $REWIRING_AMERICA_API_KEY" \
  --data-urlencode 'zip=20001'
```

### Finance Loan Programs
```bash
curl --get 'https://api.rewiringamerica.org/api/v1/finance/loan-programs' \
  -H "Authorization: Bearer $REWIRING_AMERICA_API_KEY" \
  --data-urlencode 'zip=20001'
```

### Health Impacts
```bash
curl 'https://api.rewiringamerica.org/api/v2/etools/health-impacts' \
  -H "Authorization: Bearer $REWIRING_AMERICA_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "metrics": ["fine_particulate_matter"],
    "upgrade": ["hvac__heat_pump_seer18_hspf10"],
    "state_fips": ["11"],
    "county_fips": [],
    "group_by": []
  }'
```

### Residential Electrification Model
```bash
curl --get 'https://api.rewiringamerica.org/api/v1/rem/address' \
  -H "Authorization: Bearer $REWIRING_AMERICA_API_KEY" \
  --data-urlencode 'upgrade=baseline' \
  --data-urlencode 'address=1 Dr Carlton B Goodlett Pl, San Francisco, CA 94102' \
  --data-urlencode 'heating_fuel=natural_gas'
```

## Raw Files Saved

- `api_v1_calculator.json`
- `api_v1_utilities.json`
- `api_v1_incentives_programs.json`
- `api_v1_finance_loan_programs.json`
- `api_v2_etools_health_impacts.json`
- `api_v1_rem_address.json`

These files are saved exactly as returned by the API (no normalization/transform applied).