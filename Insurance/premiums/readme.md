Insurance Premium Prediction Engine
Rather than relying on state-level average homeowner insurance premiums, CADENCE will develop a property-level insurance premium prediction engine that estimates premiums based on the characteristics of an individual asset. Modern insurers price policies using hundreds of variables—including roof age, roof material, construction type, replacement cost, local hazard exposure, wildfire and wind risk, deductible, and property location—making statewide averages too coarse for resilience planning and investment analysis. CADENCE already models many of these variables through its hazard, vulnerability, and asset aging framework, providing a strong foundation for a transparent and explainable premium estimation model.
The research effort will focus on collecting a representative dataset of real insurance quotes from properties across diverse geographic regions and hazard environments. These observations will be combined with building characteristics and climate risk metrics to calibrate statistical and machine learning models capable of predicting homeowner insurance premiums from asset-level features. The resulting model will enable CADENCE to estimate how resilience upgrades, climate change, asset aging, and insurance incentive programs influence future insurance costs. Because the model is based on interpretable property characteristics rather than proprietary insurer algorithms, it provides a flexible research platform for simulating insurer behavior, evaluating resilience investments, and exploring long-term changes in community insurability under alternative climate and policy scenarios.

Premium

= Base Rate

× Location Risk

× Construction

× Roof Age

× Roof Material

× Roof Condition

× Distance to Coast

× Wind Zone

× Hail Zone

× Wildfire

× Crime

× Fire Station Distance

× Claims History

× Credit Score

× Coverage Amount

× Deductible

× Discounts

× Company Loading

We could calibrate the model
Rather than needing millions of policies, we could collect a few thousand quotes.
For example
Take 500 houses around the country.
For each house gather
address
replacement value
roof age
roof type
county
ZIP
wind
hail
wildfire
flood
crime
deductible
estimated premium
Then fit
Premium = f(asset characteristics)
using
Random Forest
XGBoost
Bayesian model
Generalized Linear Model (GLM), which is commonly used in insurance ratemaking
This gives us a transparent, explainable premium estimator.

Or we can wait for this report - actually this report wont have
https://content.naic.org/article/state-insurance-regulators-issue-nationwide-homeowners-market-data-call

Current place holder will be state level permiums from the 2022 report

Homeowners package policies for owner-occupied dwellings (1-4 family units)
• HO-1: Basic “named-perils”2 coverage on buildings and personal property.
• HO-2: Broad “named-perils” coverage on buildings and personal property; provides coverage for
more perils than HO-1 package.
• HO-3: Provides “all-risks”3 coverage on buildings, broad named-peril coverage on personal
property; most common package written.
HO-5: Provides “all-risks” coverage on buildings and personal property.
• HO-8: Repair cost coverage for a dwelling whose replacement cost greatly exceeds its market
value. Personal property, theft and additional coverages provided are similar to coverages
provided under an HO-1 policy.
Homeowners package policies for tenants, condominium and cooperative unit owners
• HO-4 (Renter’s Insurance): Broad “named-perils” coverage for the personal property of
tenants.
• HO-6 (Condo/Co-op Insurance): Broad “named-perils” coverage for personal property of
condominium or cooperative unit owners, as well as certain building items in which the unit
owner may have an insurable interest.

Data for all states, except Texas and California, were provided by the American Association of
Insurance Services; ISO Data, Inc.; the National Independent Statistical Service; Independent
Statistical Service, Inc. (ISS); and the Mutual Service Office (MSO).
 Texas data were obtained from the Texas Department of Insurance. Historically, the Texas
department developed its own home insurance policy forms that are similar, but not identical, to
homeowners policy forms countrywide. Although, starting in 2002, insurers were permitted to
file their own independent forms, some companies continue to use the forms previously
promulgated by the department.
• California data were provided by the California Department of Insurance. The state began
collecting homeowners data in 1998, starting with the 1996 data year.

Exposure = house-years — the standard unit insurers use to measure how much coverage was actually in force, not how many policies existed.

Table 4 specifically: Average Premium isn't just "total premium ÷ number of policies" — it's Premium ÷ Exposure (house-years)

