"""
build_district_series.py

Build monthly Maharashtra district-level precipitation series
from NASA GPM IMERG Final monthly V07B NetCDF files.

Inputs:
  - Monthly .nc4 files
  - Maharashtra district GeoJSON

Outputs:
  district_series_outputs/processed/district_monthly.csv
  district_series_outputs/processed/monthly_grid.nc
  district_series_outputs/processed/build_metadata.json

Source product:
  NASA GPM IMERG Final monthly V07B
  DOI: 10.5067/GPM/IMERG/3B-MON/07

Boundary:
  datta07/INDIAN-SHAPEFILES
  Maharashtra district GeoJSON
  MIT License, copyright 2022
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr

from shapely.geometry import box


# ============================================================
# 1. USER CONFIGURATION
# ============================================================

# >>> EDIT THIS: Folder containing your monthly IMERG .nc4 files
DATA_DIR = Path(r"data/raw/0d33d2e8-a461-456c-9407-e5b928fd6e36")

# >>> EDIT THIS: Full path to Maharashtra district GeoJSON
BOUNDARY_PATH = Path(r"MAHARASHTRA_DISTRICTS.geojson")

# Output folder. You can leave this unchanged.
OUTPUT_DIR = Path("data/district_series_outputs")

# Minimum fraction of each district that must intersect
# the available IMERG grid.
# This is a configurable quality-control threshold.
MIN_GRID_COVERAGE = 0.98


# ============================================================
# 2. SOURCE AND PROCESSING METADATA
# ============================================================

PRODUCT_NAME = "NASA GPM IMERG Final monthly V07B"

PRODUCT_DOI = "10.5067/GPM/IMERG/3B-MON/07"

BOUNDARY_SOURCE = (
    "https://github.com/datta07/INDIAN-SHAPEFILES/blob/"
    "master/STATES/MAHARASHTRA/MAHARASHTRA_DISTRICTS.geojson"
)

BOUNDARY_LICENSE = "MIT License, copyright 2022"

AREA_CRS = "EPSG:6933"


# ============================================================
# 3. READ AND CONVERT ONE MONTH
# ============================================================

def interval_hours(time_bounds):
    """
    Calculate the exact duration represented by time_bnds.

    Source precipitation is a mean rate in mm/hr.
    Multiplying by the actual time interval gives mm.
    """

    interval = time_bounds[1] - time_bounds[0]

    if hasattr(interval, "total_seconds"):
        seconds = interval.total_seconds()
    else:
        seconds = pd.to_timedelta(interval).total_seconds()

    hours = float(seconds) / 3600.0

    if not np.isfinite(hours) or hours <= 0:
        raise ValueError(
            f"Invalid monthly time interval: {time_bounds}"
        )

    return hours


def read_month(file_path):
    """
    Read one monthly NetCDF file.

    The scientific variables are stored in the /Grid group.
    """

    with xr.open_dataset(
        file_path,
        group="Grid",
        engine="netcdf4",
    ) as dataset:

        required_variables = {
            "precipitation",
            "lat",
            "lon",
            "time",
            "time_bnds",
            "lat_bnds",
            "lon_bnds",
        }

        missing_variables = (
            required_variables.difference(dataset.variables)
        )

        if missing_variables:
            raise ValueError(
                f"{file_path.name}: missing variables "
                f"{sorted(missing_variables)}"
            )

        precipitation = dataset["precipitation"]

        source_units = (
            str(precipitation.attrs.get("units", ""))
            .strip()
            .lower()
            .replace(" ", "")
        )

        accepted_units = {
            "mm/hr",
            "mmh-1",
            "mmhour-1",
        }

        if source_units not in accepted_units:
            raise ValueError(
                f"{file_path.name}: unexpected precipitation "
                f"units: {source_units!r}"
            )

        # Read precipitation as (latitude, longitude).
        precipitation_rate = (
            precipitation
            .isel(time=0)
            .transpose("lat", "lon")
            .values
            .astype("float64")
        )

        latitude = dataset["lat"].values.astype("float64")
        longitude = dataset["lon"].values.astype("float64")

        latitude_bounds = (
            dataset["lat_bnds"].values.astype("float64")
        )

        longitude_bounds = (
            dataset["lon_bnds"].values.astype("float64")
        )

        time_bounds = dataset["time_bnds"].values[0]
        timestamp = dataset["time"].values[0]

        duration_hours = interval_hours(time_bounds)

        # Check that the timestamp lies inside its time interval.
        if not (time_bounds[0] <= timestamp < time_bounds[1]):
            raise ValueError(
                f"{file_path.name}: timestamp is outside "
                "its time bounds."
            )

        # Convert the timestamp to the first day of its month.
        if hasattr(timestamp, "strftime"):
            month = pd.Timestamp(
                timestamp.strftime("%Y-%m-01")
            )
        else:
            month = (
                pd.Timestamp(timestamp)
                .to_period("M")
                .to_timestamp()
            )

    if precipitation_rate.shape != (
        len(latitude),
        len(longitude),
    ):
        raise ValueError(
            f"{file_path.name}: unexpected precipitation shape."
        )

    if not np.isfinite(precipitation_rate).any():
        raise ValueError(
            f"{file_path.name}: no valid precipitation observations."
        )

    if np.any(
        precipitation_rate[np.isfinite(precipitation_rate)] < 0
    ):
        raise ValueError(
            f"{file_path.name}: negative precipitation detected."
        )

    # Convert mean precipitation rate into monthly accumulation.
    monthly_precipitation = (
        precipitation_rate * duration_hours
    )

    return {
        "file": str(file_path),
        "month": month,
        "interval_hours": duration_hours,
        "rate_mm_hr": precipitation_rate,
        "precipitation_mm": monthly_precipitation,
        "latitude": latitude,
        "longitude": longitude,
        "latitude_bounds": latitude_bounds,
        "longitude_bounds": longitude_bounds,
    }


# ============================================================
# 4. LOAD AND VALIDATE DISTRICT BOUNDARIES
# ============================================================

def load_districts(boundary_path):
    """
    Load Maharashtra district polygons.

    Expected GeoJSON fields:
      dtname = district name
      stname = state name
    """

    districts = gpd.read_file(boundary_path)

    required_fields = {"dtname", "stname"}

    missing_fields = required_fields.difference(
        districts.columns
    )

    if missing_fields:
        raise ValueError(
            f"GeoJSON missing fields: {sorted(missing_fields)}"
        )

    # Retain Maharashtra features only.
    districts = districts[
        districts["stname"]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("MAHARASHTRA")
    ].copy()

    if districts.empty:
        raise ValueError(
            "No Maharashtra features found in the GeoJSON."
        )

    if districts.crs is None:
        raise ValueError(
            "GeoJSON CRS is missing. Do not guess its CRS."
        )

    districts = districts.to_crs("EPSG:4326")

    districts["district"] = (
        districts["dtname"]
        .astype(str)
        .str.strip()
    )

    if districts["district"].duplicated().any():
        raise ValueError(
            "Duplicate district names detected."
        )

    if districts.geometry.is_empty.any():
        raise ValueError(
            "Empty district geometries detected."
        )

    if not districts.geometry.is_valid.all():
        districts["geometry"] = (
            districts.geometry.make_valid()
        )

    if not districts.geometry.is_valid.all():
        raise ValueError(
            "Some district geometries remain invalid."
        )

    if len(districts) != 36:
        raise ValueError(
            f"Expected 36 Maharashtra districts, "
            f"found {len(districts)}. "
            "Check the boundary source and vintage."
        )

    return districts[["district", "geometry"]].copy()


# ============================================================
# 5. BUILD GRID-CELL POLYGONS
# ============================================================

def build_grid_cells(
    latitude,
    longitude,
    latitude_bounds,
    longitude_bounds,
):
    """
    Convert the IMERG grid into individual cell polygons.

    Grid IDs follow row-major order:
      grid_id = latitude_index * number_of_longitudes
                 + longitude_index
    """

    number_of_latitudes = len(latitude)
    number_of_longitudes = len(longitude)

    grid_ids = []
    cell_geometries = []

    for latitude_index in range(number_of_latitudes):

        south, north = sorted(
            latitude_bounds[latitude_index].tolist()
        )

        for longitude_index in range(number_of_longitudes):

            west, east = sorted(
                longitude_bounds[longitude_index].tolist()
            )

            grid_id = (
                latitude_index * number_of_longitudes
                + longitude_index
            )

            grid_ids.append(grid_id)

            cell_geometries.append(
                box(west, south, east, north)
            )

    cells = gpd.GeoDataFrame(
        {"grid_id": grid_ids},
        geometry=cell_geometries,
        crs="EPSG:4326",
    )

    return cells.to_crs(AREA_CRS)


# ============================================================
# 6. CALCULATE DISTRICT AND STATE SPATIAL WEIGHTS
# ============================================================

def build_area_weights(
    latitude,
    longitude,
    latitude_bounds,
    longitude_bounds,
    districts,
    min_coverage=MIN_GRID_COVERAGE,
):
    """
    Calculate equal-area intersections between grid cells
    and district polygons.

    Also construct a separate statewide weight matrix using
    the dissolved union of all district polygons.

    This avoids double-counting overlapping district areas
    in the statewide aggregation.
    """

    cells = build_grid_cells(
        latitude,
        longitude,
        latitude_bounds,
        longitude_bounds,
    )

    districts_equal_area = districts.to_crs(AREA_CRS)

    district_names = districts["district"].tolist()

    number_of_cells = (
        len(latitude) * len(longitude)
    )

    # --------------------------------------------------------
    # 6A. Check district polygon overlap
    # --------------------------------------------------------

    individual_district_area = (
        districts_equal_area.geometry.area.sum()
    )

    state_geometry = (
        districts_equal_area.geometry.union_all()
    )

    union_area = state_geometry.area

    overlap_area = max(
        0.0,
        individual_district_area - union_area,
    )

    overlap_fraction = (
        overlap_area / individual_district_area
    )

    # A material overlap means the supplied district polygons
    # should be investigated before aggregating statewide.
    overlap_tolerance = 1e-5

    if overlap_fraction > overlap_tolerance:
        raise ValueError(
            "District polygons overlap materially. "
            f"Estimated overlap fraction: {overlap_fraction:.6f}. "
            "Inspect the GeoJSON topology before proceeding."
        )

    # --------------------------------------------------------
    # 6B. Intersect grid cells with individual districts
    # --------------------------------------------------------

    district_intersections = gpd.overlay(
        cells,
        districts_equal_area,
        how="intersection",
        keep_geom_type=True,
    )

    if district_intersections.empty:
        raise ValueError(
            "No overlap between IMERG grid and district polygons."
        )

    district_intersections["overlap_area_m2"] = (
        district_intersections.geometry.area
    )

    district_grouped = (
        district_intersections
        .groupby(["district", "grid_id"])
        ["overlap_area_m2"]
        .sum()
        .reset_index()
    )

    district_weights = (
        district_grouped
        .pivot(
            index="district",
            columns="grid_id",
            values="overlap_area_m2",
        )
        .reindex(
            index=district_names,
            columns=range(number_of_cells),
        )
        .fillna(0.0)
        .to_numpy(dtype="float64")
    )

    district_areas = (
        districts_equal_area
        .set_index("district")
        .geometry.area
        .reindex(district_names)
        .to_numpy(dtype="float64")
    )

    district_grid_coverage = (
        district_weights.sum(axis=1) / district_areas
    )
    
    district_grid_coverage = np.clip(
      district_grid_coverage,
      0.0,
      1.0
    )

    district_coverage_report = {
        name: float(value)
        for name, value in zip(
            district_names,
            district_grid_coverage,
        )
    }

    insufficient_coverage = {
        name: value
        for name, value in district_coverage_report.items()
        if value < min_coverage
    }

    if insufficient_coverage:
        raise ValueError(
            "Insufficient grid coverage for one or more districts. "
            f"Minimum required: {min_coverage:.1%}. "
            f"Below threshold: {insufficient_coverage}. "
            "Inspect the grid extent and boundary geometry."
        )

    # --------------------------------------------------------
    # 6C. Build statewide weights from dissolved union
    # --------------------------------------------------------

    state_polygon = gpd.GeoDataFrame(
        {"entity": ["Maharashtra"]},
        geometry=[state_geometry],
        crs=AREA_CRS,
    )

    state_intersections = gpd.overlay(
        cells,
        state_polygon,
        how="intersection",
        keep_geom_type=True,
    )

    if state_intersections.empty:
        raise ValueError(
            "No overlap between IMERG grid and statewide polygon."
        )

    state_intersections["overlap_area_m2"] = (
        state_intersections.geometry.area
    )

    state_grouped = (
        state_intersections
        .groupby("grid_id")["overlap_area_m2"]
        .sum()
    )

    state_weights = (
        state_grouped
        .reindex(range(number_of_cells))
        .fillna(0.0)
        .to_numpy(dtype="float64")
        .reshape(1, -1)
    )

    state_area = np.asarray(
        [union_area],
        dtype="float64",
    )

    state_grid_coverage = float(
        state_weights.sum() / union_area
    ) 
    
    state_grid_coverage = np.clip(
      state_grid_coverage,
      0.0,
      1.0
    )

    if state_grid_coverage < min_coverage:
        raise ValueError(
            "Insufficient IMERG grid coverage of Maharashtra. "
            f"Coverage: {state_grid_coverage:.2%}; "
            f"minimum required: {min_coverage:.1%}."
        )

    return {
        "district_names": district_names,
        "district_weights": district_weights,
        "district_areas": district_areas,
        "district_grid_coverage": district_coverage_report,
        "state_weights": state_weights,
        "state_area": state_area,
        "state_grid_coverage": state_grid_coverage,
        "district_overlap_fraction": float(overlap_fraction),
    }


# ============================================================
# 7. CALCULATE AREA-WEIGHTED PRECIPITATION
# ============================================================

def weighted_means(
    grid_values,
    area_weights,
    full_polygon_areas,
):
    """
    Calculate area-weighted precipitation means.

    Parameters
    ----------
    grid_values:
        Array of shape (time, grid_cell).

    area_weights:
        Array of shape (entity, grid_cell).

    full_polygon_areas:
        Full area of each district or statewide polygon.

    Returns
    -------
    precipitation_means:
        Area-weighted precipitation, shape (time, entity).

    valid_coverage:
        Valid observed area divided by the full polygon area,
        shape (time, entity).
    """

    valid_cells = np.isfinite(grid_values)

    # Replace missing grid observations with zero only for
    # numerator calculation; their area is excluded below.
    safe_values = np.where(
        valid_cells,
        grid_values,
        0.0,
    )

    numerator = np.einsum(
        "tc,ec->te",
        safe_values,
        area_weights,
    )

    valid_area = np.einsum(
        "tc,ec->te",
        valid_cells.astype("float64"),
        area_weights,
    )

    precipitation_means = np.divide(
        numerator,
        valid_area,
        out=np.full(
            numerator.shape,
            np.nan,
            dtype="float64",
        ),
        where=valid_area > 0,
    )

    valid_coverage = (
        valid_area / full_polygon_areas[None, :]
    )

    valid_coverage = np.clip(
        valid_coverage,
        0.0,
        1.0,
    )

    return precipitation_means, valid_coverage


# ============================================================
# 8. VALIDATE MONTHLY FILE SEQUENCE AND GRID CONSISTENCY
# ============================================================

def validate_month_sequence(monthly_data):
    """Check for duplicate months and missing monthly files."""

    monthly_data.sort(
        key=lambda item: item["month"]
    )

    month_index = pd.DatetimeIndex(
        [item["month"] for item in monthly_data]
    )

    if month_index.has_duplicates:
        raise ValueError(
            "Duplicate months detected in input files."
        )

    expected_months = pd.date_range(
        month_index.min(),
        month_index.max(),
        freq="MS",
    )

    if not month_index.equals(expected_months):
        missing_months = (
            expected_months
            .difference(month_index)
            .strftime("%Y-%m")
            .tolist()
        )

        raise ValueError(
            f"Missing months detected: {missing_months}"
        )

    return month_index


def validate_grid_consistency(monthly_data):
    """Ensure every file uses identical coordinates and bounds."""

    reference = monthly_data[0]

    grid_fields = (
        "latitude",
        "longitude",
        "latitude_bounds",
        "longitude_bounds",
    )

    for month in monthly_data[1:]:

        for field in grid_fields:

            if not np.array_equal(
                month[field],
                reference[field],
            ):
                raise ValueError(
                    f"Grid mismatch in {month['file']}: {field}"
                )

    return reference


# ============================================================
# 9. BUILD OUTPUT TABLE
# ============================================================

def build_monthly_panel(
    month_index,
    district_names,
    district_precipitation,
    district_valid_coverage,
    district_grid_coverage,
    state_precipitation,
    state_valid_coverage,
    state_grid_coverage,
    interval_hours_by_month,
):
    """
    Create one tidy table containing district and state records.

    spatial_coverage_fraction:
        Month-specific fraction of the full polygon area
        represented by valid precipitation observations.

    grid_coverage_fraction:
        Fixed fraction of the full polygon intersected by
        the available IMERG grid.
    """

    rows = []

    for time_index, month in enumerate(month_index):

        month_string = month.strftime("%Y-%m-%d")

        for district_index, district_name in enumerate(
            district_names
        ):

            rows.append({
                "month": month_string,
                "entity_type": "district",
                "entity": district_name,
                "monthly_precip_mm": float(
                    district_precipitation[
                        time_index,
                        district_index,
                    ]
                ),
                "interval_hours": float(
                    interval_hours_by_month[time_index]
                ),
                "grid_coverage_fraction": float(
                    district_grid_coverage[district_name]
                ),
                "spatial_coverage_fraction": float(
                    district_valid_coverage[
                        time_index,
                        district_index,
                    ]
                ),
            })

        rows.append({
            "month": month_string,
            "entity_type": "state",
            "entity": "Maharashtra",
            "monthly_precip_mm": float(
                state_precipitation[time_index, 0]
            ),
            "interval_hours": float(
                interval_hours_by_month[time_index]
            ),
            "grid_coverage_fraction": float(
                state_grid_coverage
            ),
            "spatial_coverage_fraction": float(
                state_valid_coverage[time_index, 0]
            ),
        })

    return pd.DataFrame(rows)


# ============================================================
# 10. SAVE OUTPUTS
# ============================================================

def save_outputs(
    output_directory,
    monthly_panel,
    monthly_data,
    reference_grid,
    metadata,
):
    """Save the district panel, gridded NetCDF and metadata."""

    processed_directory = (
        output_directory / "processed"
    )

    processed_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # 10A. District and statewide monthly CSV
    # --------------------------------------------------------

    panel_path = (
        processed_directory / "district_monthly.csv"
    )

    monthly_panel.to_csv(
        panel_path,
        index=False,
    )

    # --------------------------------------------------------
    # 10B. Gridded NetCDF
    # --------------------------------------------------------

    time_index = pd.DatetimeIndex(
        [item["month"] for item in monthly_data]
    )

    rate_grid = np.stack([
        item["rate_mm_hr"]
        for item in monthly_data
    ]).astype("float32")

    precipitation_grid = np.stack([
        item["precipitation_mm"]
        for item in monthly_data
    ]).astype("float32")

    interval_hours_array = np.asarray([
        item["interval_hours"]
        for item in monthly_data
    ], dtype="float32")

    grid_dataset = xr.Dataset(
        data_vars={
            "precipitation_rate_mm_hr": (
                ("time", "lat", "lon"),
                rate_grid,
            ),
            "monthly_precipitation_mm": (
                ("time", "lat", "lon"),
                precipitation_grid,
            ),
            "interval_hours": (
                ("time",),
                interval_hours_array,
            ),
        },
        coords={
            "time": time_index,
            "lat": reference_grid["latitude"],
            "lon": reference_grid["longitude"],
        },
        attrs={
            "source": PRODUCT_NAME,
            "doi": PRODUCT_DOI,
            "conversion": (
                "Monthly mean rate multiplied by the exact "
                "time_bnds duration in hours."
            ),
            "boundary_source": BOUNDARY_SOURCE,
            "boundary_license": BOUNDARY_LICENSE,
            "area_weighting_crs": AREA_CRS,
        },
    )

    grid_path = (
        processed_directory / "monthly_grid.nc"
    )

    grid_dataset.to_netcdf(
        grid_path,
        engine="netcdf4",
        encoding={
            "precipitation_rate_mm_hr": {
                "zlib": True,
                "complevel": 4,
            },
            "monthly_precipitation_mm": {
                "zlib": True,
                "complevel": 4,
            },
            "interval_hours": {
                "zlib": True,
                "complevel": 4,
            },
        },
    )

    # --------------------------------------------------------
    # 10C. Processing metadata
    # --------------------------------------------------------

    metadata_path = (
        processed_directory / "build_metadata.json"
    )

    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    return panel_path, grid_path, metadata_path


# ============================================================
# 11. MAIN PIPELINE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    # Configuration defaults are defined at the top.
    # Command-line arguments can override them if required.
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
    )

    parser.add_argument(
        "--boundary",
        type=Path,
        default=BOUNDARY_PATH,
    )

    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUTPUT_DIR,
    )

    parser.add_argument(
        "--min-coverage",
        type=float,
        default=MIN_GRID_COVERAGE,
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # 11A. Validate input paths and settings
    # --------------------------------------------------------

    if not args.data_dir.exists():
        raise FileNotFoundError(
            f"IMERG data directory not found: {args.data_dir}\n"
            "Edit DATA_DIR at the top of the script."
        )

    if not args.data_dir.is_dir():
        raise NotADirectoryError(
            f"IMERG input path is not a directory: {args.data_dir}"
        )

    if not args.boundary.exists():
        raise FileNotFoundError(
            f"District GeoJSON not found: {args.boundary}\n"
            "Edit BOUNDARY_PATH at the top of the script."
        )

    if not 0 < args.min_coverage <= 1:
        raise ValueError(
            "--min-coverage must be greater than 0 and at most 1."
        )

    # --------------------------------------------------------
    # 11B. Discover and read monthly files
    # --------------------------------------------------------

    input_files = sorted(
        args.data_dir.rglob("*.nc4")
    )

    if not input_files:
        raise FileNotFoundError(
            f"No .nc4 files found in {args.data_dir}"
        )

    print("=" * 60)
    print("MAHARASHTRA IMERG DISTRICT SERIES")
    print("=" * 60)

    print(f"\nInput files found: {len(input_files)}")
    print("Reading monthly NetCDF files...")

    monthly_data = [
        read_month(file_path)
        for file_path in input_files
    ]

    month_index = validate_month_sequence(
        monthly_data
    )

    reference_grid = validate_grid_consistency(
        monthly_data
    )

    print(
        f"Monthly coverage: "
        f"{month_index.min():%Y-%m} to "
        f"{month_index.max():%Y-%m}"
    )

    print(
        f"Monthly files validated: {len(monthly_data)}"
    )

    # --------------------------------------------------------
    # 11C. Load district boundaries
    # --------------------------------------------------------

    print("\nLoading Maharashtra district boundaries...")

    districts = load_districts(
        args.boundary
    )

    print(
        f"District features loaded: {len(districts)}"
    )

    # --------------------------------------------------------
    # 11D. Construct area weights
    # --------------------------------------------------------

    print("\nBuilding equal-area spatial weights...")

    spatial_weights = build_area_weights(
        latitude=reference_grid["latitude"],
        longitude=reference_grid["longitude"],
        latitude_bounds=reference_grid["latitude_bounds"],
        longitude_bounds=reference_grid["longitude_bounds"],
        districts=districts,
        min_coverage=args.min_coverage,
    )

    district_names = spatial_weights["district_names"]

    print("District grid-coverage check passed.")

    print(
        "Statewide grid coverage: "
        f"{spatial_weights['state_grid_coverage']:.2%}"
    )

    print(
        "District polygon overlap fraction: "
        f"{spatial_weights['district_overlap_fraction']:.8f}"
    )

    # --------------------------------------------------------
    # 11E. Prepare precipitation arrays
    # --------------------------------------------------------

    print("\nPreparing precipitation arrays...")

    # Keep float64 for spatial aggregation and analysis.
    monthly_grid = np.stack([
        item["precipitation_mm"]
        for item in monthly_data
    ]).astype("float64")

    flat_monthly_grid = monthly_grid.reshape(
        len(monthly_data),
        -1,
    )

    interval_hours_by_month = np.asarray([
        item["interval_hours"]
        for item in monthly_data
    ], dtype="float64")

    # --------------------------------------------------------
    # 11F. Calculate district precipitation
    # --------------------------------------------------------

    print("Calculating district precipitation series...")

    district_precipitation, district_valid_coverage = (
        weighted_means(
            grid_values=flat_monthly_grid,
            area_weights=spatial_weights["district_weights"],
            full_polygon_areas=spatial_weights["district_areas"],
        )
    )

    # --------------------------------------------------------
    # 11G. Calculate statewide precipitation
    # --------------------------------------------------------

    print("Calculating statewide precipitation series...")

    state_precipitation, state_valid_coverage = (
        weighted_means(
            grid_values=flat_monthly_grid,
            area_weights=spatial_weights["state_weights"],
            full_polygon_areas=spatial_weights["state_area"],
        )
    )

    # --------------------------------------------------------
    # 11H. Build tidy monthly panel
    # --------------------------------------------------------

    print("Building monthly output table...")

    monthly_panel = build_monthly_panel(
        month_index=month_index,
        district_names=district_names,
        district_precipitation=district_precipitation,
        district_valid_coverage=district_valid_coverage,
        district_grid_coverage=(
            spatial_weights["district_grid_coverage"]
        ),
        state_precipitation=state_precipitation,
        state_valid_coverage=state_valid_coverage,
        state_grid_coverage=(
            spatial_weights["state_grid_coverage"]
        ),
        interval_hours_by_month=interval_hours_by_month,
    )

    # --------------------------------------------------------
    # 11I. Build metadata
    # --------------------------------------------------------

    metadata = {
        "source_product": PRODUCT_NAME,
        "doi": PRODUCT_DOI,
        "input_file_count": len(input_files),
        "first_month": month_index.min().strftime("%Y-%m"),
        "last_month": month_index.max().strftime("%Y-%m"),
        "derived_units": "mm/month",
        "source_units": "mm/hr",
        "conversion": (
            "Monthly mean precipitation rate multiplied by "
            "the exact time_bnds duration in hours."
        ),
        "boundary_source": BOUNDARY_SOURCE,
        "boundary_license": BOUNDARY_LICENSE,
        "boundary_feature_count": len(district_names),
        "district_names": district_names,
        "area_weighting_crs": AREA_CRS,
        "minimum_grid_coverage_threshold": args.min_coverage,
        "district_grid_coverage_fraction": (
            spatial_weights["district_grid_coverage"]
        ),
        "state_grid_coverage_fraction": (
            spatial_weights["state_grid_coverage"]
        ),
        "district_polygon_overlap_fraction": (
            spatial_weights["district_overlap_fraction"]
        ),
        "quality_filter": (
            "No precipitationQualityIndex threshold applied. "
            "No undocumented quality threshold was assumed."
        ),
        "coverage_definition": {
            "grid_coverage_fraction": (
                "Fixed fraction of the full polygon area "
                "intersected by the available IMERG grid."
            ),
            "spatial_coverage_fraction": (
                "Month-specific fraction of the full polygon area "
                "represented by valid precipitation observations."
            ),
        },
        "statewide_aggregation": (
            "Area-weighted mean calculated using the dissolved "
            "union of all Maharashtra district polygons. "
            "District weights are not summed."
        ),
        "si_assistance": (
            "OpenAI ChatGPT assisted with script drafting and "
            "documentation. Processing and results require "
            "independent execution and verification."
        ),
        "limitations": [
            "District polygons are fixed across the full time series.",
            "IMERG is a satellite-gauge precipitation estimate.",
            "Spatial coverage depends on the supplied grid subset.",
            "Boundary provenance and topology should be documented.",
            "A valid spatial average does not establish statistical "
            "significance or a climate trend.",
        ],
    }

    # --------------------------------------------------------
    # 11J. Save all outputs
    # --------------------------------------------------------

    print("\nSaving outputs...")

    panel_path, grid_path, metadata_path = save_outputs(
        output_directory=args.out_dir,
        monthly_panel=monthly_panel,
        monthly_data=monthly_data,
        reference_grid=reference_grid,
        metadata=metadata,
    )

    # --------------------------------------------------------
    # 11K. Completion summary
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("PROCESSING COMPLETE")
    print("=" * 60)

    print(f"Months processed: {len(monthly_data)}")
    print(f"Districts processed: {len(district_names)}")
    print(f"Monthly panel rows: {len(monthly_panel)}")

    print("\nOutput files:")
    print(f"  District panel: {panel_path}")
    print(f"  Gridded data:   {grid_path}")
    print(f"  Metadata:       {metadata_path}")

    print("\nCoverage columns:")
    print("  grid_coverage_fraction")
    print("  spatial_coverage_fraction")

    print("\nNext step: validate the CSV and metadata before")
    print("running the trend-analysis script.")


if __name__ == "__main__":
    main()
