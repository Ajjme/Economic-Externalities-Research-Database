# Economic Externalities Research Database

National-scale economic data framework for CADENCE. This repository collects and standardizes finance, carbon, community, disposal, energy, insurance, and incentive datasets for downstream benefit-cost modeling (NPV, BCR, payback, and scenario analysis).

This README documents what is actually implemented in code today (as of 2026-07-11), the format of each produced data product, and suggested use of each metric.

## 1. Implementation Status (Code-Verified)

### Implemented pipelines

1. Finance inflation pull from FRED + CBO:
        - Script: Finance/inflation/Task_1_Inflation.py
        - Outputs: data/economics/inflation/fred_inflation.csv, data/economics/inflation/cbo_longterm_raw.csv

2. Finance mortgage rate pull from FRED:
        - Script: Finance/financing/Task_3_Mortgage_Rates.py
        - Output: data/economics/mortgage_rates/fred_mortgage_rates.csv

3. Finance cost of capital parser (Damodaran WACC):
        - Script: Finance/financing/Task_4_Cost_of_Capitial.py
        - Output: data/economics/cost_of_capital/damodaran_wacc_2026.csv

4. Energy thermal product extraction (CRRC cool roofs):
        - Script: Energy/thermal/Task_5_Cool_Roofs.py
        - Outputs: data/raw/cool_roofs_raw.csv, data/processed/cool_roofs_summary.csv

5. Failure costs disposal parser (EREF tipping fees):
        - Script: Failure Costs/disposal/Task_7_Disposal.py
        - Output: Failure Costs/disposal/EREF_2024_Tipping_Fees_Parsed.csv

6. Community GDP county pipeline (BEA):
        - Scripts: Community/GDP/Task_9_GDP.py, Community/GDP/bea_county_gdp.py
        - Outputs: Community/GDP/reference/county_gdp.csv, Community/GDP/reference/bea_line_codes.json, Community/GDP/reference/county_gdp_data_quality_notes.md

7. Community property values pipeline (ACS5):
        - Script: Community/property values/Task_10_Property_values.py
        - Output: data/processed/cadence_property_values_acs5.csv
        - Note: tract pulls may be skipped when Census wildcard tract queries fail; county-level output still exports.

8. Carbon SCC extraction (EPA Table A.5.1):
        - Script: Carbon/SCC/Task_11_SCGHG.py
        - Output: Carbon/SCC/table_a5_1_scghg_unrounded_2020_2080.csv

9. Carbon SCC extraction (NY DEC combined A1-A12):
        - Script: Carbon/SCC/Task_12_SCGHG_NY.py
        - Outputs: Outputs/scghg_ny_combined.csv, Outputs/scghg_ny_combined.parquet

10. Carbon disposal emissions factors (EPA Hub Table 9 + roofing proxy map):
         - Script: Carbon/emissions_disposal/Task_13_EPA_WARM_EF.py
         - Output: Outputs/roofing_eol_emission_factors.csv

11. Community employment anchors (BLS QCEW):
         - Script: Community/employment/Task_14_employment_metrics.py
         - Output: Outputs/bls_qcew_housing_roofing_anchors.csv

12. Insurance premium extraction (NAIC PDF parser):
         - Script: Insurance/premiums/extraction_premiums.py
         - Output: Insurance/premiums/data/naic_2022_avg_premium_clean.csv

13. Incentives API deep-dive sample (Rewiring America):
         - Script: Incentives/federal/rewiring_america.py
         - Outputs: data/raw/rewiring/incentives_programs_deep_dive_sample.csv and scenario JSON files under data/raw/rewiring/incentives_programs_deep_dive_raw/

### Not implemented or placeholder scripts

1. Finance/discount/Task_2_Discount_Rates.py is currently empty.
2. Failure Costs/disposal/Task_8_weight_converstion.py is currently empty.
3. Incentives/federal/DSIRE.py currently contains planning notes only (no executable pipeline).

## 2. Final Data Products: Formats + Metric Usage

This section lists each script-generated final product and how to use each metric.

### Finance

#### data/economics/inflation/fred_inflation.csv
Format (CSV columns):
- date: observation date.
- series_id: FRED series key (CPIAUCSL, CPILFESL, PCEPI).
- value: inflation index value from FRED.

Suggested use:
- Use series_id to choose your inflation basis (headline CPI, core CPI, or PCE).
- Use date + value to build escalation factors for nominal cost projections.

#### data/economics/inflation/cbo_longterm_raw.csv
Format (CSV columns):
- date
- variable
- value

Suggested use:
- Use variable to select long-term macro assumptions (as provided in the CBO file).
- Use value trajectories for long-horizon scenario assumptions and sensitivity runs.

