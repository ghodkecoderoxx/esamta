
"""
02b_plot_trend_significance.py

Visualize district Sen's slopes with a zero-centred colour scale.
Hatching marks districts passing modified Mann-Kendall FDR q < 0.05.

AI assistance: OpenAI ChatGPT assisted with code drafting.
"""

from pathlib import Path
import re

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
from matplotlib.cm import ScalarMappable


# ============================================================
# CONFIGURATION — CHANGE PATHS HERE IF NECESSARY
# ============================================================

ROOT = Path(__file__).resolve().parent

RESULTS = (
    ROOT / "data" / "district_series_outputs"
    / "analysis" / "trend_results.csv"
)

BOUNDARIES = ROOT / "MAHARASHTRA_DISTRICTS.geojson"

OUTPUT = (
    ROOT / "data" / "district_series_outputs"
    / "analysis" / "district_trends_with_significance.png"
)

P_VALUE_COLUMN = "mk_q_value"
ALPHA = 0.05


def normalize_name(value):
    return re.sub(
        r"[^a-z0-9]", "", str(value).lower()
    )


def main():

    data = pd.read_csv(RESULTS)

    required = {
        "period", "entity", "entity_type",
        "sen_slope_mm_per_decade", P_VALUE_COLUMN
    }

    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    districts = data[
        data["entity_type"] == "district"
    ].copy()

    districts["join_name"] = districts[
        "entity"
    ].map(normalize_name)

    boundaries = gpd.read_file(BOUNDARIES)

    if "dtname" not in boundaries.columns:
        raise ValueError("GeoJSON must contain dtname.")

    if len(boundaries) != 36:
        raise ValueError("Expected 36 district polygons.")

    boundaries["join_name"] = boundaries[
        "dtname"
    ].map(normalize_name)

    panels = {}

    for period in ["annual", "monsoon"]:

        part = districts[
            districts["period"] == period
        ].copy()

        if len(part) != 36:
            raise ValueError(
                f"Expected 36 district trends for {period}."
            )

        if part["join_name"].duplicated().any():
            raise ValueError("Duplicate district names.")

        merged = boundaries.merge(
            part[
                [
                    "join_name",
                    "sen_slope_mm_per_decade",
                    P_VALUE_COLUMN
                ]
            ],
            on="join_name",
            how="left",
            validate="one_to_one"
        )

        if merged["sen_slope_mm_per_decade"].isna().any():
            raise ValueError(
                f"Unmatched district boundaries: {period}"
            )

        panels[period] = merged

    # One symmetric colour range shared across both maps.
    maximum = max(
        float(
            np.abs(
                panel["sen_slope_mm_per_decade"]
            ).max()
        )
        for panel in panels.values()
    )

    norm = TwoSlopeNorm(
        vmin=-maximum,
        vcenter=0,
        vmax=maximum
    )

    fig, axes = plt.subplots(
        1, 2, figsize=(15, 7)
    )

    for ax, (period, geo) in zip(
        axes, panels.items()
    ):

        geo.plot(
            column="sen_slope_mm_per_decade",
            cmap="RdBu",
            norm=norm,
            edgecolor="#555555",
            linewidth=0.4,
            ax=ax
        )

        significant = geo[
            geo[P_VALUE_COLUMN] < ALPHA
        ]

        if not significant.empty:

            significant.plot(
                ax=ax,
                facecolor="none",
                edgecolor="black",
                linewidth=1.4,
                hatch="///"
            )

        ax.set_title(
            f"{period.title()}\n"
            f"{len(significant)}/36 districts: "
            "MK FDR q < 0.05"
        )

        ax.set_axis_off()

    scalar = ScalarMappable(
        norm=norm,
        cmap="RdBu"
    )

    fig.colorbar(
        scalar,
        ax=axes,
        shrink=0.72,
        label="Sen's slope (mm/decade)"
    )

    fig.suptitle(
        "Maharashtra precipitation trends, 1998–2024\n"
        "Hatching indicates modified MK q < 0.05",
        y=0.96
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    fig.savefig(
        OUTPUT,
        dpi=240,
        bbox_inches="tight"
    )

    plt.close(fig)

    print(f"Saved map: {OUTPUT}")


if __name__ == "__main__":
    main()
