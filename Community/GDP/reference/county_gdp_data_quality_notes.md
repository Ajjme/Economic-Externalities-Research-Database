# County GDP Data Quality Notes

Generated: 2026-07-04T02:20:46.937513+00:00 UTC

## Share sanity checks
Found 20955 county-year rows where the four industry shares sum to > 1.0.

Sample rows (first 25):

| county_fips | county_name | year | manufacturing_share | construction_share | government_share | service_sector_share |
|---|---|---:|---:|---:|---:|---:|
| 01001 | Autauga, AL | 2014 | 0.449826 | 0.026923 | 0.150726 | 0.375795 |
| 01001 | Autauga, AL | 2016 | 0.484832 | 0.031086 | 0.138467 | 0.365616 |
| 01001 | Autauga, AL | 2017 | 0.542278 | 0.034949 | 0.137150 | 0.371919 |
| 01001 | Autauga, AL | 2018 | 0.521203 | 0.038444 | 0.133497 | 0.383364 |
| 01001 | Autauga, AL | 2019 | 0.455932 | 0.039987 | 0.132046 | 0.398681 |
| 01003 | Baldwin, AL | 2012 | 0.232175 | 0.042788 | 0.119108 | 0.720550 |
| 01003 | Baldwin, AL | 2013 | 0.212524 | 0.039362 | 0.114235 | 0.733015 |
| 01003 | Baldwin, AL | 2014 | 0.205970 | 0.044880 | 0.112213 | 0.735494 |
| 01003 | Baldwin, AL | 2015 | 0.198730 | 0.051872 | 0.109537 | 0.733852 |
| 01003 | Baldwin, AL | 2016 | 0.193938 | 0.064823 | 0.105738 | 0.726083 |
| 01003 | Baldwin, AL | 2017 | 0.196875 | 0.071928 | 0.104100 | 0.718743 |
| 01003 | Baldwin, AL | 2018 | 0.216867 | 0.074208 | 0.102319 | 0.710676 |
| 01003 | Baldwin, AL | 2019 | 0.212927 | 0.066486 | 0.099528 | 0.724949 |
| 01003 | Baldwin, AL | 2020 | 0.197149 | 0.074712 | 0.105355 | 0.714497 |
| 01003 | Baldwin, AL | 2021 | 0.199806 | 0.083115 | 0.098958 | 0.713504 |
| 01003 | Baldwin, AL | 2022 | 0.202699 | 0.091121 | 0.092952 | 0.712023 |
| 01003 | Baldwin, AL | 2023 | 0.121030 | 0.097323 | 0.088587 | 0.693716 |
| 01003 | Baldwin, AL | 2024 | 0.196126 | 0.095042 | 0.090796 | 0.718289 |
| 01005 | Barbour, AL | 2012 | 0.502139 | 0.011741 | 0.162271 | 0.331807 |
| 01005 | Barbour, AL | 2013 | 0.832553 | 0.012078 | 0.140169 | 0.294567 |
| 01005 | Barbour, AL | 2014 | 0.777345 | 0.011985 | 0.147427 | 0.330034 |
| 01005 | Barbour, AL | 2015 | 0.770059 | 0.013979 | 0.151485 | 0.329021 |
| 01005 | Barbour, AL | 2016 | 0.732051 | 0.021424 | 0.150829 | 0.345343 |
| 01005 | Barbour, AL | 2017 | 0.755175 | 0.021815 | 0.154043 | 0.322361 |
| 01005 | Barbour, AL | 2018 | 0.778364 | 0.022109 | 0.152874 | 0.324164 |

## Suppressed values
Encountered 0 BEA cells with `(D)` or `(NA)` and treated them as missing values.

## Connecticut geographic comparability note
Connecticut's most recent BEA county-level vintages use planning regions instead of the state's legacy counties. Older vintages that use the same county_fips labels in CT may not be spatially comparable to newer vintages.

## Basic sanity counts
Total row count: 41171
Distinct county_fips count: 3149
Expected distinct county_fips is typically about 3,100-3,150 before/without CT planning-region transition handling.
