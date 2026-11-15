"""Independent raster comparison with explicit vertical-datum gating."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import reproject

from app.domain.schemas.terrain_twin import ValidationMetrics
from app.engines.data_ingestion.ingestion import sha256_file


class ValidationUnavailable(ValueError):
    """Raised when a reference cannot support a defensible elevation comparison."""


def summarize_elevation_errors(
    source_elevation_m: np.ndarray,
    reference_elevation_m: np.ndarray,
    common_valid_mask: np.ndarray,
    *,
    pixel_area_m2: float,
    resampling: str,
) -> ValidationMetrics:
    """Calculate error statistics only over a caller-supplied common valid mask."""
    source = np.asarray(source_elevation_m, dtype="float64")
    reference = np.asarray(reference_elevation_m, dtype="float64")
    mask = np.asarray(common_valid_mask, dtype=bool)
    if source.shape != reference.shape or source.shape != mask.shape:
        raise ValueError("Source, reference, and common-valid arrays must have equal shapes")
    if not math.isfinite(pixel_area_m2) or pixel_area_m2 <= 0:
        raise ValueError("Metric pixel area must be a positive finite value")
    mask &= np.isfinite(source) & np.isfinite(reference)
    count = int(mask.sum())
    if count == 0:
        raise ValidationUnavailable("No common valid elevation samples are available")
    errors = source[mask] - reference[mask]
    absolute_errors = np.abs(errors)
    p05, p50, p95 = np.quantile(errors, [0.05, 0.5, 0.95])
    a05, a50, a95 = np.quantile(absolute_errors, [0.05, 0.5, 0.95])
    return ValidationMetrics(
        mean_absolute_error_m=float(np.mean(absolute_errors)),
        root_mean_square_error_m=float(np.sqrt(np.mean(errors**2))),
        median_absolute_error_m=float(np.median(absolute_errors)),
        mean_bias_m=float(np.mean(errors)),
        error_percentiles_m={"p05": float(p05), "p50": float(p50), "p95": float(p95)},
        absolute_error_percentiles_m={"p05": float(a05), "p50": float(a50), "p95": float(a95)},
        valid_sample_count=count,
        valid_comparison_area_m2=count * pixel_area_m2,
        valid_coverage=count / mask.size,
        resampling=resampling,
    )


def compare_independent_dem(
    source_path: Path,
    reference_path: Path,
    *,
    source_sha256: str,
    reference_sha256: str,
    source_vertical_reference: str,
    reference_vertical_reference: str,
    source_vertical_units: str,
    reference_vertical_units: str,
    source_dataset_id: str,
    reference_dataset_id: str,
    source_provider: str,
    reference_provider: str,
    source_product: str,
    reference_product: str,
    source_lineage_ids: tuple[str, ...] = (),
    reference_lineage_ids: tuple[str, ...] = (),
    source_effective_resolution_m: float | None = None,
    reference_effective_resolution_m: float | None = None,
    minimum_valid_fraction: float = 0.999,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, ValidationMetrics]:
    """Compare a mesh-surface raster to an independent DEM on common nominal support.

    Both rasters are area-aggregated to the coarsest nominal/effective support;
    the result never upsamples a coarse reference and counts interpolated pixels
    as independent comparison samples.
    """
    if not source_path.is_file() or not reference_path.is_file():
        raise ValidationUnavailable("Source or independent reference raster is unavailable")
    if source_path.resolve() == reference_path.resolve():
        raise ValidationUnavailable("Source and reference paths identify the same raster")
    if sha256_file(reference_path) != reference_sha256:
        raise ValidationUnavailable("Reference raster checksum does not match its manifest")
    if source_sha256 == reference_sha256 or source_dataset_id == reference_dataset_id:
        raise ValidationUnavailable("Reference DEM is identical to the reconstruction source")
    source_lineage = {source_dataset_id, source_sha256, *source_lineage_ids}
    if source_lineage.intersection(
        {reference_dataset_id, reference_sha256, *reference_lineage_ids}
    ):
        raise ValidationUnavailable("Reference DEM shares source-data lineage with reconstruction")
    if source_provider.strip().casefold() == reference_provider.strip().casefold() and (
        source_product.strip().casefold() == reference_product.strip().casefold()
    ):
        raise ValidationUnavailable("Reference is the same source product, not independent")
    if source_vertical_units.casefold() not in {"m", "meter", "meters", "metre", "metres"}:
        raise ValidationUnavailable("Source vertical units are not documented in metres")
    if reference_vertical_units.casefold() not in {"m", "meter", "meters", "metre", "metres"}:
        raise ValidationUnavailable("Reference vertical units are not documented in metres")
    if (
        source_vertical_reference.strip().casefold()
        != reference_vertical_reference.strip().casefold()
    ):
        raise ValidationUnavailable(
            "Vertical references differ and no validated transformation grid was supplied"
        )

    if not 0 < minimum_valid_fraction <= 1:
        raise ValueError("Minimum valid fraction must be in (0, 1]")
    with rasterio.open(source_path) as source, rasterio.open(reference_path) as reference:
        if source.count != 1 or reference.count != 1 or source.crs is None or reference.crs is None:
            raise ValidationUnavailable(
                "Both elevation references must be single-band georeferenced rasters"
            )
        if abs(source.transform.b) > 1e-12 or abs(source.transform.d) > 1e-12:
            raise ValidationUnavailable("Source mesh raster must use a north-up grid")
        source_tags = source.tags()
        if (
            source_tags.get("dataset_id") != source_dataset_id
            or source_tags.get("source_sha256") != source_sha256
            or not source_tags.get("surface_semantics", "").startswith("piecewise-planar surface")
        ):
            raise ValidationUnavailable(
                "Validation source is not a provenance-verified exported-mesh surface raster"
            )
        reference_to_source = Transformer.from_crs(reference.crs, source.crs, always_xy=True)
        ref_center_x = (reference.bounds.left + reference.bounds.right) / 2
        ref_center_y = (reference.bounds.bottom + reference.bounds.top) / 2
        center = reference_to_source.transform(ref_center_x, ref_center_y)
        x_neighbor = reference_to_source.transform(ref_center_x + reference.res[0], ref_center_y)
        y_neighbor = reference_to_source.transform(ref_center_x, ref_center_y + reference.res[1])
        reference_nominal = max(math.dist(center, x_neighbor), math.dist(center, y_neighbor))
        source_nominal = max(abs(float(source.res[0])), abs(float(source.res[1])))
        known_effective = [
            value
            for value in (source_effective_resolution_m, reference_effective_resolution_m)
            if value is not None
        ]
        if any(not math.isfinite(value) or value <= 0 for value in known_effective):
            raise ValidationUnavailable("Effective resolution metadata is invalid")
        comparison_support_m = max([source_nominal, reference_nominal, *known_effective])
        bounds = source.bounds
        width = max(1, math.ceil((bounds.right - bounds.left) / comparison_support_m))
        height = max(1, math.ceil((bounds.top - bounds.bottom) / comparison_support_m))
        if width * height > 4_000_000:
            raise ValidationUnavailable("Common-support validation grid exceeds processing limit")
        transform = Affine(
            comparison_support_m, 0, bounds.left, 0, -comparison_support_m, bounds.top
        )

        def aggregate(dataset: rasterio.io.DatasetReader) -> tuple[np.ndarray, np.ndarray]:
            masked = dataset.read(1, masked=True)
            values = np.asarray(masked.astype("float32").filled(np.nan), dtype="float32")
            valid = ~np.ma.getmaskarray(masked) & np.isfinite(values)
            values[~valid] = np.nan
            destination = np.full((height, width), np.nan, dtype="float32")
            fraction = np.zeros((height, width), dtype="float32")
            reproject(
                source=values,
                destination=destination,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=np.nan,
                dst_transform=transform,
                dst_crs=source.crs,
                dst_nodata=np.nan,
                resampling=Resampling.average,
                init_dest_nodata=True,
            )
            reproject(
                source=valid.astype("float32"),
                destination=fraction,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=None,
                dst_transform=transform,
                dst_crs=source.crs,
                dst_nodata=0,
                resampling=Resampling.average,
                init_dest_nodata=True,
            )
            return destination, fraction

        source_array, source_fraction = aggregate(source)
        warped_reference, reference_fraction = aggregate(reference)
        common = (
            (source_fraction >= minimum_valid_fraction)
            & (reference_fraction >= minimum_valid_fraction)
            & np.isfinite(source_array)
            & np.isfinite(warped_reference)
        )
        metrics = summarize_elevation_errors(
            source_array,
            warped_reference,
            common,
            pixel_area_m2=comparison_support_m**2,
            resampling=(
                "area-average source mesh and independent reference to common metric support; "
                "valid fraction threshold "
                f"{minimum_valid_fraction:g}; support {comparison_support_m:.6g} m"
            ),
        )
        metrics = metrics.model_copy(update={"comparison_support_m": comparison_support_m})
        return source_array, warped_reference, common, metrics


def unavailable_validation_reason(
    *,
    reference_requested: bool,
    reference_id: str | None,
    exception: Exception | None = None,
) -> tuple[Literal["unvalidated"], str | None]:
    if not reference_requested:
        return "unvalidated", "No independent reference DEM was selected."
    if isinstance(exception, ValidationUnavailable):
        return "unvalidated", str(exception)
    if exception is not None:
        return "unvalidated", "The reference DEM could not be aligned for comparison."
    return "unvalidated", f"Independent reference {reference_id or 'unknown'} is unavailable."
