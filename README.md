# Challenge 2 — Earth System Trend Detective (groundwork v2)

## Confirmed challenge requirements
The official brief asks for a **tool**, not just one trend chart. A user should be able to select Earth-science variables measured by missions or produced by models, obtain data for a chosen region, view a sufficiently long time series, estimate the rate of change, and test statistical significance (for example, a t-test, Mann–Kendall, or confidence intervals). Variable definitions and a couple of example investigations would make the tool more useful. Linear trend analysis is explicitly an acceptable starting point; seasonal cycles and serial correlation need to be considered.

## Groundwork data sources
1. **NASA MERRA-2 Monthly Single-Level Diagnostics (`M2TMNXSLV`)** — primary candidate for data-access familiarization. It is a model/reanalysis product with monthly gridded variables such as near-surface air temperature, specific humidity, winds, and pressure since 1980. Downloading requires a free NASA Earthdata Login.
2. **NASA GRACE / GRACE-FO Mascon Water Height** — alternative candidate aligned with water stress and climate-risk use cases; monthly total-water-storage changes from 2002 onward. Downloading requires a free NASA Earthdata Login.
3. **NASA GISTEMP v4** — retain the existing CSV notebook for basic data cleaning, anomaly interpretation, trend estimation, and significance concepts. Treat it as a teaching dataset, **not the preferred submission source** until the official resource list is available and eligibility is checked.

## Why MERRA-2 is the best first access test
A single catalogued monthly product offers multiple candidate variables, helps satisfy the variable-selection concept, and spans enough years for trend analysis. Its regional aggregation, missing-data rules, variable units, seasonality, and serial correlation must still be checked carefully. NASA Giovanni can make time series and maps in a browser, but its current beta page requires Earthdata Login and warns that usage may be limited by cloud credits; do not make the project dependent on it without a successful test.

## New exploratory notebook
`02_MERRA2_Catalog_and_Variable_Familiarization.ipynb` searches the NASA catalogue and, optionally, downloads one monthly granule for metadata inspection. It does **not** build the challenge’s regional trend engine, statistical-analysis pipeline, or application. A NASA Earthdata Login is required only if you opt in to the download step.

## Competition boundary
Until the official challenge Resources tab is available and the event starts, restrict work to data discovery, access checks, understanding variable metadata, learning statistical concepts, and comparing candidate sources. Do not implement the submission tool or pre-build its final pipeline/UI. The pasted brief says the challenge resource lists may be updated before the event; check them on **13 November 2026**.

## Official and supporting links
- Official challenge page: https://www.spaceappschallenge.org/2026/challenges/be-an-earth-system-trend-detective/
- NASA MERRA-2 overview/FAQ: https://gmao.gsfc.nasa.gov/gmao-products/merra-2/faq_merra-2/
- NASA Giovanni: https://giovanni.earthdata.nasa.gov/
- NASA GRACE/GRACE-FO products: https://podaac.jpl.nasa.gov/
- NASA GISTEMP v4 data downloads: https://data.giss.nasa.gov/gistemp/data_v4.html
- Independent pre-event dataset map (helpful, not NASA-endorsed and not the official resource list): https://spacedata.swapniltamse.com/challenges/earth-system-trend-detective/