#### data/economics/mortgage_rates/fred_mortgage_rates.csv
Format (CSV columns):
- date
- loan_type (30-year fixed, 15-year fixed)
- interest_rate (percent)

Suggested use:
- Use loan_type to map financing assumptions to project tenure.
- Use interest_rate as baseline debt cost in homeowner financing scenarios.

#### data/economics/cost_of_capital/damodaran_wacc_2026.csv
Format (CSV columns):
- industry
- num_firms
- beta
- cost_of_equity
- cost_of_debt
- wacc

Suggested use:
- wacc: default discount/hurdle candidate for private-sector NPV.
- beta: risk proxy for scenario-dependent equity return adjustments.
- cost_of_equity and cost_of_debt: build blended capital structures for sensitivity analysis.
- num_firms: confidence context (higher counts typically mean more stable industry estimate).

#### data/economics/discount_rates/omb_a94_2026.csv
Format (CSV columns):
- maturity_years
- nominal_rate
- real_rate
- budget_year

Suggested use:
- real_rate: primary federal-style real discounting for social analyses.
- nominal_rate: use when cash flows are kept in nominal dollars.
- maturity_years: match rate horizon to project analysis period.

#### data/economics/discount_rates/treasury_avg_rates.csv
Format (CSV columns):
- record_date
- security_type_desc
- security_desc
- avg_interest_rate_amt
- src_line_nbr
- record_fiscal_year
- record_fiscal_quarter
- record_calendar_year
- record_calendar_quarter
- record_calendar_month
- record_calendar_day

Suggested use:
- avg_interest_rate_amt: market anchor for low-risk discounting and scenario calibration.
- security_type_desc/security_desc: choose term structure point relevant to your analysis horizon.

### Energy / Thermal

#### data/raw/cool_roofs_raw.csv
Format (CSV columns):
- Manufacturer
- Product Name
- Product Type
- Material
- Color
- Initial Solar Reflectance
- 3-Year Solar Reflectance
- Initial Thermal Emittance
- 3-Year Thermal Emittance
- Initial SRI
- 3-Year SRI
- CRRC Product ID
- Date Collected

Suggested use:
- Initial vs 3-Year metrics: quantify expected performance degradation.
- Solar Reflectance and Thermal Emittance: convert to cooling-load assumptions in building-energy models.
- SRI: single-index screening metric for candidate material comparison.

#### data/processed/cool_roofs_summary.csv
Format (CSV columns):
- Product Type
- Color
- Number of products
- For each metric (Initial/3-Year Solar Reflectance, Initial/3-Year Thermal Emittance, Initial/3-Year SRI): mean, median, std, min, max

Suggested use:
- Number of products: indicates market depth/availability by type-color group.
- mean/median: baseline expected performance values.
- std: uncertainty width for Monte Carlo or high/low scenario envelopes.
- min/max: practical lower/upper bounds for stress tests.

### Failure Costs / Disposal

#### Failure Costs/disposal/EREF_2024_Tipping_Fees_Parsed.csv
Format (CSV columns):
- Region/State
- Average tipping Fee
- Standard Deviation

Suggested use:
- Average tipping Fee: baseline disposal unit-cost assumption.
- Standard Deviation: dispersion input for regional uncertainty and sensitivity testing.

### Community

#### Community/GDP/reference/county_gdp.csv
Format (CSV columns):
- county_fips
- county_name
- state_abbr
- year
- gdp_current_dollars
- gdp_real_chained_dollars
- gdp_growth_pct
- population
- gdp_per_capita
- gdp_per_capita_is_estimated
- manufacturing_share
- construction_share
- government_share
- service_sector_share

Suggested use:
- gdp_current_dollars: nominal exposure base for dollar-denominated impact scaling.
- gdp_real_chained_dollars: inflation-adjusted economic size for temporal comparability.
- gdp_growth_pct: macro trend indicator for forward demand/recovery assumptions.
- population + gdp_per_capita: normalize impacts to per-capita burden or benefit.
- sector shares: economic structure weights to tailor regional vulnerability/rebound assumptions.

#### data/processed/cadence_property_values_acs5.csv
Format (CSV columns):
- year
- geography_level
- fips
- state_fips
- county_fips
- tract_fips
- state
- county
- tract
- area_name
- median_home_value
- total_housing_units
- owner_occupied_units
- owner_occupancy_rate

Suggested use:
- median_home_value: asset-value baseline for avoided-loss framing.
- total_housing_units: stock exposure scalar.
- owner_occupied_units and owner_occupancy_rate: proxy for adoption propensity and resilience co-benefit distribution.
- geography_level + FIPS fields: harmonize joins to county/tract hazard, income, or policy layers.

