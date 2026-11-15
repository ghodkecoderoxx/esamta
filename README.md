# ESAMTA

**Exploratory Seasonal and Annual Monsoon Trend Analyses for Maharashtra Region**

NASA Space Apps Challenge 2026 · **Be An Earth System Trend Detective!**  
Team / developer: **Vedant Ghodke** · Local Event

> **Submission scope:** The demonstrated results in this repository focus on **precipitation**, using NASA GPM IMERG Version 07. GLDAS Noah V2.1 root-zone soil moisture was explored as a potential extension but is **not claimed as a completed result** here.

## Overview

ESAMTA investigates how precipitation has changed across **Maharashtra, India**, at statewide and district scales. It analyzes annual totals (January–December) and southwest-monsoon totals (**June–September, JJAS**) over **1998–2024**, turning monthly satellite precipitation estimates into long regional time series, maps of trend magnitude, and statistical tests of monotonic change.

The purpose is to reveal regional differences that can be obscured by statewide averages. ESAMTA is an **exploratory trend-analysis workflow**, not a rainfall forecasting model or a causal attribution study.

## Main findings

Analysis of the supplied 1998–2024 results covers **27 years**, **36 districts**, and a Maharashtra-wide aggregate. Trend magnitude is estimated using **Sen's slope**. Statistical evidence for monotonic change is assessed with a **Hamed–Rao modified Mann–Kendall test**; district-level results are additionally screened using **false discovery rate (FDR)** correction.

| Spatial scale / period | Sen's slope | Modified MK p-value | Interpretation |
|---|---:|---:|---|
| Maharashtra, annual | +66.9 mm/decade | 0.144 | No significant statewide monotonic trend at 5% |
| Maharashtra, JJAS | +52.5 mm/decade | 0.156 | No significant statewide monotonic trend at 5% |

**Five of 36 districts** passed the district-level modified MK FDR criterion (q &lt; 0.05) in **both** annual and JJAS analyses:

| District | Annual Sen's slope (mm/decade) | JJAS Sen's slope (mm/decade) |
|---|---:|---:|
| Mumbai | +277.0 | +273.7 |
| Mumbai Suburban | +308.6 | +292.2 |
| Palghar | +254.3 | +226.2 |
| Raigarh | +208.3 | +191.1 |
| Thane | +206.3 | +180.5 |

These are **estimated historical trends**, not future projections. A trend's statistical significance should not be confused with causal attribution or the size of its practical impacts. Values above come from the submitted `trend_results.csv`; they have not been independently regenerated from source granules for this README.

## Visual results

The repository can include these supplied figures under `results/figures/` (update paths if stored elsewhere):

### District-scale trend direction and significance

![Annual and JJAS district precipitation trends; hatching identifies FDR-significant districts](results/figures/district_trends_with_significance.png)

*Sen's slope (mm/decade) for annual and JJAS precipitation. Hatching denotes modified Mann–Kendall results passing FDR-adjusted q &lt; 0.05, as labeled in the supplied figure.*

### Statewide precipitation time series

![Maharashtra annual precipitation, 1998–2024](results/figures/annual_timeseries.png)

![Maharashtra JJAS precipitation, 1998–2024](results/figures/monsoon_timeseries.png)

*The dashed line in these figures is an **OLS descriptive fit**, not Sen's slope. Trend inference reported above uses the modified Mann–Kendall test; OLS results and HAC sensitivity are also recorded in the outputs.*

Additional maps, if committed: `annual_district_trends.png` and `monsoon_district_trends.png`.

## Data sources

| Component | Source | Use |
|---|---|---|
| Precipitation | **NASA GPM IMERG Version 07**, monthly precipitation estimates; monthly product family `GPM_3IMERGM` | Precipitation time series and spatial trend analysis |
| Administrative boundaries | `MAHARASHTRA_DISTRICTS.geojson` | District geographic extraction and visualization (36 district polygons) |
| Soil moisture — potential extension | NASA GLDAS Noah V2.1 (`GLDAS_NOAH025_M`) | Not part of the demonstrated precipitation results |

- NASA IMERG monthly product: https://doi.org/10.5067/GPM/IMERG/3B-MONTH/07
- NASA precipitation mission overview: https://gpm.nasa.gov/data/imerg
- NASA GLDAS information: https://ldas.gsfc.nasa.gov/gldas
- **Boundary source URL and publisher:** `[ADD THE ORIGINAL GEOJSON SOURCE URL AND PUBLISHER BEFORE SUBMISSION]`. A separate MIT-formatted `LICENSE.txt` accompanied the provided resource; retain its copyright notice and attribution and ensure it applies to this file.

The exact IMERG file identifiers, regional pixel weighting, missing-data filters, and monthwise conversion from source rate units to precipitation accumulation should be read from the processing scripts; this README does not assert their implementation details without inspecting those scripts.

## Methods

1. **Data ingestion:** Download or read NASA IMERG V07 precipitation data. The analysis uses monthly precipitation aggregated by calendar month.
2. **Geographic extraction:** Construct Maharashtra-wide and district-level precipitation series using the Maharashtra district boundaries.
3. **Temporal aggregation:** Sum monthly precipitation into **calendar-year** (January–December) and **JJAS monsoon** (June–September) totals for each year.
4. **Trend magnitude:** Compute **Sen's slope**, reported in **mm/decade**.
5. **Significance:** Apply the **Hamed–Rao modified Mann–Kendall** trend test, which is intended to adjust variance for temporal autocorrelation. Apply **FDR correction** over district-level tests for each time aggregation.
6. **Sensitivity and visualization:** Produce OLS fits, HAC-based sensitivity results, district trend maps, and statewide time series.

