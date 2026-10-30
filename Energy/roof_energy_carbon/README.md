# Roof Energy Savings & Avoided Carbon (CADENCE)

> Status: **Planned / in development.** This module turns a roof replacement into annual benefit streams for the CADENCE Economics Module:
> 1. **Net energy savings:** cooling electricity saved minus the winter heating penalty, in kWh/MMBtu and in utility-bill dollars.
> 2. **Avoided greenhouse gas emissions:** in tonnes and in SCGHG-monetized dollars.
>
> This README is also the implementation plan. See [Implementation plan](#implementation-plan) and [Decisions log](#decisions-log).

## Current state of the data
- `Energy/thermal/` has the CRRC product pipeline (`Task_5_Cool_Roofs.py`) and a conceptual design doc (`energy_module_planning.md`). No savings or carbon code exists yet.
- `data/raw/cool_roofs_raw.csv` has 3,193 CRRC products. 544 of them have no 3-year (aged) reflectance or emittance values.
- `data/processed/cool_roofs_summary.csv` has 247 groups, many with only one product, because multi-color strings like "Tan, Brown, Multicolor" are kept as-is.
- `Task_5` drops fields this module needs: **Slope** (Steep 926 / Both 2,000 / Low 303), **Product Market**, **Secondary Product Type**, and **Color Family**. It also labels CRRC's `Product Class` as `Material`, but `Product Class` is a rating category, not a material.
- Reusable assets in the repo:
  - EPA GHG Emission Factors Hub tables (fuel combustion factors, eGRID2023 subregion factors, GWPs).
  - EPA 2023 SCGHG (`Carbon/SCC/table_a5_1_scghg_unrounded_2020_2080.csv`) and NY DEC SCGHG (`Outputs/scghg_ny_combined.csv`).
  - FRED CPI for dollar-year conversion.
  - The ACS API pattern from `Task_10`.

## Design decisions
| Topic | Decision |
|---|---|
| Building scope | Residential, steep-slope (CRRC `Slope` ∈ {Steep, Both}) |
| Geography | County. Each county maps to an IECC climate zone, a Cambium GEA region, and an eGRID subregion |
| Energy method (V1) | Coefficients from DOE/ORNL Roof Savings Calculator (RSC) runs: kWh of cooling saved and heating penalty per m² of roof per unit ΔSR, by climate zone |
| Heating penalty | Included. Fuel blend comes from the county ACS B25040 heating-fuel mix |
| Grid emission factor | NREL Cambium long-run marginal (LRMER) is the primary basis. eGRID2023 subregion average is the fallback and sensitivity case |
| Gases | CO2, CH4, and N2O tracked separately. CO2e uses AR5 GWPs |
| Monetization | EPA 2023 SCGHG by default, NY DEC as an option. Social-cost values are applied per gas and reported at all three EPA discount rates (1.5%, 2.0%, 2.5%), in **2026 dollars** |
| Utility-bill savings | Computed in this module using EIA state residential electricity and heating-fuel prices, in 2026 dollars |
| Cambium scenario | Mid-case only |
| Roof life | 20 years by default (parameter) |
| Roof archetypes | Product Type × primary (first-listed) color, steep-slope only |
| Missing aged values | CA Title 24 imputation, flagged |
| Baseline roof | Generic dark asphalt shingle, overridable per property |
| Time dynamics | Annual stream over the roof's life, with grid decarbonization and reflectance aging |
| Deliverables | Precomputed per-ft² lookup CSV for all U.S. counties + reusable Python function |

## Scope (V1)
- **Buildings:** residential, steep-slope roofs only (CRRC `Slope` = Steep or Both Low and Steep).
- **Geography:** U.S. counties (FIPS), crosswalked to IECC climate zone, NREL Cambium GEA region, and EPA eGRID subregion.
- **What changes:** only the roof surface (solar reflectance and thermal emittance). Insulation, HVAC, setpoints, occupancy, and geometry are held constant. See `../thermal/energy_module_planning.md`.

## Method

### 1. Roof archetypes
Source: CRRC Rated Products Directory (`Energy/thermal/Task_5_Cool_Roofs.py`).
- Products are filtered to steep-slope and grouped by **Product Type × primary color**, where primary color is the first color listed.
- Missing 3-year values are imputed with the CA Title 24 aging relation:
  `SR_aged = 0.2 + 0.7 · (SR_initial − 0.2)`, `TE_aged = TE_initial`. Imputed rows are flagged.
- **Baseline (existing) roof default:** generic dark asphalt shingle, SR ≈ 0.09, TE ≈ 0.90. Can be overridden per property.

### 2. Energy savings
Coefficients come from DOE/ORNL Roof Savings Calculator runs: one representative steep-slope house per IECC climate zone (and representative city), with a dark-shingle baseline compared against higher-SR roofs. The results are fit as energy change per m² of roof per unit change in solar reflectance (ΔSR). This follows the LBNL / Levinson & Akbari form:

```
ΔSR_t        = SR_new(t) − SR_baseline(t)
ΔE_cool,t    = k_cool(county) · ΔSR_t · A_roof · f_attic          [kWh electricity]
ΔH_t         = k_heat(county) · ΔSR_t · A_roof · f_attic          [heat demand added]
```

The heating penalty is split across fuels using the county's ACS B25040 home-heating-fuel shares and system efficiencies. Gas, propane, and oil use AFUE. Electric heat uses a blended resistance / heat-pump COP.

```
ΔkWh_net,t = ΔE_cool,t − ΔkWh_electric_heat,t
ΔFuel_j,t  = share_j · ΔH_t / η_j                                [MMBtu, by fuel j]
```

Reflectance aging: linear from initial to 3-year values over years 0–3. After year 3, the 3-year value is held by default; an optional decline rate is available.

### 3. Avoided emissions
Each gas g (CO2, CH4, N2O) is computed separately:

```
ΔM_g,t = ΔkWh_net,t · EF_grid,g(region, t) − Σ_j ΔFuel_j,t · EF_fuel,g,j
CO2e_t = Σ_g ΔM_g,t · GWP_g        (AR5: CO2 = 1, CH4 = 28, N2O = 265)
```

- **Primary grid factor:** NREL Cambium **long-run marginal emission rate (LRMER)**, Mid-case, by GEA region and year. Between published years, values are interpolated linearly; after the last published year they are held flat. LRMER is measured at the end use, so no extra T&D loss is added.
- **Fallback / sensitivity:** EPA eGRID2023 subregion output emission rates (GHG Emission Factors Hub Table 6) plus the eGRID grid-loss factor.
- **Fuel combustion factors:** EPA GHG Emission Factors Hub Table 1.

### 4. Monetization
```
Value_t = Σ_g ΔM_g,t · SC_g(year t, discount rate)
```
- Default: **EPA 2023 SCGHG** (`Carbon/SCC/table_a5_1_scghg_unrounded_2020_2080.csv`). Optional: **NY DEC** (`Outputs/scghg_ny_combined.csv`).
- Values are gas-specific (SC-CO2, SC-CH4, SC-N2O). They are converted to **2026 dollars** with FRED CPI.
- All three EPA near-term discount rates (1.5%, 2.0%, 2.5%) are reported as separate columns. The Economics Module picks the one that matches its own discount rate.
- Streams are reported **undiscounted**. Discounting happens in the Economics Module.

### 5. Utility-bill savings
```
Bill_t = ΔkWh_net,t · P_elec(state) − Σ_j ΔFuel_j,t · P_j(state)
```
- Prices are EIA state average residential prices: electricity, natural gas, propane, and heating oil. They are converted to 2026 dollars and held constant in real terms by default.
- Like the carbon value, this can be negative in heating-dominated counties.

## Inputs
| Input | Source | File |
|---|---|---|
| Roof optical properties | CRRC directory | `data/raw/cool_roofs_raw.csv` |
| Roof archetypes | derived | `data/processed/roof_archetypes_steep.csv` |
| Energy coefficients (k_cool, k_heat, f_attic) | DOE/ORNL Roof Savings Calculator runs | `data/processed/roof_energy_coefficients.csv` |
| County crosswalk | IECC / Cambium / eGRID | `data/processed/county_energy_crosswalk.csv` |
| Heating fuel mix | ACS 5-yr B25040 | `data/processed/county_heating_fuel_mix.csv` |
| Grid emission factors | NREL Cambium, EPA eGRID | `data/processed/grid_emission_factors.csv` |
| Fuel emission factors + GWPs | EPA GHG Hub Tables 1, 11 | `data/processed/fuel_emission_factors.csv` |
| SCGHG | EPA 2023, NY DEC | existing Carbon outputs |
| Retail energy prices | EIA state residential prices | `data/processed/state_energy_prices.csv` |

## Outputs
1. **Calculator:** `compute_roof_energy_carbon(county_fips, new_archetype, roof_area_ft2, baseline=DEFAULT, start_year, life_years=20, ef_basis="cambium_lrmer", scghg="epa_2023", dollar_year=2026)` returns one row per year with:
   `year, delta_sr, kwh_cool_saved, kwh_heat_penalty, kwh_net_saved, fuel_penalty_mmbtu_<fuel>, co2_t, ch4_t, n2o_t, co2e_t, scghg_usd_1.5pct, scghg_usd_2.0pct, scghg_usd_2.5pct, utility_bill_usd`.
2. **Lookup table:** `Outputs/roof_energy_carbon_lookup.csv` (+ `.parquet`), values **per ft² of roof**, keyed by `county_fips × archetype × year`, with columns for both emission-factor bases.

## Usage in the Economics Module
Multiply lookup values by roof area. Use `utility_bill_usd` as the private utility-savings stream, and the `scghg_usd_<rate>` column that matches the Economics Module discount rate as the carbon-externality stream. Then discount alongside the other benefit streams for NPV, BCR, and payback.

## Assumptions & limitations
- Literature coefficients are a screening-level estimate, not a building simulation.
- Residential coefficients and the attic attenuation factor carry the largest uncertainty. Their provenance is documented in the coefficients file.
- Thermal emittance is treated as secondary in V1. Most published coefficients are per ΔSR.
- No post-year-3 aging data exists in CRRC. The aging beyond year 3 is an assumption.
- In heating-dominated counties, net energy and carbon savings can be **negative**. This is reported as-is, not clipped to zero.
- Average (eGRID) and marginal (Cambium) factors answer different questions. Marginal is the default because it is the appropriate basis for avoided emissions.

## Open research risks
1. **Residential coefficients:** Levinson & Akbari (2010) studied *commercial* buildings, so V1 uses DOE/ORNL Roof Savings Calculator runs instead. Risks: RSC availability and batch access, the choice of a representative house per climate zone, and whether one city per zone is enough. Document every RSC input and check the results against published LBNL residential ranges.
2. **Attic attenuation (`f_attic`):** Vented attics on steep-slope homes reduce the savings. Use a literature default, based on building vintage where possible, and make it a parameter.
3. **Thermal emittance:** Most published coefficients are per ΔSR at roughly constant TE. V1 treats TE as secondary, and the README documents that choice.
4. **Aging after year 3:** CRRC has no data past year 3. By default the 3-year value is held constant, with an optional linear decline.
5. **Cambium years:** Cambium publishes 2025–2050 in 5-year steps. Values between those years are interpolated, and 2050 values are held flat afterward. With a 20-year life, a roof installed in 2031 or later runs past 2050. Document the Mid-case release year and the GEA-region crosswalk.

## Implementation plan
New pipeline scripts continue the repo numbering (`Task_15` onward).

| # | Task | Output | Depends on |
|---|---|---|---|
| 1 | **CRRC fields:** extend `Energy/thermal/Task_5_Cool_Roofs.py` to keep Slope, Product Market, Secondary Product Type, Color Family, and the true Product Class (rename `Material`). Regenerate the CSVs and update the docs. | updated `data/raw` / `data/processed` CSVs | — |
| 2 | **Roof archetypes:** filter to steep-slope, group by Product Type × primary color, impute missing aged values (flagged), and add the baseline-roof row. | `data/processed/roof_archetypes_steep.csv` | 1 |
| 3 | **Energy coefficients:** run the ORNL Roof Savings Calculator for a representative steep-slope house in each IECC climate zone at several SR levels, then fit `k_cool` / `k_heat`. Record `f_attic` assumptions and every RSC input. *(Highest research effort.)* | `data/processed/roof_energy_coefficients.csv` | — |
| 4 | **Geographic crosswalk:** county FIPS → IECC climate zone, Cambium GEA region, and eGRID subregion. | `data/processed/county_energy_crosswalk.csv` | — |
| 5 | **Heating fuel mix:** county ACS B25040 shares, reusing the `Task_10` pattern. | `data/processed/county_heating_fuel_mix.csv` | — |
| 6 | **Emission factors:** Cambium LRMER (CO2, CH4, N2O) by region × year, and GHG Hub eGRID, fuel, and GWP tables. | `data/processed/grid_emission_factors.csv`, `fuel_emission_factors.csv` | — |
| 7 | **Calculator:** `Energy/roof_energy_carbon/roof_energy_carbon.py` with `compute_roof_energy_carbon(...)`. | annual DataFrame | 2, 3, 4, 5, 6 |
| 8 | **Monetization:** join EPA SCGHG (all three discount rates) and NY SCGHG per gas, and pull EIA state residential energy prices. Convert everything to 2026 dollars with CPI. | SCGHG + utility-bill columns, `data/processed/state_energy_prices.csv` | 6 |
| 9 | **Lookup table:** batch runner over archetype × county × year, per ft² of roof. | `Outputs/roof_energy_carbon_lookup.csv` (+ parquet) | 7, 8 |
| 10 | **Validation:** compare results with published per-house savings ranges, check that savings turn negative in cold climates, run the eGRID vs Cambium sensitivity, and add unit tests. | tests + validation notes | 9 |
| 11 | **Docs:** finalize this README, update the repo `README.md` and `Energy/thermal/energy_module_planning.md`. | docs | 10 |

Tasks 1, 3, 4, 5, and 6 can run in parallel.

## Decisions log
Confirmed:
- **Coverage:** all U.S. counties in V1. No single-region pilot.
- **Coefficient source:** DOE/ORNL Roof Savings Calculator runs.
- **Cambium scenario:** Mid-case only.
- **Roof life:** 20 years (parameter).
- **Dollar year:** 2026.
- **SCGHG discount rates:** report all three (1.5%, 2.0%, 2.5%).
- **Utility-bill savings:** computed in this module.
- **Baseline roof:** fixed dark asphalt shingle default.

Still open:
- Default `f_attic` and whether it should vary by building vintage.
- How to run the RSC in batch, and which representative city to use per climate zone.
- Whether retail energy prices stay flat in real terms or follow EIA AEO projections.

## Future work
Commercial low-slope roofs; ResStock/ComStock-derived response functions; explicit R-value and attic ventilation; continuous aging curves; hourly Cambium short-run marginal rates with cooling load shapes.
