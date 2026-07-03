https://erefdn.org/product/eref-landfill-tip-fee-list-2022/
sources

Plan # Roof Disposal and Recycling Economics Research Plan

## Overview

This project develops the **Roof Disposal Economics** component of the CADENCE Economic Module. The objective is to estimate the end-of-life cost of roofing materials by modeling two competing disposal pathways:

1. **Landfill disposal**
2. **Asphalt shingle recycling**

The initial implementation intentionally avoids transportation and hauling costs to keep the model simple and based entirely on publicly available national datasets. Future versions can incorporate distance-based routing and hauling costs.

---

# Objectives

Develop a nationwide database capable of estimating:

* Disposal cost of removed roofing materials
* Recycling availability
* Potential recycling cost savings
* Default national disposal values for locations without local data

The resulting database will integrate directly into the CADENCE economic engine, allowing disposal costs to be included in NPV, Benefit-Cost Ratio (BCR), Payback Period, and lifecycle cost analyses.

---

# Phase 1 — National Landfill Cost Database

## Primary Data Source

**2025 EREF Report: *MSWLF Tipping Fees 2024***

This report will serve as the authoritative source for national disposal economics.

### Data to Extract

* National average tipping fee
* Regional average tipping fees
* Standard deviation
* Minimum and maximum reported fees
* Historical trends (where available)
* Statistical distributions suitable for uncertainty analysis

These values will become the default landfill disposal assumptions throughout CADENCE.

---

# Phase 2 — Roofing Recycling Database

## Primary Source

Construction & Demolition Recycling Association

[https://shinglerecycling.org/find-a-recycler/](https://shinglerecycling.org/find-a-recycler/)

This website contains the most comprehensive public directory of asphalt shingle recycling facilities in North America.

### Data Collection

Develop a web scraper to collect:

* Facility name
* Address
* City
* State
* ZIP code
* Latitude
* Longitude
* Phone number
* Website
* Accepted roofing materials
* Acceptance of tear-off shingles
* Acceptance of manufacturer scrap
* Operating status

The resulting database will provide the geographic availability of asphalt shingle recycling throughout the United States.

---

# Phase 3 — Recycling Economics

The recycler directory identifies facilities but generally does not include pricing.

For each recycler, collect (where publicly available):

* Recycling fee
* Processing fee
* Material acceptance requirements
* Clean load requirements
* Contamination restrictions
* Minimum load size
* Maximum load size

If pricing cannot be obtained, the database should include a placeholder value and identify facilities requiring manual follow-up.

---

# Phase 4 — Roofing Waste Generation Database

To convert roof area into disposal cost, CADENCE requires default waste generation factors.

Develop a reference database containing typical tear-off weights for common roofing systems.

Example asset classes include:

* 3-tab asphalt shingles
* Architectural asphalt shingles
* Impact-resistant (Class 4) shingles
* Metal roofing
* Clay tile
* Concrete tile
* Slate roofing

For each roofing material collect:

* Weight per roofing square (100 ft²)
* Weight per square foot
* Typical service life
* Source reference

These values will allow the software to estimate waste tonnage from roof area alone.

---

# Economic Calculation Workflow

The disposal calculation will follow a straightforward sequence:

1. User provides roof area and roofing material.
2. CADENCE estimates the quantity of roofing waste using material-specific weight factors.
3. National tipping fee statistics from the EREF report are applied to estimate landfill disposal cost.
4. If a recycling facility exists for the selected material, the system estimates recycling cost using the collected facility pricing or default assumptions.
5. The economic engine compares landfill disposal and recycling costs and incorporates the selected pathway into lifecycle economic analyses.

---

# Database Structure

## National Tipping Fee Statistics

| Field              | Description                 |
| ------------------ | --------------------------- |
| National Mean      | Average tipping fee ($/ton) |
| Standard Deviation | National variability        |
| Minimum            | Lowest reported fee         |
| Maximum            | Highest reported fee        |
| Report Year        | Data vintage                |
| Source             | EREF                        |

---

## Recycling Facility Database

| Field                      | Description           |
| -------------------------- | --------------------- |
| Facility ID                | Unique identifier     |
| Facility Name              | Recycler name         |
| Address                    | Street address        |
| City                       | City                  |
| State                      | State                 |
| ZIP Code                   | ZIP code              |
| Latitude                   | Geographic coordinate |
| Longitude                  | Geographic coordinate |
| Phone                      | Contact number        |
| Website                    | Facility website      |
| Accepts Tear-Off Shingles  | Yes/No                |
| Accepts Manufacturer Scrap | Yes/No                |
| Accepted Materials         | Material types        |
| Recycling Fee              | $/ton (if available)  |
| Data Source                | Source URL            |

---

## Roofing Waste Database

| Material | Weight (lb/square) | Weight (lb/ft²) | Typical Life (years) | Source |
| -------- | -----------------: | --------------: | -------------------: | ------ |

---

# Expected Deliverables

* National tipping fee database derived from the 2025 EREF report.
* Nationwide database of asphalt shingle recycling facilities.
* Database of publicly available recycling fees and facility acceptance criteria.
* Roofing material weight database for estimating tear-off waste quantities.
* Disposal cost calculation module integrated into the CADENCE economic engine.

---

# Future Enhancements

The initial implementation focuses on disposal and recycling fees only. Future research may extend the module with:

* Distance-based hauling costs
* Nearest-facility routing
* Regional landfill selection
* Carbon emissions associated with disposal and recycling
* Material recovery value and recycled asphalt commodity pricing
* Time-varying tipping fee projections for long-term economic simulations

This phased approach establishes a robust national disposal economics layer while remaining simple enough for immediate integration into the CADENCE platform.
