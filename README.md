# Economic-Externalities-Research-Database
National-scale economic data framework for CADENCE. Collects and standardizes insurance, energy, incentive, financing, carbon, and other externality datasets to support customizable benefit-cost analysis, NPV, BCR, payback, and resilience investment scenario modeling.

Everything in the economic engine should be location-aware, nationally available, updateable, and independent of the hazard model.

API key from FRED needs to be redownloaded each day

File Structure

├── Insurance
│     premiums
        Will create formulaically based on the information we already have in the model (ask what should the premium be instead of what is it)
        For now though we will make this a user input. we will request the user use online premium estimators from various insurance companies 
│     discounts
│     underwriting
│
├── Energy
│     electricity
│     gas
│     solar
│
├── Incentives
│     federal
│     state
│     utility
│     local
        FORTIFIED Homes Program - could build national database of who utilitze this incentive scheme but wont for now
│
├── Carbon
│     SCC
│     emissions
│
├── Finance
│     inflation
        Task_1_Inflation.py
│     discount
        Task_2_Discount_rates.py
│     financing
        Task_3_Mortgage_rates.py
        Task_4_Cost_of_Capitial.py
│
├── Failure Costs
│     downtime
│     housing
│     contents
│
├── Community
│     GDP
│     employment
│     property values