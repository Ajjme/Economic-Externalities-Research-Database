# CRRC Roof Directory Pipeline

## Source
- Public CRRC Roof Directory page: https://coolroofs.org/directory/roof?product_type_id=
- Backing portal API host observed in frontend source: https://portal.coolroofs.org
- Direct daily export endpoint used by this pipeline: https://portal.coolroofs.org/directory/roof/download

## Endpoint Investigation Results
- REST/JSON endpoint: yes.
	- POST https://portal.coolroofs.org/api/directory returns paginated JSON product records.
	- Additional JSON endpoints include /api/product-types, /api/product-colors, /api/companies, and /api/customer-types.
- GraphQL endpoint: no evidence.
	- Probe to https://portal.coolroofs.org/graphql returned HTTP 404.
- Downloadable CSV: yes.
	- https://portal.coolroofs.org/directory/roof/download returns text/csv with a daily snapshot of all roof products.
- HTML scraping requirement: no.
	- Since JSON and CSV endpoints are available, scraping rendered HTML is unnecessary.

## Collection Method
- Script: Energy/thermal/Task_5_Cool_Roofs.py
- The script downloads the CSV export, keeps valid CRRC product rows, and writes:
	- data/raw/cool_roofs_raw.csv
	- data/processed/cool_roofs_summary.csv

## Output Datasets
- Raw dataset columns:
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

- Engineering summary:
	- Grouped by Product Type and Color
	- Statistics for each thermal/reflectance metric:
		- mean
		- median
		- std
		- min
		- max
	- Includes Number of products per group

## Update Procedure
1. From repo root, run: python Energy/thermal/Task_5_Cool_Roofs.py
2. Confirm both CSV files were rewritten with the current Date Collected.
3. Commit updated CSVs if needed.

## Assumptions
- The portal CSV export remains publicly accessible without authentication.
- CRRC product identifiers in the export continue to follow the pattern ####-####.
- Product Name is represented as Brand + Model in CRRC export fields.
- Material is represented using Product Class.

## Limitations
- The export is generated once per day by CRRC, so it may lag behind live portal changes.
- The export includes non-product explanatory rows that must be filtered.
- Missing or non-numeric performance values are retained as blank in raw data and excluded from numeric statistics.