A significant trend means statistical evidence of a monotonic change under the method's assumptions; it does **not** establish why precipitation changed. Statewide and district-level inferences are distinct.

## Repository files

The following are the **working project filenames reported by the developer**. Preserve the paths used by your scripts unless you also update their file references.

```text
ESAMTA/
├── README.md
├── requirements.txt
├── .gitignore
├── LICENSE                         # your own code license, if chosen
├── 01_build_district_series.py
├── 02_analyze_trends.py
├── 02b_plot_trend_significance.py
├── 03_screen_dry_conditions.py     # include only if used/documented
├── download_subset_files_v02.py
├── validate_data.py
├── MAHARASHTRA_DISTRICTS.geojson
├── results/
│   ├── annual_series.csv
│   ├── monsoon_series.csv
│   ├── trend_results.csv
│   ├── hac_sensitivity.csv
│   └── figures/
│       ├── annual_timeseries.png
│       ├── monsoon_timeseries.png
│       ├── district_trends_with_significance.png
│       ├── annual_district_trends.png
│       └── monsoon_district_trends.png
└── third_party_licenses/
    └── MAHARASHTRA_DISTRICTS_LICENSE.txt
```

The `results/` organization above is **recommended**, not verified as your current local directory structure. Adjust the README image links to match the actual committed paths. Raw `.nc`/`.nc4` downloads and virtual environments should not be committed.

## Installation and reproduction

**Prerequisites:** Python, sufficient local storage for any source data downloads, and NASA Earthdata authentication if required by the chosen data access workflow.

```powershell
# From your project directory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**Run order (based on script names, not yet command-line verified):**

1. `download_subset_files_v02.py` — retrieve input data, using its documented configuration or authentication.
2. `validate_data.py` — validate downloaded input data.
3. `01_build_district_series.py` — build region-level precipitation series.
4. `02_analyze_trends.py` — calculate trend and significance results.
5. `02b_plot_trend_significance.py` — plot district significance maps.
6. `03_screen_dry_conditions.py` — optional exploratory screening, only if included in the final results.

**Important:** The actual scripts were not included with the materials reviewed for this README, so their CLI arguments, input directories, and successful end-to-end execution have **not** been verified. Open each script for its expected parameters; do not assume `python script.py` works without configuration. The committed CSV and PNG results let judges inspect the analysis without downloading the full raw dataset.

## Outputs

- `annual_series.csv` — year-by-year annual regional precipitation totals.
- `monsoon_series.csv` — year-by-year JJAS precipitation totals.
- `trend_results.csv` — trend magnitude, modified MK statistics, FDR flags, OLS and HAC results.
- `hac_sensitivity.csv` — OLS trend inference with alternate HAC lag settings.
- PNG plots — statewide time series and district-scale trend maps.

## Limitations

- **Historical period:** The demonstrated precipitation outputs use **1998–2024**, not the previously considered 2000–2024 interval.
- **Source uncertainty:** Satellite precipitation products can contain systematic and time-varying retrieval errors. Small districts and complex coastal terrain require particular care.
- **Spatial representation:** District-wide gridded estimates do not resolve all local weather extremes. Aggregation depends on masks, sampling, and any spatial weighting.
- **Autocorrelation and multiple tests:** The modified MK and FDR procedures help address inference issues but do not eliminate all dependence, including spatial correlation between neighboring districts.
- **Interpretation:** A positive trend does not imply an increase in rainfall every year; the year-to-year range remains substantial. Neither the maps nor the tests establish causality.
- **Drought:** Precipitation trends alone do not diagnose root-zone soil-moisture drought. GLDAS-based drought-state classification is **future work** unless completed and documented separately.
- **Software maturity:** The uploaded figures demonstrate an analysis pipeline; a separate interactive deployed application has not been established in the supplied materials.

## Project demo

A seven-slide PDF demo presents the research question, methods, historical time series, spatial trend maps, statistical findings, and limitations.

**Public demo URL:** `[ADD PUBLIC LINK TO SEVEN-SLIDE DEMO]`  
**NASA Space Apps project URL:** `[ADD SUBMISSION LINK IF AVAILABLE]`

## Attribution and responsible AI use

- **NASA / GPM IMERG V07:** Cite the NASA product and relevant data documentation. NASA datasets are attributed to their respective producing institutions.
- **Maharashtra boundaries:** Retain the third-party source URL, publisher and applicable license/copyright statement. The supplied third-party MIT-style license is separate from the author's original software license.
- **Third-party software:** See `requirements.txt` and applicable upstream package licences.
- **AI assistance:** ChatGPT was used to help draft submission documentation and presentation content. Include additional truthful disclosures if AI assisted with code, plots, or data analysis, and identify AI-generated elements where required under the NASA Space Apps submission rules.

## License

**Original ESAMTA source code:** `[INSERT THE REPOSITORY'S ACTUAL CHOSEN LICENSE, E.G. MIT, AND A MATCHING ROOT LICENSE FILE]`. A suggested owner notice for a newly adopted MIT code license is `Copyright (c) 2026 Vedant Ghodke`.

Third-party data, administrative boundaries and assets retain their **own** attribution and licence terms; the ESAMTA software license does not relicense them.