#### Outputs/bls_qcew_housing_roofing_anchors.csv
Format (CSV columns):
- area_fips
- own_code
- industry_code
- year
- qtr
- qtrly_estabs_count
- month3_emplvl
- total_qtrly_wages

Suggested use:
- qtrly_estabs_count: local business capacity proxy.
- month3_emplvl: labor availability anchor for scaling retrofit throughput and recovery timelines.
- total_qtrly_wages: payroll intensity proxy for local economic multipliers.
- industry_code: compare broad residential construction vs roofing-specific labor anchors.

### Carbon

#### Carbon/SCC/table_a5_1_scghg_unrounded_2020_2080.csv
Format (CSV columns):
- emission_year
- scc_co2_2.5pct
- scc_co2_2.0pct
- scc_co2_1.5pct
- scc_ch4_2.5pct
- scc_ch4_2.0pct
- scc_ch4_1.5pct
- scc_n2o_2.5pct
- scc_n2o_2.0pct
- scc_n2o_1.5pct

Suggested use:
- Choose gas-specific SCC column by emitted pollutant.
- Choose discount-rate column (2.5/2.0/1.5) by social discounting convention in the scenario.
- Multiply SCC by avoided or added emissions to monetize carbon externalities.

#### Outputs/scghg_ny_combined.csv
Format (CSV columns):
- gas
- gas_name
- year
- discount_rate
- sc_value
- unit
- source_table
- source_document

Suggested use:
- sc_value: monetary externality value per metric ton for NY policy framing.
- gas + year + discount_rate: explicit scenario key for reproducible monetization assumptions.

#### Outputs/scghg_ny_combined.parquet
Format:
- Parquet version of Outputs/scghg_ny_combined.csv with the same logical fields.

Suggested use:
- Prefer for analytics workflows that need typed columns and faster reads at scale.

#### Outputs/roofing_eol_emission_factors.csv
Format (CSV columns):
- Roofing Material Type
- Closest WARM/Hub Proxy
- Landfilling EF (MT CO2e/short ton)
- Recycling/Processing EF (MT CO2e/short ton)
- Notes
- Landfilling EF (kg CO2e/lb)
- Recycling/Processing EF (kg CO2e/lb)

Suggested use:
- Landfilling/Recycling EFs: direct factors for end-of-life emissions accounting in roofing scenarios.
- MT CO2e/short ton columns: best for tonnage-based waste models.
- kg CO2e/lb columns: best for models where debris mass is tracked in pounds.
- Notes: required interpretation context for proxy mappings and missing-factor fallback assumptions.

### Insurance

#### Insurance/premiums/data/naic_2022_avg_premium_clean.csv
Format (CSV columns):
- state
- policy_form
- insurance_range
- insurance_range_min
- insurance_range_max
- exposure_house_years
- premium_dollars
- avg_premium_dollars
- source_table
- data_year

Suggested use:
- avg_premium_dollars: normalized premium benchmark by policy form and insured-value bin.
- exposure_house_years: credibility/weighting signal for observed premium values.
- premium_dollars: aggregate premium mass for scaling market-level impacts.
- insurance_range bounds: interpolation support when mapping to modeled property values.

### Incentives

#### data/raw/rewiring/incentives_programs_deep_dive_sample.csv
Format (CSV columns):
- zip
- scenario_name
- http_status
- language
- authority_types
- utility_filter
- gas_utility_filter
- location_state
- location_city
- location_county_fips
- coverage_state
- program_key
- program_name
- program_url
- program_authority_type
- program_authority_id
- authority_name
- program_count_in_response
- response_error_type
- response_error_message
- raw_json_file

Suggested use:
- program_count_in_response: quick density signal for incentive availability under each filter scenario.
- authority/program fields: metadata for manual curation of candidate incentive programs.
- http_status and response_error_*: QA diagnostics for API reliability and filter logic.

## 3. Operational Notes

1. Environment/API keys used by implemented scripts:
        - FRED_API_KEY for Task_1_Inflation.py and Task_3_Mortgage_Rates.py
        - BEA_API_KEY for Community/GDP/bea_county_gdp.py
        - CENSUS_API_KEY (optional but recommended) for Task_10_Property_values.py
        - REWIRING_AMERICA_API_KEY for Incentives/federal/rewiring_america.py

2. Output location behavior:
        - Some finance scripts first attempt /data/... and fall back to repository-local data/... when system-level /data is unavailable.

3. Table extraction dependencies:
        - pdfplumber is required for PDF table parsers.
        - pyarrow is required for NY SCGHG parquet export.
        - tabulate is optional for markdown console display in Task_13_EPA_WARM_EF.py.