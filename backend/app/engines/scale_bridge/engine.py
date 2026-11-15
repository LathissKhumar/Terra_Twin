"""Metric local-grid harmonization for cross-body terrain morphology."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyproj
import rasterio
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.warp import reproject

from app.core.exceptions import (
    CoordinateTransformationError,
    IncompatibleResolutionError,
    IncompatibleVerticalUnitsError,
    InvalidRasterError,
)
from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.observation_counts import ObservationCountsManifest
from app.domain.schemas.scale_bridge import (
    CoverageReport,
    GeographicCenter,
    ObservationCountsReport,
    ScaleBridgeConfig,
    ScaleBridgeReport,
    SourceGridReport,
)
from app.engines.data_ingestion.ingestion import sha256_file

OUTPUT_NODATA = np.float32(-3.402823466e38)
MAX_TARGET_CELLS = 4_000_000
_VERTICAL_TO_METRES = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "km": 1_000.0,
    "kilometer": 1_000.0,
    "kilometers": 1_000.0,
    "kilometre": 1_000.0,
    "kilometres": 1_000.0,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
}


@dataclass(frozen=True)
class ScaleBridgeResult:
    """In-memory paired surfaces, paired validity mask and persisted run report."""

    planetary_relative_elevation_m: np.ndarray
    earth_relative_elevation_m: np.ndarray
    common_support_mask: np.ndarray | None
    planetary_local_crs: str
    earth_local_crs: str
    report: ScaleBridgeReport
    artifact_paths: dict[str, Path]


@dataclass(frozen=True)
class ObservationCountSource:
    """Validated ancillary observation counts aligned to a planetary DEM."""

    raster_path: Path
    manifest: ObservationCountsManifest
    open_path: Path | None = None


@dataclass(frozen=True)
class _SourceGrid:
    crs: CRS
    local_crs: CRS
    local_crs_text: str
    x_spacing_m: float
    y_spacing_m: float
    effective_resolution_m: float | None
    horizontal_units: str
    geographic_bounds: tuple[float, float, float, float]


def _unit_to_metres(unit: str) -> float:
    factor = _VERTICAL_TO_METRES.get(unit.strip().casefold())
    if factor is None:
        raise IncompatibleVerticalUnitsError(
            "Vertical units cannot be converted to metres; provide a supported linear unit"
        )
    return factor


def _local_metric_crs(source_crs: CRS, center: GeographicCenter) -> CRS:
    geodetic = source_crs.geodetic_crs
    if geodetic is None:
        raise CoordinateTransformationError("Source CRS has no identifiable geodetic CRS")
    ellipsoid = geodetic.ellipsoid
    if ellipsoid is None:
        raise CoordinateTransformationError("Source CRS does not define an ellipsoid")
    semi_major = ellipsoid.semi_major_metre
    semi_minor = ellipsoid.semi_minor_metre
    if not all(math.isfinite(value) and value > 0 for value in (semi_major, semi_minor)):
        raise CoordinateTransformationError("Source CRS ellipsoid is unavailable or invalid")
    try:
        return CRS.from_proj4(
            f"+proj=aeqd +lat_0={center.latitude:.12f} +lon_0={center.longitude:.12f} "
            f"+a={semi_major:.12f} +b={semi_minor:.12f} +units=m +no_defs +type=crs"
        )
    except Exception as exc:
        raise CoordinateTransformationError("Could not construct a local metric CRS") from exc


def _inspect_source(
    raster_path: Path,
    open_path: Path | None,
    manifest: DatasetManifest,
    center: GeographicCenter,
) -> _SourceGrid:
    if manifest.processing_status != "validated":
        raise InvalidRasterError("ScaleBridge accepts only validated source manifests")
    if not raster_path.is_file():
        raise InvalidRasterError("Source raster file is unavailable")
    if sha256_file(raster_path) != manifest.checksum_sha256:
        raise InvalidRasterError("Raster checksum does not match its provenance manifest")
    try:
        declared_crs = CRS.from_user_input(manifest.crs)
        with rasterio.open(open_path or raster_path) as dataset:
            if dataset.crs is None:
                raise InvalidRasterError("Input raster has no CRS")
            actual_crs = CRS.from_wkt(dataset.crs.to_wkt())
            if not actual_crs.equals(declared_crs):
                raise InvalidRasterError("Raster CRS differs from its validated manifest")
            if (
                dataset.width != manifest.width
                or dataset.height != manifest.height
                or dataset.count != 1
            ):
                raise InvalidRasterError("Raster dimensions or band count differ from manifest")
            actual_bounds = (
                dataset.bounds.left,
                dataset.bounds.bottom,
                dataset.bounds.right,
                dataset.bounds.top,
            )
            if any(
                not math.isclose(actual, declared, rel_tol=1e-10, abs_tol=1e-8)
                for actual, declared in zip(actual_bounds, manifest.bounds, strict=True)
            ):
                raise InvalidRasterError("Raster bounds differ from its validated manifest")
            actual_spacing = (abs(dataset.res[0]), abs(dataset.res[1]))
            if any(
                not math.isclose(actual, declared, rel_tol=1e-10, abs_tol=1e-10)
                for actual, declared in zip(
                    actual_spacing,
                    (manifest.pixel_resolution_x, manifest.pixel_resolution_y),
                    strict=True,
                )
            ):
                raise InvalidRasterError("Raster pixel spacing differs from its manifest")
            if dataset.dtypes[0] != manifest.dtype:
                raise InvalidRasterError("Raster data type differs from its validated manifest")
            if dataset.nodata != manifest.nodata:
                raise InvalidRasterError("Raster NoData metadata differs from its manifest")
            geodetic = actual_crs.geodetic_crs
            if geodetic is None:
                raise CoordinateTransformationError("Input CRS lacks a geodetic coordinate system")
            local_crs = _local_metric_crs(actual_crs, center)
            geographic_bounds = Transformer.from_crs(
                actual_crs, geodetic, always_xy=True
            ).transform_bounds(*manifest.bounds, densify_pts=41)
            to_source = Transformer.from_crs(geodetic, actual_crs, always_xy=True)
            to_local = Transformer.from_crs(actual_crs, local_crs, always_xy=True)
            source_x, source_y = to_source.transform(center.longitude, center.latitude)
            if not math.isfinite(source_x) or not math.isfinite(source_y):
                raise CoordinateTransformationError(
                    "Center transform produced non-finite coordinates"
                )
            row, col = dataset.index(source_x, source_y)
            if row < 0 or col < 0 or row >= dataset.height or col >= dataset.width:
                raise IncompatibleResolutionError("Requested center lies outside the source raster")
            px, py = dataset.transform @ (col + 0.5, row + 0.5)
            px_next, py_next = dataset.transform @ (col + 1.5, row + 0.5)
            px_down, py_down = dataset.transform @ (col + 0.5, row + 1.5)
            local_points = [
                to_local.transform(x, y)
                for x, y in ((px, py), (px_next, py_next), (px_down, py_down))
            ]
            x_spacing = math.dist(local_points[0], local_points[1])
            y_spacing = math.dist(local_points[0], local_points[2])
            if min(x_spacing, y_spacing) <= 0 or not all(
                math.isfinite(value) for value in (x_spacing, y_spacing)
            ):
                raise CoordinateTransformationError("Ground pixel spacing could not be measured")
            units = actual_crs.axis_info[0].unit_name if actual_crs.axis_info else "unknown"
    except (InvalidRasterError, CoordinateTransformationError, IncompatibleResolutionError):
        raise
    except Exception as exc:
        raise InvalidRasterError("Could not inspect or transform the source raster") from exc

    effective = manifest.product_metadata.get("effective_resolution_m")
    effective_m: float | None = None
    if effective is not None:
        try:
            effective_m = float(effective)
        except (TypeError, ValueError) as exc:
            raise InvalidRasterError("Documented effective resolution is not numeric") from exc
        if not math.isfinite(effective_m) or effective_m <= 0:
            raise InvalidRasterError("Documented effective resolution must be positive and finite")
    return _SourceGrid(
        crs=actual_crs,
        local_crs=local_crs,
        local_crs_text=local_crs.to_wkt(),
        x_spacing_m=x_spacing,
        y_spacing_m=y_spacing,
        effective_resolution_m=effective_m,
        horizontal_units=units,
        geographic_bounds=geographic_bounds,
    )


def _target_transform(width: int, height: int, resolution_m: float) -> Affine:
    return Affine(
        resolution_m,
        0,
        -(width * resolution_m) / 2,
        0,
        -resolution_m,
        (height * resolution_m) / 2,
    )


def _warp_source(
    path: Path,
    open_path: Path | None,
    manifest: DatasetManifest,
    grid: _SourceGrid,
    destination_transform: Affine,
    width: int,
    height: int,
    minimum_valid_fraction: float,
    observation_counts: ObservationCountSource | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    factor = _unit_to_metres(manifest.vertical_units)
    try:
        with rasterio.open(open_path or path) as dataset:
            valid_source = dataset.read_masks(1)
            np.greater(valid_source, 0, out=valid_source, casting="unsafe")
            source = dataset.read(1, out_dtype="float32")
            source *= factor
            if observation_counts is not None:
                counts_path = observation_counts.raster_path
                if sha256_file(counts_path) != observation_counts.manifest.checksum_sha256:
                    raise InvalidRasterError("Observation-count checksum differs from its manifest")
                with rasterio.open(observation_counts.open_path or counts_path) as counts_ds:
                    count_manifest = observation_counts.manifest
                    count_bounds = (
                        counts_ds.bounds.left,
                        counts_ds.bounds.bottom,
                        counts_ds.bounds.right,
                        counts_ds.bounds.top,
                    )
                    if (
                        counts_ds.count != 1
                        or counts_ds.dtypes[0] != "uint8"
                        or counts_ds.width != dataset.width
                        or counts_ds.height != dataset.height
                        or counts_ds.width != count_manifest.width
                        or counts_ds.height != count_manifest.height
                        or counts_ds.crs is None
                        or not CRS.from_wkt(counts_ds.crs.to_wkt()).equals(grid.crs)
                        or not CRS.from_user_input(count_manifest.crs).equals(grid.crs)
                        or counts_ds.transform != dataset.transform
                        or counts_path.stat().st_size != count_manifest.file_size_bytes
                        or any(
                            not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-8)
                            for a, b in zip(count_bounds, count_manifest.bounds, strict=True)
                        )
                        or counts_ds.dtypes[0] != count_manifest.dtype
                        or count_manifest.product_id != "MEGC44N000HB"
                        or any(
                            not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
                            for a, b in zip(
                                (abs(counts_ds.res[0]), abs(counts_ds.res[1])),
                                (
                                    count_manifest.pixel_resolution_x,
                                    count_manifest.pixel_resolution_y,
                                ),
                                strict=True,
                            )
                        )
                    ):
                        raise InvalidRasterError(
                            "Observation counts must be a co-registered uint8 raster"
                        )
                    counts = counts_ds.read(1)
                if counts.shape != source.shape:
                    raise InvalidRasterError("Observation-count grid dimensions do not match DEM")
                if (
                    count_manifest.total_cells != counts.size
                    or count_manifest.observed_cells != int(np.count_nonzero(counts))
                    or count_manifest.maximum_count != int(counts.max(initial=0))
                ):
                    raise InvalidRasterError(
                        "Observation-count summary metadata does not match raster values"
                    )
                valid_source &= counts > 0
            source[valid_source == 0] = np.nan
            values = np.full((height, width), np.nan, dtype="float32")
            reproject(
                source=source,
                destination=values,
                src_transform=dataset.transform,
                src_crs=grid.crs,
                src_nodata=np.nan,
                dst_transform=destination_transform,
                dst_crs=grid.local_crs,
                dst_nodata=np.nan,
                resampling=Resampling.average,
                init_dest_nodata=True,
            )
            fractions = np.full((height, width), -1.0, dtype="float32")
            reproject(
                source=valid_source,
                destination=fractions,
                src_transform=dataset.transform,
                src_crs=grid.crs,
                dst_transform=destination_transform,
                dst_crs=grid.local_crs,
                dst_nodata=-1.0,
                resampling=Resampling.average,
                init_dest_nodata=True,
            )
    except InvalidRasterError:
        raise
    except Exception as exc:
        raise InvalidRasterError("Raster reprojection or aggregation failed") from exc

    valid = np.isfinite(values) & (fractions >= minimum_valid_fraction)
    values[~valid] = np.nan
    if not np.any(valid):
        raise IncompatibleResolutionError("Requested support contains no sufficiently valid cells")
    reference = float(np.median(values[valid]))
    values[valid] -= reference
    return values, valid, reference


def _write_float_raster(
    path: Path,
    array: np.ndarray,
    crs_wkt: str,
    transform: Affine,
    *,
    manifest: DatasetManifest,
    center: GeographicCenter,
    target_resolution_m: float,
    median_reference_m: float,
) -> None:
    encoded = np.where(np.isfinite(array), array, OUTPUT_NODATA).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=array.shape[1],
        height=array.shape[0],
        count=1,
        dtype="float32",
        crs=crs_wkt,
        transform=transform,
        nodata=float(OUTPUT_NODATA),
        compress="deflate",
        predictor=3,
    ) as dataset:
        dataset.write(encoded, 1)
        dataset.set_band_description(1, "median-relative elevation")
        dataset.update_tags(
            dataset_id=manifest.id,
            target_body=manifest.target_body,
            product=manifest.product,
            source_surface_type=str(
                manifest.product_metadata.get(
                    "surface_type",
                    "planetary_dtm" if manifest.target_body in {"mars", "moon"} else "unknown",
                )
            ),
            source_vertical_reference=manifest.vertical_reference,
            source_vertical_units=manifest.vertical_units,
            output_vertical_units="m",
            value_semantics="elevation minus valid-cell median; absolute datum not preserved",
            removed_valid_cell_median_m=f"{median_reference_m:.12g}",
            comparison_center_lon_lat=f"{center.longitude:.12g},{center.latitude:.12g}",
            target_resolution_m=f"{target_resolution_m:.12g}",
            resampling="area-weighted average",
            source_sha256=manifest.checksum_sha256,
        )


def run_scale_bridge(
    *,
    planetary_raster: Path,
    planetary_manifest: DatasetManifest,
    planetary_center: tuple[float, float] | GeographicCenter,
    earth_raster: Path,
    earth_manifest: DatasetManifest,
    earth_center: tuple[float, float] | GeographicCenter,
    support_width_m: float,
    support_height_m: float,
    planetary_support_width_m: float | None = None,
    planetary_support_height_m: float | None = None,
    output_dir: Path,
    target_resolution_m: float | None = None,
    minimum_valid_fraction_per_cell: float = 0.999,
    planetary_open_path: Path | None = None,
    earth_open_path: Path | None = None,
    planetary_observation_counts: ObservationCountSource | None = None,
) -> ScaleBridgeResult:
    """Build paired, locally projected rasters over an explicit physical support.

    Centers are ``(longitude, latitude)`` degrees in each body's own geodetic
    system. The two local CRSs intentionally have separate origins and are never
    treated as one shared geographic coordinate system.
    """

    def as_center(value: tuple[float, float] | GeographicCenter) -> GeographicCenter:
        if isinstance(value, GeographicCenter):
            return value
        if not isinstance(value, tuple) or len(value) != 2:
            raise CoordinateTransformationError(
                "Each center must be a longitude/latitude pair in degrees"
            )
        return GeographicCenter(longitude=value[0], latitude=value[1])

    config = ScaleBridgeConfig(
        planetary_center=as_center(planetary_center),
        earth_center=as_center(earth_center),
        support_width_m=support_width_m,
        support_height_m=support_height_m,
        planetary_support_width_m=planetary_support_width_m,
        planetary_support_height_m=planetary_support_height_m,
        target_resolution_m=target_resolution_m,
        minimum_valid_fraction_per_cell=minimum_valid_fraction_per_cell,
    )
    if planetary_manifest.target_body == "earth" or earth_manifest.target_body != "earth":
        raise InvalidRasterError(
            "ScaleBridge requires one non-Earth reference and one Earth raster"
        )
    p_path, e_path = Path(planetary_raster), Path(earth_raster)
    p_open, e_open = planetary_open_path, earth_open_path
    p_grid = _inspect_source(p_path, p_open, planetary_manifest, config.planetary_center)
    e_grid = _inspect_source(e_path, e_open, earth_manifest, config.earth_center)
    if planetary_observation_counts is not None:
        count_manifest = planetary_observation_counts.manifest
        if planetary_manifest.target_body != "mars":
            raise InvalidRasterError("This observation-count adapter is specific to MOLA Mars DEMs")
        if count_manifest.source_topography_id != planetary_manifest.id:
            raise InvalidRasterError("Observation-count provenance points to a different DEM")
        if sha256_file(planetary_observation_counts.raster_path) != count_manifest.checksum_sha256:
            raise InvalidRasterError("Observation-count checksum differs from its manifest")
        if count_manifest.id != count_manifest.checksum_sha256:
            raise InvalidRasterError("Observation-count manifest ID must match its checksum")
    p_factor = _unit_to_metres(planetary_manifest.vertical_units)
    e_factor = _unit_to_metres(earth_manifest.vertical_units)
    software_versions = {
        "terratwin_scale_bridge": "0.2.0",
        "numpy": np.__version__,
        "rasterio": rasterio.__version__,
        "gdal": rasterio.__gdal_version__,
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
    }
    p_nominal = max(p_grid.x_spacing_m, p_grid.y_spacing_m)
    e_nominal = max(e_grid.x_spacing_m, e_grid.y_spacing_m)
    sampling_floor = max(
        p_nominal,
        e_nominal,
        p_grid.effective_resolution_m or 0.0,
        e_grid.effective_resolution_m or 0.0,
    )
    requested_resolution = config.target_resolution_m or 0.0
    resolution = max(sampling_floor, requested_resolution)
    source_limited = requested_resolution > 0 and sampling_floor > requested_resolution + 1e-8
    cell_budget_resolution = (
        max(
            math.sqrt(config.support_width_m * config.support_height_m / MAX_TARGET_CELLS),
            math.sqrt(config.planetary_width_m * config.planetary_height_m / MAX_TARGET_CELLS),
        )
        * 1.001
    )
    cell_limited = cell_budget_resolution > resolution
    if cell_limited:
        # Account for ceil() when deriving dimensions so a boundary-rounding
        # pixel cannot exceed the explicit memory budget.
        resolution = cell_budget_resolution * 1.001
    earth_width = max(2, math.ceil(config.support_width_m / resolution))
    earth_height = max(2, math.ceil(config.support_height_m / resolution))
    planetary_width = max(2, math.ceil(config.planetary_width_m / resolution))
    planetary_height = max(2, math.ceil(config.planetary_height_m / resolution))
    if (
        earth_width * earth_height > MAX_TARGET_CELLS
        or planetary_width * planetary_height > MAX_TARGET_CELLS
    ):
        raise IncompatibleResolutionError(
            "Comparison grid still exceeds the cell limit after safe coarsening"
        )
    earth_transform = _target_transform(earth_width, earth_height, resolution)
    planetary_transform = _target_transform(planetary_width, planetary_height, resolution)

    p_values, p_valid, p_median = _warp_source(
        p_path,
        p_open,
        planetary_manifest,
        p_grid,
        planetary_transform,
        planetary_width,
        planetary_height,
        config.minimum_valid_fraction_per_cell,
        planetary_observation_counts,
    )
    e_values, e_valid, e_median = _warp_source(
        e_path,
        e_open,
        earth_manifest,
        e_grid,
        earth_transform,
        earth_width,
        earth_height,
        config.minimum_valid_fraction_per_cell,
    )
    common = p_valid & e_valid if p_valid.shape == e_valid.shape else None
    cell_area = resolution * resolution
    planetary_output_cells = planetary_width * planetary_height
    output_cells = earth_width * earth_height
    coverage = CoverageReport(
        planetary_valid_cells=int(p_valid.sum()),
        earth_valid_cells=int(e_valid.sum()),
        planetary_output_cells=planetary_output_cells,
        output_cells=output_cells,
        planetary_valid_area_m2=float(p_valid.sum() * cell_area),
        earth_valid_area_m2=float(e_valid.sum() * cell_area),
        planetary_fraction=float(p_valid.sum() / planetary_output_cells),
        earth_fraction=float(e_valid.sum() / output_cells),
        common_valid_cells=None if common is None else int(common.sum()),
        common_fraction=(None if common is None else float(common.sum() / planetary_output_cells)),
        common_valid_area_m2=(None if common is None else float(common.sum() * cell_area)),
    )

    config_payload: dict[str, Any] = {
        "planetary_id": planetary_manifest.id,
        "earth_id": earth_manifest.id,
        "planetary_observation_counts": (
            None
            if planetary_observation_counts is None
            else {
                key: value
                for key, value in planetary_observation_counts.manifest.model_dump(
                    mode="json"
                ).items()
                if key != "downloaded_at"
            }
        ),
        "planetary_scientific_metadata": {
            "crs": planetary_manifest.crs,
            "bounds": planetary_manifest.bounds,
            "pixel_resolution_x": planetary_manifest.pixel_resolution_x,
            "pixel_resolution_y": planetary_manifest.pixel_resolution_y,
            "vertical_units": planetary_manifest.vertical_units,
            "vertical_reference": planetary_manifest.vertical_reference,
            "nodata": planetary_manifest.nodata,
            "effective_resolution_m": p_grid.effective_resolution_m,
            "product_metadata": planetary_manifest.product_metadata,
        },
        "earth_scientific_metadata": {
            "crs": earth_manifest.crs,
            "bounds": earth_manifest.bounds,
            "pixel_resolution_x": earth_manifest.pixel_resolution_x,
            "pixel_resolution_y": earth_manifest.pixel_resolution_y,
            "vertical_units": earth_manifest.vertical_units,
            "vertical_reference": earth_manifest.vertical_reference,
            "nodata": earth_manifest.nodata,
            "effective_resolution_m": e_grid.effective_resolution_m,
            "product_metadata": earth_manifest.product_metadata,
        },
        "planetary_center": config.planetary_center.model_dump(),
        "earth_center": config.earth_center.model_dump(),
        "support_width_m": config.support_width_m,
        "support_height_m": config.support_height_m,
        "planetary_support_width_m": config.planetary_width_m,
        "planetary_support_height_m": config.planetary_height_m,
        "target_resolution_m": resolution,
        "minimum_valid_fraction_per_cell": config.minimum_valid_fraction_per_cell,
        "vertical_conversion_factors_to_m": [p_factor, e_factor],
        "processing_software": software_versions,
    }
    reproducibility = hashlib.sha256(
        json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run_id = reproducibility[:20]
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "planetary": "planetary_relative_elevation.tif",
        "earth": "earth_relative_elevation.tif",
        "report": "report.json",
    }
    if common is not None:
        names["common_mask"] = "common_support_mask.npy"
    paths = {key: run_dir / name for key, name in names.items()}
    p_output_crs = CRS.from_wkt(p_grid.local_crs_text)
    e_output_crs = CRS.from_wkt(e_grid.local_crs_text)
    _write_float_raster(
        paths["planetary"],
        p_values,
        p_output_crs.to_wkt(),
        planetary_transform,
        manifest=planetary_manifest,
        center=config.planetary_center,
        target_resolution_m=resolution,
        median_reference_m=p_median,
    )
    _write_float_raster(
        paths["earth"],
        e_values,
        e_output_crs.to_wkt(),
        earth_transform,
        manifest=earth_manifest,
        center=config.earth_center,
        target_resolution_m=resolution,
        median_reference_m=e_median,
    )
    if common is not None:
        np.save(paths["common_mask"], common, allow_pickle=False)
    artifact_sha256 = {key: sha256_file(path) for key, path in paths.items() if key != "report"}

    warnings = [
        "Earth and planetary grids use independent local CRSs and origins; "
        "array indices represent paired support only.",
        "Vertical datums and reference surfaces are not reconciled; each output is "
        "centered on its own valid-cell median.",
    ]
    if p_grid.effective_resolution_m is None or e_grid.effective_resolution_m is None:
        warnings.append(
            "At least one product has no documented effective spatial resolution; "
            "nominal sampling is only a conservative grid floor."
        )
    if cell_limited:
        warnings.append(
            "The requested support would exceed the ScaleBridge cell budget. The comparison "
            f"grid was transparently coarsened to {resolution:.6g} m; the report records this "
            "scale and no finer terrain information is implied."
        )
    if (
        planetary_manifest.target_body == "mars"
        and planetary_manifest.product_metadata.get("product_id") == "MEGT44N000HB"
        and planetary_observation_counts is None
    ):
        warnings.append(
            "MOLA observation-count raster was not supplied; bins interpolated where the "
            "MEGDR has no direct observations cannot be excluded from common support."
        )
    if planetary_manifest.vertical_reference != earth_manifest.vertical_reference:
        warnings.append(
            "Input vertical references differ and absolute elevations must not be compared."
        )
    if coverage.common_fraction is not None and coverage.common_fraction < 1.0:
        warnings.append(
            "Some paired support cells did not meet the per-cell valid-data threshold; "
            "interpret comparisons with the reported coverage."
        )
    if common is None:
        warnings.append(
            "Planetary reference and Earth search supports have different dimensions; "
            "no single paired-cell mask is defined. Candidate-level feature masks are "
            "computed independently during discovery."
        )
    for manifest in (planetary_manifest, earth_manifest):
        convention = str(manifest.product_metadata.get("nodata_convention", ""))
        if "interpolat" in convention.casefold():
            if manifest is planetary_manifest and planetary_observation_counts is not None:
                warnings.append(
                    f"{manifest.product} documents interpolation for bins without observations; "
                    "the companion counts mask excluded zero-count bins, but does not quantify "
                    "uncertainty or other interpolation effects in retained cells."
                )
            else:
                warnings.append(
                    f"{manifest.product} contains product-documented interpolated cells; "
                    "they are not direct measurements."
                )
    resolution_basis = (
        "maximum of measured local ground pixel spacing, documented effective resolution, "
        "and requested comparison resolution; the coarsest source support is never upsampled"
    )
    if cell_limited:
        resolution_basis += "; coarsened further to stay within the configured target-cell budget"
    if source_limited:
        warnings.append(
            "The requested comparison resolution is finer than at least one source's measured "
            f"sampling support. The actual grid uses {resolution:.6g} m; "
            "no upsampling is performed."
        )
    report = ScaleBridgeReport(
        run_id=run_id,
        planetary=SourceGridReport(
            dataset_id=planetary_manifest.id,
            target_body=planetary_manifest.target_body,
            product=planetary_manifest.product,
            source_crs=planetary_manifest.crs,
            source_horizontal_units=p_grid.horizontal_units,
            local_metric_crs=p_grid.local_crs_text,
            nominal_ground_spacing_x_m=p_grid.x_spacing_m,
            nominal_ground_spacing_y_m=p_grid.y_spacing_m,
            effective_resolution_m=p_grid.effective_resolution_m,
            vertical_units=planetary_manifest.vertical_units,
            vertical_reference=planetary_manifest.vertical_reference,
            center_longitude_latitude=(
                config.planetary_center.longitude,
                config.planetary_center.latitude,
            ),
            source_bounds=planetary_manifest.bounds,
            source_geographic_bounds_lon_lat=p_grid.geographic_bounds,
            relative_elevation_reference_m=p_median,
        ),
        earth=SourceGridReport(
            dataset_id=earth_manifest.id,
            target_body=earth_manifest.target_body,
            product=earth_manifest.product,
            source_crs=earth_manifest.crs,
            source_horizontal_units=e_grid.horizontal_units,
            local_metric_crs=e_grid.local_crs_text,
            nominal_ground_spacing_x_m=e_grid.x_spacing_m,
            nominal_ground_spacing_y_m=e_grid.y_spacing_m,
            effective_resolution_m=e_grid.effective_resolution_m,
            vertical_units=earth_manifest.vertical_units,
            vertical_reference=earth_manifest.vertical_reference,
            center_longitude_latitude=(config.earth_center.longitude, config.earth_center.latitude),
            source_bounds=earth_manifest.bounds,
            source_geographic_bounds_lon_lat=e_grid.geographic_bounds,
            relative_elevation_reference_m=e_median,
        ),
        target_resolution_m=resolution,
        target_resolution_basis=resolution_basis,
        resampling="area-weighted average; no upsampling below source sampling support",
        information_loss={
            "planetary": (
                (
                    "No finer spatial detail is created. Source cells are averaged onto the "
                    "comparison grid. The MOLA counts mask excluded zero-count bins; retained "
                    "cells remain product-level MEGDR values and do not resolve sub-grid terrain."
                )
                if planetary_observation_counts is not None
                else (
                    "No finer spatial detail is created. Source cells are averaged onto "
                    "the comparison grid; sub-grid terrain and documented interpolated source "
                    "cells remain unresolved."
                )
            ),
            "earth": (
                "Fine-scale terrain is aggregated to the coarsest comparison support "
                "and is not retained "
                "as resolvable detail in the output."
            ),
        },
        requested_support_width_m=config.support_width_m,
        requested_support_height_m=config.support_height_m,
        actual_support_width_m=earth_width * resolution,
        actual_support_height_m=earth_height * resolution,
        planetary_requested_support_width_m=config.planetary_width_m,
        planetary_requested_support_height_m=config.planetary_height_m,
        planetary_actual_support_width_m=planetary_width * resolution,
        planetary_actual_support_height_m=planetary_height * resolution,
        alignment_description=(
            "Each body is centered independently on its supplied coordinate and projected to a "
            "local azimuthal-equidistant metric grid at the same cell size; support extents and "
            "raster dimensions may differ, and matching array indices have no geographic meaning."
        ),
        grid_width=earth_width,
        grid_height=earth_height,
        planetary_grid_width=planetary_width,
        planetary_grid_height=planetary_height,
        minimum_valid_fraction_per_cell=config.minimum_valid_fraction_per_cell,
        coverage=coverage,
        planetary_observation_counts=(
            None
            if planetary_observation_counts is None
            else ObservationCountsReport(
                product_id=planetary_observation_counts.manifest.product_id,
                checksum_sha256=planetary_observation_counts.manifest.checksum_sha256,
                source_topography_id=planetary_observation_counts.manifest.source_topography_id,
                count_units=planetary_observation_counts.manifest.count_units,
                zero_count_policy=(
                    "zero-count cells excluded as unobserved; positive count is a validity mask "
                    "only and count magnitude is not used to weight elevation"
                ),
                observed_source_cells=planetary_observation_counts.manifest.observed_cells,
                total_source_cells=planetary_observation_counts.manifest.total_cells,
                maximum_count=planetary_observation_counts.manifest.maximum_count,
            )
        ),
        vertical_normalization=(
            "Convert recognized linear units to metres, area-average, then subtract each "
            "source's own median over valid output cells; no vertical datum conversion."
        ),
        area_calculation=(
            "Valid area is projected local-grid cell count multiplied by target cell-size squared; "
            "it is not an ellipsoidal geodesic area measurement."
        ),
        common_mask_semantics=(
            "Boolean NumPy array aligned by row and column to both outputs; true only where "
            "both source valid fractions meet the configured threshold; no single CRS applies."
            if common is not None
            else "Unavailable for unequal support dimensions; candidate-level feature masks "
            "are evaluated against the planetary reference during discovery."
        ),
        processing_software=software_versions,
        reproducibility_sha256=reproducibility,
        warnings=warnings,
        artifacts={key: path.name for key, path in paths.items()},
        artifact_sha256=artifact_sha256,
    )
    paths["report"].write_text(report.model_dump_json(indent=2))
    return ScaleBridgeResult(
        planetary_relative_elevation_m=p_values,
        earth_relative_elevation_m=e_values,
        common_support_mask=common,
        planetary_local_crs=p_grid.local_crs_text,
        earth_local_crs=e_grid.local_crs_text,
        report=report,
        artifact_paths=paths,
    )
