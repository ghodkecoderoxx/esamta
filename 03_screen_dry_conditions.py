
"""
03_screen_dry_conditions.py

Historical JJAS dry-condition screening for Maharashtra.

Inputs:
    Required:
        district_monthly.csv (NASA IMERG)

    Optional:
        gldas_rootzone_monthly.csv (NASA GLDAS)

Output:
    Rainfall percentile CSV
    Yearly summary CSV
    Rainfall map
    Optional combined rainfall + soil-moisture CSV/map

IMPORTANT:
    A low-percentile flag is NOT an official drought
    classification or a future drought forecast.

AI assistance: OpenAI ChatGPT assisted with code drafting.
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

IMERG_CSV = (
    ROOT / "data" / "district_series_outputs"
    / "processed" / "district_monthly.csv"
)

GLDAS_CSV = (
    ROOT / "data" / "district_series_outputs"
    / "processed" / "gldas_rootzone_monthly.csv"
)

BOUNDARY_FILE = ROOT / "MAHARASHTRA_DISTRICTS.geojson"

OUTPUT_DIR = (
    ROOT / "data" / "district_series_outputs"
    / "dry_conditions"
)

START_YEAR = 2000
END_YEAR = 2024

JJAS = {6, 7, 8, 9}

# Exploratory project choices, not official drought criteria.
LOW_PERCENTILE = 20.0
MIN_BASELINE_YEARS = 20

# Used only for the optional GLDAS data.
MIN_SOIL_COVERAGE = 0.80
MIN_EFFECTIVE_CELLS = 2.0

# Choose a year for the map.
MAP_YEAR = 2015


# ============================================================
# AGGREGATE COMPLETE JJAS SEASONS
# ============================================================

def aggregate_jjas(source, column, aggregation):

    if isinstance(source, pd.DataFrame):
        df = source.copy()
        source_name = "dataframe"
    else:
        if not source.exists():
            raise FileNotFoundError(source)
        df = pd.read_csv(source)
        source_name = source.name

    required = {
        "month", "entity_type", "entity", column
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"{source_name}: missing {sorted(missing)}"
        )

    df["month"] = pd.to_datetime(
        df["month"], errors="raise"
    )

    if df.duplicated(
        ["month", "entity_type", "entity"]
    ).any():
        raise ValueError(
            f"Duplicate observations in {source_name}"
        )

    df[column] = pd.to_numeric(
        df[column], errors="coerce"
    )

    if np.isinf(df[column]).any():
        raise ValueError("Infinite values encountered.")

    if aggregation == "sum":
        if (df[column].dropna() < 0).any():
            raise ValueError("Negative precipitation.")

    df["year"] = df["month"].dt.year
    df["month_number"] = df["month"].dt.month

    df = df[
        df["year"].between(START_YEAR, END_YEAR)
        & df["month_number"].isin(JJAS)
    ]

    grouped = df.groupby(
        ["entity_type", "entity", "year"],
        as_index=False
    ).agg(
        months=("month_number", "nunique"),
        valid=(column, "count"),
        value=(column, aggregation)
    )

    # Reject incomplete seasons.
    return grouped.loc[
        (grouped["months"] == 4)
        & (grouped["valid"] == 4),
        ["entity_type", "entity", "year", "value"]
    ].copy()


# ============================================================
# COMPUTE HISTORICAL PERCENTILES
# ============================================================

def empirical_percentiles(
    df, value_column, result_column
):
    """
    Rank observations within each region using the
    fixed 2000–2024 reference period.

    An in-sample percentile is descriptive, not predictive.
    """

    output = df.copy()
    output[result_column] = np.nan

    for _, group in output.groupby(
        ["entity_type", "entity"]
    ):

        reference = group[
            value_column
        ].dropna().to_numpy(dtype=float)

        if len(reference) < MIN_BASELINE_YEARS:
            continue

        sorted_reference = np.sort(reference)

        valid_indices = group.index[
            group[value_column].notna()
        ]

        values = group.loc[
            valid_indices, value_column
        ].to_numpy(dtype=float)

        # Upper empirical rank for ties.
        percentiles = (
            100.0
            * np.searchsorted(
                sorted_reference,
                values,
                side="right"
            )
            / len(reference)
        )

        output.loc[
            valid_indices, result_column
        ] = percentiles

    return output


# ============================================================
# OPTIONAL GLDAS SOIL-MOISTURE PROCESSING
# ============================================================

def load_soil():

    if not GLDAS_CSV.exists():
        print(
            "GLDAS CSV not found. "
            "Running rainfall-only analysis."
        )
        return None

    df = pd.read_csv(GLDAS_CSV)

    required = {
        "month",
        "entity_type",
        "entity",
        "rootzone_moisture_kg_m2",
        "valid_coverage_fraction",
        "effective_cells"
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"GLDAS columns missing: {sorted(missing)}"
        )

    numeric_columns = [
        "rootzone_moisture_kg_m2",
        "valid_coverage_fraction",
        "effective_cells"
    ]

    for col in numeric_columns:
        df[col] = pd.to_numeric(
            df[col], errors="coerce"
        )

    good = (
        (df["valid_coverage_fraction"] >= MIN_SOIL_COVERAGE)
        & (df["effective_cells"] >= MIN_EFFECTIVE_CELLS)
        & np.isfinite(df["rootzone_moisture_kg_m2"])
        & (df["rootzone_moisture_kg_m2"] >= 0)
    )

    df.loc[
        ~good, "rootzone_moisture_kg_m2"
    ] = np.nan

    soil = aggregate_jjas(
        df,
        "rootzone_moisture_kg_m2",
        "mean"
    )

    soil = soil.rename(
        columns={"value": "soil_jjas_mean_kg_m2"}
    )

    if soil.empty:
        print(
            "No complete quality-checked GLDAS seasons."
        )
        return None

    soil = empirical_percentiles(
        soil,
        "soil_jjas_mean_kg_m2",
        "soil_percentile"
    )

    if soil["soil_percentile"].notna().sum() == 0:
        print(
            "GLDAS has insufficient baseline years "
            "for joint screening."
        )
        return None

    return soil


# ============================================================
# MAP GENERATION
# ============================================================

def make_maps(rain, combined):

    if not BOUNDARY_FILE.exists():
        print("GeoJSON missing; maps skipped.")
        return

    import geopandas as gpd
    from matplotlib.patches import Patch

    boundaries = gpd.read_file(BOUNDARY_FILE)

    if (
        "dtname" not in boundaries.columns
        or len(boundaries) != 36
    ):
        raise ValueError(
            "Expected 36 boundaries with dtname."
        )

    chosen = rain[
        (rain["entity_type"] == "district")
        & (rain["year"] == MAP_YEAR)
    ]

    if set(chosen["entity"]) != set(boundaries["dtname"]):
        raise ValueError(
            "Rainfall districts do not match boundaries."
        )

    merged = boundaries.merge(
        chosen[["entity", "rain_percentile"]],
        left_on="dtname",
        right_on="entity",
        validate="one_to_one"
    )

    fig, ax = plt.subplots(figsize=(9, 8))

    merged.plot(
        column="rain_percentile",
        cmap="RdYlBu",
        vmin=0,
        vmax=100,
        legend=True,
        edgecolor="#444444",
        linewidth=0.5,
        legend_kwds={
            "label": "JJAS rainfall percentile"
        },
        ax=ax
    )

    low = merged[
        merged["rain_percentile"] <= LOW_PERCENTILE
    ]

    if not low.empty:
        low.boundary.plot(
            ax=ax, color="black", linewidth=1.8
        )

    ax.set_title(
        f"{MAP_YEAR}: historical low-rainfall screening\n"
        "Bold outlines: bottom 20% (2000–2024)"
    )

    ax.set_axis_off()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / f"{MAP_YEAR}_rain_percentiles.png",
        dpi=200
    )

    plt.close(fig)

    if combined is None:
        return

    selected = combined[
        (combined["entity_type"] == "district")
        & (combined["year"] == MAP_YEAR)
    ]

    joined = boundaries.merge(
        selected[["entity", "screening_signal"]],
        left_on="dtname",
        right_on="entity",
        validate="one_to_one"
    )

    palette = {
        "joint_low": "#7b1fa2",
        "rain_low_only": "#e69f00",
        "soil_low_only": "#3182bd",
        "neither_low": "#d9e2da",
        "soil_unavailable": "#aaaaaa"
    }

    fig, ax = plt.subplots(figsize=(9, 8))

    for label, color in palette.items():

        region = joined[
            joined["screening_signal"] == label
        ]

        if not region.empty:
            region.plot(
                ax=ax,
                color=color,
                edgecolor="#444444",
                linewidth=0.5
            )

    handles = [
        Patch(
            facecolor=color,
            label=label.replace("_", " ")
        )
        for label, color in palette.items()
        if (joined["screening_signal"] == label).any()
    ]

    ax.legend(
        handles=handles,
        loc="lower left",
        fontsize=8
    )

    ax.set_title(
        f"{MAP_YEAR}: rainfall and modeled "
        "soil-moisture conditions"
    )

    ax.set_axis_off()
    fig.tight_layout()

    fig.savefig(
        OUTPUT_DIR / f"{MAP_YEAR}_joint_signals.png",
        dpi=200
    )

    plt.close(fig)


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True, exist_ok=True
    )

    # 1. JJAS rainfall totals.
    rain = aggregate_jjas(
        IMERG_CSV,
        "monthly_precip_mm",
        "sum"
    )

    rain = rain.rename(
        columns={"value": "jjas_rain_mm"}
    )

    # 2. Within-district rainfall percentiles.
    rain = empirical_percentiles(
        rain,
        "jjas_rain_mm",
        "rain_percentile"
    )

    if rain["rain_percentile"].isna().any():
        raise ValueError(
            "Insufficient IMERG reference observations."
        )

    rain["rain_low20"] = (
        rain["rain_percentile"] <= LOW_PERCENTILE
    )

    rain.to_csv(
        OUTPUT_DIR / "jjas_rainfall_screen.csv",
        index=False
    )

    # 3. Count low-rainfall districts per year.
    yearly = rain[
        rain["entity_type"] == "district"
    ].groupby("year").agg(
        districts_with_low_rain=("rain_low20", "sum"),
        district_count=("entity", "nunique")
    ).reset_index()

    state = rain[
        rain["entity_type"] == "state"
    ][
        ["year", "jjas_rain_mm", "rain_percentile"]
    ]

    yearly = yearly.merge(
        state,
        on="year",
        validate="one_to_one"
    )

    yearly.to_csv(
        OUTPUT_DIR / "yearly_dry_rainfall_summary.csv",
        index=False
    )

    # 4. Optional GLDAS comparison.
    soil = load_soil()
    combined = None

    if soil is not None:

        combined = rain.merge(
            soil,
            on=["entity_type", "entity", "year"],
            how="left",
            validate="one_to_one"
        )

        def classify(row):

            if pd.isna(row["soil_percentile"]):
                return "soil_unavailable"

            rain_low = bool(row["rain_low20"])
            soil_low = (
                row["soil_percentile"]
                <= LOW_PERCENTILE
            )

            if rain_low and soil_low:
                return "joint_low"

            if rain_low:
                return "rain_low_only"

            if soil_low:
                return "soil_low_only"

            return "neither_low"

        combined["screening_signal"] = (
            combined.apply(classify, axis=1)
        )

        combined.to_csv(
            OUTPUT_DIR / "jjas_joint_screen.csv",
            index=False
        )

    # 5. Visualization.
    make_maps(rain, combined)

    # 6. Provenance and limitations.
    metadata = {
        "IMERG": (
            "GPM IMERG Final monthly V07B; "
            "doi:10.5067/GPM/IMERG/3B-MON/07"
        ),
        "GLDAS": (
            "GLDAS_NOAH025_M V2.1"
            if soil is not None else None
        ),
        "reference_period": [
            START_YEAR, END_YEAR
        ],
        "threshold_percentile": LOW_PERCENTILE,
        "AI_assistance": (
            "OpenAI ChatGPT assisted with script drafting."
        ),
        "limitations": [
            "Historical screening, not verified drought.",
            "Not a forecast or a calibrated risk probability.",
            "Reference period shorter than 30 years.",
            "GLDAS is modeled, not a direct observation.",
            "GLDAS and IMERG are not wholly independent.",
            "The empirical thresholds are in-sample."
        ]
    }

    (
        OUTPUT_DIR / "screening_metadata.json"
    ).write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8"
    )

    print("\nDRY-CONDITION SCREENING COMPLETE")
    print("-" * 50)

    print(
        f"Rainfall observations: {len(rain)} "
        "region-years"
    )

    print(
        "GLDAS comparison:",
        "available" if soil is not None else "not available"
    )

    example = yearly[
        yearly["year"] == MAP_YEAR
    ]

    if not example.empty:
        row = example.iloc[0]
        print(
            f"{MAP_YEAR}: "
            f"{int(row['districts_with_low_rain'])}/"
            f"{int(row['district_count'])} districts "
            "in their bottom rainfall quintile."
        )

    print(f"Output directory: {OUTPUT_DIR}")
    print(
        "WARNING: These are historical relative "
        "dry-condition indicators, not drought forecasts."
    )


if __name__ == "__main__":
    main()
