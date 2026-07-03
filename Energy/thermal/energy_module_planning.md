# CADENCE Energy Delta Module

## Overview

The Energy Delta Module estimates the change in annual building energy consumption resulting from replacing one roofing material with another. The purpose of this module is **not** to perform a full building energy simulation (e.g., EnergyPlus), but rather to estimate the incremental energy benefit attributable solely to changes in roof surface optical properties.

The module is designed to integrate directly into the CADENCE Economics Module where annual utility savings become another benefit stream contributing to:

- Net Present Value (NPV)
- Benefit-Cost Ratio (BCR)
- Payback Period
- Carbon Reduction
- Scenario Analysis

This module assumes that all other aspects of the building remain unchanged.

---

# Version 1 Assumptions

To isolate the effect of roofing materials, the following assumptions are made:

- Roof insulation remains unchanged after roof replacement.
- Roof decking remains unchanged.
- HVAC equipment remains unchanged.
- Indoor temperature setpoints remain unchanged.
- Building occupancy remains unchanged.
- Air leakage remains unchanged.
- Roof geometry remains unchanged.
- Roof area remains unchanged.
- Local weather is represented by the selected ASHRAE climate zone.
- Only the roof topping (surface material) changes.

These assumptions mean the module estimates the **incremental energy benefit** caused solely by changing the roof surface.

---

# Physical Basis

Incoming solar radiation experiences three primary pathways:

Incoming Solar Radiation

↓

Reflected

+

Absorbed

↓

Roof Surface Heating

↓

Heat Transfer through Roof

↓

Building Cooling Load

Solar Reflectance determines how much incoming solar energy is reflected.

Thermal Emittance determines how efficiently absorbed heat is released back to the atmosphere.

Because roof insulation is assumed constant, the conductive heat transfer equation simplifies to

Q = U × A × ΔT

where

- U = Roof thermal transmittance (constant)
- A = Roof Area (constant)
- ΔT = Roof Surface Temperature – Indoor Temperature

Since U and A are constant, the only changing variable is roof surface temperature.

Therefore,

**Changes in Solar Reflectance and Thermal Emittance alter roof surface temperature, which changes conductive heat flow into the building, ultimately affecting HVAC energy consumption.**

---

# Input Data

## From cool_roofs_summary.csv

The engineering database contains summarized optical properties for each roof class.

Example

| Field |
|--------|
| Product Type |
| Color |
| Initial Solar Reflectance mean |
| 3-Year Solar Reflectance mean |
| Initial Thermal Emittance mean |
| 3-Year Thermal Emittance mean |
| Initial SRI mean |
| 3-Year SRI mean |

Example row

| Product Type | Color | Initial Solar Reflectance | 3-Year Solar Reflectance | Initial Thermal Emittance | 3-Year Thermal Emittance |
|--------------|-------|--------------------------|--------------------------|---------------------------|--------------------------|
| Asphalt Shingle | Black | 0.194 | 0.196 | 0.918 | 0.918 |

---

## User Inputs

The user provides:

- Existing Roof Type
- Existing Roof Color
- New Roof Type
- New Roof Color
- Roof Area (ft²)
- Electric Price ($/kWh)
- Climate Zone
- Carbon Intensity (kg CO₂/kWh)

Future versions may additionally include

- Heating fuel type
- Utility demand charges
- Roof pitch
- Building occupancy
- Building type

---

# Simulation Workflow

## Step 1

Read the existing roof optical properties from the engineering database.

Obtain

- Solar Reflectance
- Thermal Emittance

---

## Step 2

Read the replacement roof optical properties.

Obtain

- Solar Reflectance
- Thermal Emittance

---

## Step 3

Calculate property changes

Δ Solar Reflectance

ΔSR = SR_new − SR_old

Δ Thermal Emittance

ΔTE = TE_new − TE_old

These two values describe the physical improvement created by the replacement.

---

## Step 4

Estimate Roof Surface Temperature Reduction

The module will estimate

ΔT_roof

using empirical relationships developed from published DOE, ASHRAE, California Title 24, and peer-reviewed building energy simulation studies.

Example

Higher Solar Reflectance

↓

Less absorbed solar radiation

↓

Lower roof temperature

Higher Thermal Emittance

↓

Faster radiative cooling

↓

Lower roof temperature

The combined effect determines

ΔT_roof

---

## Step 5

Estimate Building Cooling Load Reduction

The reduced roof temperature decreases conductive heat flow into the building.

The simulation estimates

Annual Cooling Energy Reduction (%)

using an empirical response function

Cooling Reduction

=

f(

Climate Zone,

ΔSR,

ΔTE

)

This function will be calibrated from published building energy studies.

---

## Step 6

Calculate Annual Energy Savings

Annual kWh Saved

=

Baseline Annual Cooling Energy

×

Cooling Reduction %

The baseline annual cooling energy may come from

- DOE reference buildings
- ResStock
- ComStock
- Future CADENCE building database

Version 1 may instead estimate savings directly from published literature lookup tables.

---

## Step 7

Calculate Utility Savings

Annual Utility Savings

=

Annual kWh Saved

×

Electric Price

---

## Step 8

Calculate Carbon Reduction

Annual Carbon Reduction

=

Annual kWh Saved

×

Carbon Intensity

Outputs may be reported in

- kg CO₂/year
- metric tons CO₂/year

---

# Outputs

The simulation returns

| Output |
|----------|
| Existing Solar Reflectance |
| New Solar Reflectance |
| Δ Solar Reflectance |
| Existing Thermal Emittance |
| New Thermal Emittance |
| Δ Thermal Emittance |
| Estimated Roof Temperature Reduction |
| Estimated Cooling Energy Reduction (%) |
| Annual Electricity Savings (kWh) |
| Annual Utility Savings ($) |
| Annual Carbon Reduction (kg CO₂) |

These values are passed directly into the Economics Module.

---

# Integration with the Economics Module

Annual utility savings become another annual benefit stream alongside

- Avoided Losses
- Insurance Premium Savings
- Tax Incentives
- Community Incentives
- Carbon Credits

The annual utility savings are discounted over the analysis period and incorporated into

- Net Present Value
- Benefit-Cost Ratio
- Payback Period

---

# Aging Considerations

The Cool Roof Rating Council database provides both

- Initial properties
- Three-Year properties

Version 1 will estimate performance using the three-year values, representing stabilized field performance after initial weathering.

Future versions may model optical degradation over the full roof lifetime using aging curves.

Example

Year 0

Solar Reflectance = 0.72

↓

Year 3

Solar Reflectance = 0.67

↓

Year 10

Estimated = 0.63

↓

Year 20

Estimated = 0.59

This would allow annual energy savings to decrease gradually over time, making the energy simulation consistent with CADENCE's broader asset aging framework.

---

# Future Enhancements

Version 2

- Include heating penalties for cold climates.
- Include HVAC system efficiency.
- Incorporate roof insulation (R-value).
- Incorporate attic ventilation.
- Model roof aging continuously beyond three years.
- Support commercial buildings.
- Support wall systems.
- Integrate DOE ResStock and ComStock reference buildings.
- Replace empirical response functions with reduced-order physics models derived from EnergyPlus simulations.

---

# Required Research

The primary research task is to develop empirical functions relating

Climate Zone

+

Solar Reflectance Change

+

Thermal Emittance Change

↓

Roof Surface Temperature Reduction

↓

Cooling Energy Reduction

↓

Annual Electricity Savings

This calibration will be based on published DOE, ASHRAE, California Title 24, and peer-reviewed building energy simulation studies.

Once calibrated, these relationships become the core predictive engine of the CADENCE Energy Delta Module.