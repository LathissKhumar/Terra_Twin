"""Bounded, provenance-preserving DEM-to-GLB terrain reconstruction."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pyproj
import rasterio
from rasterio.features import geometry_mask
from rasterio.mask import mask as raster_mask
from rasterio.warp import (
    Resampling,
    calculate_default_transform,
    reproject,
    transform_geom,
)

from app.domain.schemas.datasets import DatasetManifest
from app.domain.schemas.terrain_twin import TerrainTwinCandidate, TerrainTwinMetadata
from app.engines.data_ingestion.ingestion import sha256_file
from app.engines.validation.engine import (
    ValidationUnavailable,
    compare_independent_dem,
    unavailable_validation_reason,
)

MAX_SOURCE_CROP_CELLS = 8_000_000
ENGINE_VERSION = "0.1.2"


def terrain_twin_identifier(
    candidate_id: str,
    source_sha256: str,
    *,
    max_vertices: int,
    chunk_cells: int,
    vertical_exaggeration: float,
    reference_sha256: str | None = None,
) -> str:
    return hashlib.sha256(
        f"{candidate_id}:{source_sha256}:{max_vertices}:"
        f"{chunk_cells}:{vertical_exaggeration}:{reference_sha256}:{ENGINE_VERSION}".encode()
    ).hexdigest()[:24]


def _rgba_color(values: np.ndarray, low: float, high: float, palette: str) -> np.ndarray:
    normalized = np.clip((values.astype("float64") - low) / max(high - low, 1e-12), 0, 1)
    if palette == "slope":
        stops = np.array([[22, 163, 175], [34, 197, 94], [234, 179, 8], [239, 68, 68]])
    elif palette == "error":
        stops = np.array([[37, 99, 235], [148, 163, 184], [220, 38, 38]])
    else:
        stops = np.array([[15, 23, 42], [8, 145, 178], [45, 212, 191], [245, 158, 11]])
    position = normalized * (len(stops) - 1)
    index = np.minimum(position.astype("int32"), len(stops) - 2)
    fraction = (position - index)[..., None]
    return cast(
        np.ndarray,
        np.rint(stops[index] * (1 - fraction) + stops[index + 1] * fraction).astype("uint8"),
    )


def _write_png(path: Path, rgba: np.ndarray) -> None:
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("PNG image must be an RGBA array")
    height, width, _ = rgba.shape
    scanlines = b"".join(b"\x00" + rgba[row].tobytes() for row in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    content = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines, level=6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(content)


def _write_unavailable_svg(path: Path, heading: str, detail: str) -> None:
    safe_heading = heading.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe_detail = detail.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="400" '
        'viewBox="0 0 720 400"><rect width="720" height="400" fill="#101827"/>'
        '<rect x="20" y="20" width="680" height="360" rx="8" fill="#172235" '
        'stroke="#475569"/><text x="52" y="170" fill="#fbbf24" font-size="22" '
        'font-family="sans-serif">'
        f'{safe_heading}</text><text x="52" y="210" fill="#cbd5e1" '
        f'font-size="15" font-family="sans-serif">{safe_detail}</text></svg>'
    )


def _write_preview(
    path: Path,
    elevation: np.ndarray,
    valid: np.ndarray,
    palette: str,
    pixel_spacing_m: tuple[float, float] = (1.0, 1.0),
) -> None:
    rgba = np.zeros((*elevation.shape, 4), dtype="uint8")
    rgba[..., :3] = (24, 34, 50)
    rgba[..., 3] = 255
    values = elevation[valid]
    if values.size:
        render_valid = valid.copy()
        if palette == "slope":
            row_gradient, col_gradient = np.gradient(
                elevation.astype("float64"), pixel_spacing_m[1], pixel_spacing_m[0]
            )
            pixel_slope = np.degrees(np.arctan(np.hypot(row_gradient, col_gradient)))
            render_valid &= np.isfinite(pixel_slope)
            color_values = pixel_slope[render_valid]
        elif palette == "error":
            limit = float(np.quantile(np.abs(values), 0.98))
            low, high = -max(limit, 1e-9), max(limit, 1e-9)
            rgba[valid, :3] = _rgba_color(values, low, high, palette)
            _write_png(path, rgba)
            return
        else:
            color_values = values
        low, high = np.quantile(color_values, [0.02, 0.98])
        rgba[render_valid, :3] = _rgba_color(color_values, float(low), float(high), palette)
    _write_png(path, rgba)


def _axis_gradient(values: np.ndarray, valid: np.ndarray, axis: int, spacing: float) -> np.ndarray:
    previous_values = np.roll(values, 1, axis=axis)
    next_values = np.roll(values, -1, axis=axis)
    previous_valid = np.roll(valid, 1, axis=axis)
    next_valid = np.roll(valid, -1, axis=axis)
    first: list[slice | int] = [slice(None)] * values.ndim
    last: list[slice | int] = [slice(None)] * values.ndim
    first[axis] = 0
    last[axis] = -1
    previous_valid[tuple(first)] = False
    next_valid[tuple(last)] = False
    both = previous_valid & next_valid & valid
    only_next = next_valid & ~previous_valid & valid
    only_previous = previous_valid & ~next_valid & valid
    gradient = np.zeros(values.shape, dtype="float64")
    gradient[both] = (next_values[both] - previous_values[both]) / (2 * spacing)
    gradient[only_next] = (next_values[only_next] - values[only_next]) / spacing
    gradient[only_previous] = (values[only_previous] - previous_values[only_previous]) / spacing
    gradient[~valid] = np.nan
    return gradient


def _calculate_normals(
    elevation: np.ndarray, valid: np.ndarray, x_spacing: float, y_spacing: float
) -> np.ndarray:
    dz_dx = _axis_gradient(elevation, valid, 1, x_spacing)
    dz_drow = _axis_gradient(elevation, valid, 0, y_spacing)
    dz_dn = -dz_drow  # northing decreases as raster row index increases
    nx = -np.nan_to_num(dz_dx, nan=0.0)
    ny = np.ones(elevation.shape, dtype="float64")
    nz = -np.nan_to_num(dz_dn, nan=0.0)
    normals = np.stack((nx, ny, nz), axis=-1)
    lengths = np.linalg.norm(normals, axis=-1, keepdims=True)
    return cast(np.ndarray, (normals / np.maximum(lengths, 1e-12)).astype("float32"))


def _downsample_indices(length: int, stride: int) -> np.ndarray:
    positions = list(range(0, length, stride))
    if positions[-1] != length - 1:
        positions.append(length - 1)
    return np.asarray(positions, dtype="int32")


def _chunked_vertex_upper_bound(rows: int, columns: int, chunk_cells: int) -> int:
    row_chunks = math.ceil((rows - 1) / chunk_cells)
    column_chunks = math.ceil((columns - 1) / chunk_cells)
    return (rows + max(0, row_chunks - 1)) * (columns + max(0, column_chunks - 1))


def _valid_coarse_cells(valid: np.ndarray, rows: np.ndarray, columns: np.ndarray) -> np.ndarray:
    invalid_prefix = np.pad((~valid).astype("uint32"), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    r0 = rows[:-1, None]
    r1 = rows[1:, None] + 1
    c0 = columns[None, :-1]
    c1 = columns[None, 1:] + 1
    invalid_count = (
        invalid_prefix[r1, c1]
        - invalid_prefix[r0, c1]
        - invalid_prefix[r1, c0]
        + invalid_prefix[r0, c0]
    )
    return cast(np.ndarray, invalid_count == 0)


def _piecewise_mesh_surface(
    elevation: np.ndarray, valid: np.ndarray, stride: int
) -> tuple[np.ndarray, np.ndarray]:
    """Rasterize the exported mesh's decimated piecewise-planar surface at source centers."""
    rows = _downsample_indices(elevation.shape[0], stride)
    columns = _downsample_indices(elevation.shape[1], stride)
    sampled = elevation[np.ix_(rows, columns)]
    sampled_valid = valid[np.ix_(rows, columns)]
    coarse_valid = _valid_coarse_cells(valid, rows, columns)
    surface = np.full(elevation.shape, np.nan, dtype="float32")
    surface_valid = np.zeros(elevation.shape, dtype=bool)
    for ri in range(len(rows) - 1):
        r0, r1 = int(rows[ri]), int(rows[ri + 1])
        row_fraction = np.arange(r1 - r0 + 1, dtype="float64")[:, None] / (r1 - r0)
        for ci in range(len(columns) - 1):
            if not coarse_valid[ri, ci] or not sampled_valid[ri : ri + 2, ci : ci + 2].all():
                continue
            c0, c1 = int(columns[ci]), int(columns[ci + 1])
            col_fraction = np.arange(c1 - c0 + 1, dtype="float64")[None, :] / (c1 - c0)
            ul, ur = float(sampled[ri, ci]), float(sampled[ri, ci + 1])
            ll, lr = float(sampled[ri + 1, ci]), float(sampled[ri + 1, ci + 1])
            first = row_fraction + col_fraction <= 1.0
            values = np.where(
                first,
                ul + col_fraction * (ur - ul) + row_fraction * (ll - ul),
                ur * (1 - row_fraction)
                + lr * (row_fraction + col_fraction - 1)
                + ll * (1 - col_fraction),
            )
            surface[r0 : r1 + 1, c0 : c1 + 1] = values.astype("float32")
            surface_valid[r0 : r1 + 1, c0 : c1 + 1] = True
    return surface, surface_valid


def _reproject_valid_mask(
    valid: np.ndarray,
    *,
    source_transform: rasterio.Affine,
    source_crs: rasterio.crs.CRS,
    destination_transform: rasterio.Affine,
    destination_crs: pyproj.CRS,
    destination_shape: tuple[int, int],
) -> np.ndarray:
    """Warp categorical valid/invalid codes while reserving 0 and 255 as NoData."""
    destination = np.zeros(destination_shape, dtype="uint8")
    source_classes = np.where(valid, 1, 2).astype("uint8")
    reproject(
        source=source_classes,
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        src_nodata=255,
        dst_transform=destination_transform,
        dst_crs=destination_crs,
        dst_nodata=0,
        resampling=Resampling.nearest,
        init_dest_nodata=True,
    )
    return cast(np.ndarray, destination == 1)


def _align4(buffer: bytearray) -> None:
    buffer.extend(b"\x00" * ((-len(buffer)) % 4))


def _write_glb(
    path: Path,
    elevation: np.ndarray,
    valid: np.ndarray,
    normals: np.ndarray,
    transform: rasterio.Affine,
    *,
    stride: int,
    chunk_cells: int,
    vertical_exaggeration: float,
    elevation_origin_m: float,
    metadata: dict[str, Any],
) -> tuple[int, int]:
    rows = _downsample_indices(elevation.shape[0], stride)
    columns = _downsample_indices(elevation.shape[1], stride)
    sampled_elevation = elevation[np.ix_(rows, columns)]
    sampled_valid = valid[np.ix_(rows, columns)]
    sampled_normals = normals[np.ix_(rows, columns)]
    coarse_cells_valid = _valid_coarse_cells(valid, rows, columns)
    x_values = transform.c + (columns + 0.5) * transform.a
    north_values = transform.f + (rows + 0.5) * transform.e
    x_center = (float(x_values[0]) + float(x_values[-1])) / 2
    north_center = (float(north_values[0]) + float(north_values[-1])) / 2
    elevation_low, elevation_high = np.quantile(elevation[valid], [0.02, 0.98])
    rgb = np.zeros((*sampled_elevation.shape, 3), dtype="float32")
    rgb[sampled_valid] = (
        _rgba_color(
            sampled_elevation[sampled_valid],
            float(elevation_low),
            float(elevation_high),
            "elevation",
        ).astype("float32")
        / 255
    )

    binary = bytearray()
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    total_vertices = 0
    chunk_count = 0

    def append_view(data: bytes, target: int) -> int:
        _align4(binary)
        offset = len(binary)
        binary.extend(data)
        index = len(buffer_views)
        buffer_views.append(
            {"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": target}
        )
        return index

    def append_accessor(
        view_index: int,
        component_type: int,
        count: int,
        accessor_type: str,
        *,
        minimum: list[float] | None = None,
        maximum: list[float] | None = None,
    ) -> int:
        accessor: dict[str, Any] = {
            "bufferView": view_index,
            "componentType": component_type,
            "count": count,
            "type": accessor_type,
        }
        if minimum is not None:
            accessor["min"] = minimum
        if maximum is not None:
            accessor["max"] = maximum
        accessors.append(accessor)
        return len(accessors) - 1

    row_starts = range(0, len(rows) - 1, chunk_cells)
    col_starts = range(0, len(columns) - 1, chunk_cells)
    for row_start in row_starts:
        row_stop = min(row_start + chunk_cells, len(rows) - 1)
        for col_start in col_starts:
            col_stop = min(col_start + chunk_cells, len(columns) - 1)
            patch_height = row_stop - row_start + 1
            patch_width = col_stop - col_start + 1
            patch_valid = sampled_valid[row_start : row_stop + 1, col_start : col_stop + 1]
            if not patch_valid.any():
                continue
            patch_elevation = sampled_elevation[row_start : row_stop + 1, col_start : col_stop + 1]
            patch_normals = sampled_normals[row_start : row_stop + 1, col_start : col_stop + 1]
            patch_rgb = rgb[row_start : row_stop + 1, col_start : col_stop + 1]
            x_grid, north_grid = np.meshgrid(
                x_values[col_start : col_stop + 1], north_values[row_start : row_stop + 1]
            )
            safe_elevation = np.where(patch_valid, patch_elevation, elevation_origin_m)
            positions = np.stack(
                (
                    x_grid - x_center,
                    (safe_elevation - elevation_origin_m) * vertical_exaggeration
                    + elevation_origin_m,
                    north_grid - north_center,
                ),
                axis=-1,
            ).astype("float32")
            flat_valid = patch_valid.ravel()
            cell_valid = coarse_cells_valid[row_start:row_stop, col_start:col_stop]
            base_rows, base_cols = np.indices((patch_height - 1, patch_width - 1))
            upper_left = (base_rows * patch_width + base_cols).ravel().astype("uint32")
            upper_right = upper_left + 1
            lower_left = upper_left + patch_width
            lower_right = lower_left + 1
            include = (
                cell_valid.ravel()
                & flat_valid[upper_left]
                & flat_valid[upper_right]
                & flat_valid[lower_left]
                & flat_valid[lower_right]
            )
            faces = (
                np.stack(
                    (
                        upper_left[include],
                        upper_right[include],
                        lower_left[include],
                        upper_right[include],
                        lower_right[include],
                        lower_left[include],
                    ),
                    axis=1,
                )
                .astype("uint32", copy=False)
                .ravel()
            )
            if faces.size == 0:
                continue
            local_positions = positions.reshape(-1, 3)
            local_normals = patch_normals.reshape(-1, 3)
            local_colors = patch_rgb.reshape(-1, 3)
            pos_min = local_positions.min(axis=0).astype(float).tolist()
            pos_max = local_positions.max(axis=0).astype(float).tolist()
            position_accessor = append_accessor(
                append_view(local_positions.astype("<f4").tobytes(), 34962),
                5126,
                len(local_positions),
                "VEC3",
                minimum=pos_min,
                maximum=pos_max,
            )
            normal_accessor = append_accessor(
                append_view(local_normals.astype("<f4").tobytes(), 34962),
                5126,
                len(local_normals),
                "VEC3",
            )
            color_accessor = append_accessor(
                append_view(local_colors.astype("<f4").tobytes(), 34962),
                5126,
                len(local_colors),
                "VEC3",
            )
            index_accessor = append_accessor(
                append_view(faces.astype("<u4").tobytes(), 34963), 5125, len(faces), "SCALAR"
            )
            meshes.append(
                {
                    "name": f"terrain-chunk-{chunk_count:04d}",
                    "primitives": [
                        {
                            "attributes": {
                                "POSITION": position_accessor,
                                "NORMAL": normal_accessor,
                                "COLOR_0": color_accessor,
                            },
                            "indices": index_accessor,
                            "material": 0,
                            "mode": 4,
                        }
                    ],
                }
            )
            nodes.append({"name": f"terrain-chunk-{chunk_count:04d}", "mesh": chunk_count})
            total_vertices += len(local_positions)
            chunk_count += 1

    if not meshes:
        raise ValueError(
            "No valid terrain triangles remain after NoData and simplification handling"
        )
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": f"TerraTwin Terrain Twin {ENGINE_VERSION}",
            "extras": metadata,
        },
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {
                "name": "Terrain elevation colors",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [1, 1, 1, 1],
                    "metallicFactor": 0,
                    "roughnessFactor": 1,
                },
                "doubleSided": False,
            }
        ],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    json_bytes = json.dumps(gltf, separators=(",", ":"), allow_nan=False).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    _align4(binary)
    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary)
    path.write_bytes(
        struct.pack("<III", 0x46546C67, 2, total_length)
        + struct.pack("<II", len(json_bytes), 0x4E4F534A)
        + json_bytes
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
    return total_vertices, chunk_count


def _manifest_lineage(manifest: DatasetManifest) -> tuple[str, ...]:
    raw = manifest.product_metadata.get("source_lineage_ids")
    if not isinstance(raw, str):
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _effective_resolution_m(manifest: DatasetManifest) -> float | None:
    value = manifest.product_metadata.get("effective_resolution_m")
    if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
        return float(value)
    return None


def _utm_crs(longitude: float, latitude: float) -> pyproj.CRS:
    zone = max(1, min(60, math.floor((longitude + 180) / 6) + 1))
    epsg = (32600 if latitude >= 0 else 32700) + zone
    return pyproj.CRS.from_epsg(epsg)


def _source_resolution_metres(
    crs: rasterio.crs.CRS,
    bounds: tuple[float, float, float, float],
    resolution: tuple[float, float],
) -> tuple[float, float]:
    projected = pyproj.CRS.from_wkt(crs.to_wkt())
    if projected.is_projected:
        factors = [axis.unit_conversion_factor for axis in projected.axis_info[:2]]
        return abs(resolution[0] * factors[0]), abs(resolution[1] * factors[1])
    center_x = (bounds[0] + bounds[2]) / 2
    center_y = (bounds[1] + bounds[3]) / 2
    geod = projected.get_geod()
    if geod is None:
        raise ValueError("Geographic source CRS does not define a geodesic")
    x_dist = geod.inv(center_x, center_y, center_x + resolution[0], center_y)[2]
    y_dist = geod.inv(center_x, center_y, center_x, center_y + resolution[1])[2]
    return abs(float(x_dist)), abs(float(y_dist))


def create_terrain_twin(
    *,
    candidate: TerrainTwinCandidate,
    source_path: Path,
    source_manifest: DatasetManifest,
    output_directory: Path,
    max_vertices: int = 150_000,
    chunk_cells: int = 128,
    vertical_exaggeration: float = 1.0,
    reference_path: Path | None = None,
    reference_manifest: DatasetManifest | None = None,
    artifact_base_url: str,
) -> TerrainTwinMetadata:
    """Create a georeferenced chunked mesh and visual artifacts for one real candidate."""
    if source_manifest.target_body != "earth" or source_manifest.id != candidate.source_dataset_id:
        raise ValueError("Candidate and source Earth dataset manifest do not match")
    if sha256_file(source_path) != source_manifest.checksum_sha256:
        raise ValueError("Immutable source DEM checksum does not match its manifest")
    if source_manifest.vertical_units.casefold() not in {"m", "meter", "meters", "metre", "metres"}:
        raise ValueError("Source DEM vertical units are not documented in metres")
    if not 1_000 <= max_vertices <= 250_000 or not 32 <= chunk_cells <= 512:
        raise ValueError("Mesh limits are outside configured resource bounds")
    if not math.isfinite(vertical_exaggeration) or not 0 < vertical_exaggeration <= 10:
        raise ValueError("Vertical exaggeration must be finite and in (0, 10]")

    output_directory.mkdir(parents=True, exist_ok=True)
    polygon = {"type": "Polygon", "coordinates": [candidate.geographic_boundary_wgs84]}
    elevation_path = output_directory / "candidate_metric_elevation.tif"
    with rasterio.open(source_path) as source:
        if source.crs is None or source.count != 1:
            raise ValueError("Candidate source must be a single-band raster with a declared CRS")
        if (
            source.width != source_manifest.width
            or source.height != source_manifest.height
            or not pyproj.CRS.from_user_input(source.crs).equals(
                pyproj.CRS.from_user_input(source_manifest.crs)
            )
        ):
            raise ValueError("Source raster metadata differs from its ingested manifest")
        if source_manifest.vertical_reference.strip() == "":
            raise ValueError("Source vertical reference is required")
        if not all(
            math.isfinite(value) for point in candidate.geographic_boundary_wgs84 for value in point
        ):
            raise ValueError("Candidate polygon contains non-finite coordinates")
        source_crs = source.crs
        source_resolution = source.res
        source_bounds = (
            source.bounds.left,
            source.bounds.bottom,
            source.bounds.right,
            source.bounds.top,
        )
        source_dimensions = (source.height, source.width)
        projected_polygon = transform_geom("EPSG:4326", source_crs, polygon, precision=12)
        ring = projected_polygon["coordinates"][0]
        polygon_bounds = (
            min(point[0] for point in ring),
            min(point[1] for point in ring),
            max(point[0] for point in ring),
            max(point[1] for point in ring),
        )
        source_bounds_check = (
            source.bounds.left,
            source.bounds.bottom,
            source.bounds.right,
            source.bounds.top,
        )
        if (
            polygon_bounds[0] < source_bounds_check[0] - 1e-9
            or polygon_bounds[1] < source_bounds_check[1] - 1e-9
            or polygon_bounds[2] > source_bounds_check[2] + 1e-9
            or polygon_bounds[3] > source_bounds_check[3] + 1e-9
        ):
            raise ValueError("Candidate polygon extends outside the source DEM coverage")
        cropped, crop_transform = raster_mask(
            source,
            [projected_polygon],
            crop=True,
            filled=False,
            all_touched=False,
        )
        source_crop = np.asarray(cropped[0].astype("float32").filled(np.nan), dtype="float32")
        if source_crop.size > MAX_SOURCE_CROP_CELLS:
            raise ValueError("Candidate source crop exceeds the configured pixel limit")
        candidate_footprint_mask = geometry_mask(
            [projected_polygon],
            out_shape=source_crop.shape,
            transform=crop_transform,
            invert=True,
            all_touched=False,
        )
        source_data_mask = np.ma.getmaskarray(cropped[0])
        source_valid = candidate_footprint_mask & ~source_data_mask & np.isfinite(source_crop)
        source_nodata_cell_count = int(
            np.count_nonzero(candidate_footprint_mask & source_data_mask)
        )
        source_candidate_exterior_cell_count = int(
            source_crop.size - candidate_footprint_mask.sum()
        )
        source_crop_valid_count = int(source_valid.sum())
        if not source_valid.any():
            raise ValueError("Candidate footprint has no valid source elevation samples")
        bounds = rasterio.transform.array_bounds(
            source_crop.shape[0], source_crop.shape[1], crop_transform
        )
        center_lon, center_lat = candidate.centroid_wgs84
        mesh_crs = _utm_crs(center_lon, center_lat)
        target_resolution = max(
            _source_resolution_metres(source_crs, source_bounds, source_resolution)
        )
        target_transform, target_width, target_height = calculate_default_transform(
            source_crs,
            mesh_crs,
            source_crop.shape[1],
            source_crop.shape[0],
            *bounds,
            resolution=target_resolution,
        )
    if (
        target_width < 2
        or target_height < 2
        or target_width * target_height > MAX_SOURCE_CROP_CELLS
    ):
        raise ValueError("Projected candidate raster exceeds configured dimensions or pixel limit")
    metric_elevation = np.full((target_height, target_width), np.nan, dtype="float32")
    metric_mask = _reproject_valid_mask(
        source_valid,
        source_transform=crop_transform,
        source_crs=source_crs,
        destination_transform=target_transform,
        destination_crs=mesh_crs,
        destination_shape=(target_height, target_width),
    )
    reproject(
        source=source_crop,
        destination=metric_elevation,
        src_transform=crop_transform,
        src_crs=source_crs,
        src_nodata=np.nan,
        dst_transform=target_transform,
        dst_crs=mesh_crs,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
        init_dest_nodata=True,
    )
    valid = metric_mask & np.isfinite(metric_elevation)
    if int(valid.sum()) < 4:
        raise ValueError("Projected candidate does not contain enough valid cells to form a mesh")
    metric_elevation[~valid] = np.nan
    with rasterio.open(
        elevation_path,
        "w",
        driver="GTiff",
        width=target_width,
        height=target_height,
        count=1,
        dtype="float32",
        crs=mesh_crs,
        transform=target_transform,
        nodata=np.nan,
        compress="deflate",
    ) as destination:
        destination.write(metric_elevation, 1)
        destination.update_tags(
            source_dataset_id=source_manifest.id,
            source_sha256=source_manifest.checksum_sha256,
            vertical_units=source_manifest.vertical_units,
            vertical_reference=source_manifest.vertical_reference,
            candidate_id=candidate.candidate_id,
        )

    mesh_shape = metric_elevation.shape
    stride = max(1, math.ceil(math.sqrt((mesh_shape[0] * mesh_shape[1]) / max_vertices)))
    while (
        _chunked_vertex_upper_bound(
            len(_downsample_indices(mesh_shape[0], stride)),
            len(_downsample_indices(mesh_shape[1], stride)),
            chunk_cells,
        )
        > max_vertices
    ):
        stride += 1
    normals = _calculate_normals(
        metric_elevation, valid, abs(target_transform.a), abs(target_transform.e)
    )
    elevations = metric_elevation[valid]
    elevation_origin = float(np.median(elevations))
    preview_elevation = output_directory / "elevation.png"
    preview_slope = output_directory / "slope.png"
    _write_preview(preview_elevation, metric_elevation, valid, "elevation")
    mesh_spacing = (abs(float(target_transform.a)), abs(float(target_transform.e)))
    mesh_surface_path = output_directory / "exported_mesh_surface.tif"
    mesh_surface, mesh_surface_valid = _piecewise_mesh_surface(metric_elevation, valid, stride)
    with rasterio.open(
        mesh_surface_path,
        "w",
        driver="GTiff",
        width=mesh_surface.shape[1],
        height=mesh_surface.shape[0],
        count=1,
        dtype="float32",
        crs=mesh_crs,
        transform=target_transform,
        nodata=np.nan,
        compress="deflate",
    ) as output:
        output.write(mesh_surface, 1)
        output.update_tags(
            dataset_id=source_manifest.id,
            source_sha256=source_manifest.checksum_sha256,
            surface_semantics="piecewise-planar surface of exported mesh; physical vertical scale",
            mesh_stride=str(stride),
            vertical_exaggeration=str(vertical_exaggeration),
        )
    _write_preview(preview_slope, metric_elevation, valid, "slope", mesh_spacing)
    terrain_twin_id = terrain_twin_identifier(
        candidate.candidate_id,
        source_manifest.checksum_sha256,
        max_vertices=max_vertices,
        chunk_cells=chunk_cells,
        vertical_exaggeration=vertical_exaggeration,
        reference_sha256=reference_manifest.checksum_sha256 if reference_manifest else None,
    )
    warnings: list[str] = []
    if candidate.discovery_status == "insufficient_evidence":
        warnings.append(
            "The selected Earth window is insufficient evidence and has no analogue ranking."
        )
    validation_metrics = None
    reference_sha256 = None
    validation_status: Literal["validated", "unvalidated"] = "unvalidated"
    validation_mask_path = output_directory / "valid_comparison_mask_unavailable.svg"
    error_map_path = output_directory / "error_map_unavailable.svg"
    validation_reason: str | None = "No independent reference DEM was selected."
    if reference_path is not None and reference_manifest is not None:
        reference_sha256 = reference_manifest.checksum_sha256
        try:
            source_values, reference_values, common_mask, validation_metrics = (
                compare_independent_dem(
                    mesh_surface_path,
                    reference_path,
                    source_sha256=source_manifest.checksum_sha256,
                    reference_sha256=reference_manifest.checksum_sha256,
                    source_vertical_reference=source_manifest.vertical_reference,
                    reference_vertical_reference=reference_manifest.vertical_reference,
                    source_vertical_units=source_manifest.vertical_units,
                    reference_vertical_units=reference_manifest.vertical_units,
                    source_dataset_id=source_manifest.id,
                    reference_dataset_id=reference_manifest.id,
                    source_provider=source_manifest.provider,
                    reference_provider=reference_manifest.provider,
                    source_product=source_manifest.product,
                    reference_product=reference_manifest.product,
                    source_lineage_ids=_manifest_lineage(source_manifest),
                    reference_lineage_ids=_manifest_lineage(reference_manifest),
                    source_effective_resolution_m=_effective_resolution_m(source_manifest),
                    reference_effective_resolution_m=_effective_resolution_m(reference_manifest),
                )
            )
            validation_status = "validated"
            validation_reason = None
            validation_mask_path = output_directory / "valid_comparison_mask.png"
            mask_image = np.zeros((*common_mask.shape, 4), dtype="uint8")
            mask_image[..., :3] = np.where(common_mask[..., None], (34, 197, 94), (30, 41, 59))
            mask_image[..., 3] = 255
            _write_png(validation_mask_path, mask_image)
            error_map_path = output_directory / "elevation_error.png"
            _write_preview(error_map_path, source_values - reference_values, common_mask, "error")
        except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
            validation_status, validation_reason = unavailable_validation_reason(
                reference_requested=True, reference_id=reference_manifest.id, exception=exc
            )
            warnings.append(f"Independent validation unavailable: {validation_reason}")
    elif reference_path is not None or reference_manifest is not None:
        validation_status, validation_reason = unavailable_validation_reason(
            reference_requested=True,
            reference_id=reference_manifest.id if reference_manifest else None,
            exception=ValidationUnavailable("Reference raster or manifest is missing"),
        )
        warnings.append(f"Independent validation unavailable: {validation_reason}")
    else:
        warnings.append("No independent reference DEM is selected; mesh is visualization-only.")
    if validation_status == "unvalidated":
        _write_unavailable_svg(
            error_map_path,
            "ERROR MAP UNAVAILABLE",
            validation_reason or "No independent reference DEM is available.",
        )
        _write_unavailable_svg(
            validation_mask_path,
            "COMPARISON MASK UNAVAILABLE",
            "No independent reference DEM is available; no comparison cells are asserted.",
        )

    west = min(point[0] for point in candidate.geographic_boundary_wgs84)
    south = min(point[1] for point in candidate.geographic_boundary_wgs84)
    east = max(point[0] for point in candidate.geographic_boundary_wgs84)
    north = max(point[1] for point in candidate.geographic_boundary_wgs84)
    source_res = (source_manifest.pixel_resolution_x, source_manifest.pixel_resolution_y)
    mesh_res = (abs(float(target_transform.a)), abs(float(target_transform.e)))
    mesh_path = output_directory / "terrain.glb"
    glb_extras = {
        "terrainTwinId": terrain_twin_id,
        "candidateId": candidate.candidate_id,
        "sourceDatasetId": source_manifest.id,
        "sourceProduct": source_manifest.product,
        "sourceSha256": source_manifest.checksum_sha256,
        "geographicBoundsWgs84": [west, south, east, north],
        "candidateBoundaryWgs84": candidate.geographic_boundary_wgs84,
        "sourceCrs": source_manifest.crs,
        "meshCrs": mesh_crs.to_wkt(),
        "horizontalUnits": "m",
        "sourceVerticalUnits": source_manifest.vertical_units,
        "sourceVerticalReference": source_manifest.vertical_reference,
        "verticalTransformation": (
            "no datum conversion; exaggeration is anchored at median elevation"
        ),
        "verticalExaggeration": vertical_exaggeration,
        "elevationExaggerationAnchorM": elevation_origin,
        "sourceResolution": list(source_res),
        "sourceResolutionUnit": source_manifest.resolution_unit,
        "meshResolutionM": list(mesh_res),
        "sourceDimensions": [source_manifest.width, source_manifest.height],
        "meshDimensions": [target_width, target_height],
        "simplificationStride": stride,
        "maxVertices": max_vertices,
        "validationStatus": validation_status,
        "coordinateAxisOrder": "east, up, north",
    }
    vertex_count, chunk_count = _write_glb(
        mesh_path,
        metric_elevation,
        valid,
        normals,
        target_transform,
        stride=stride,
        chunk_cells=chunk_cells,
        vertical_exaggeration=vertical_exaggeration,
        elevation_origin_m=elevation_origin,
        metadata=glb_extras,
    )
    if vertex_count > max_vertices:
        raise RuntimeError("Chunked terrain mesh exceeded the configured total vertex budget")
    artifacts = {
        "mesh": f"{artifact_base_url}/artifacts/mesh",
        "elevation_map": f"{artifact_base_url}/artifacts/elevation-map",
        "slope_map": f"{artifact_base_url}/artifacts/slope-map",
        "error_map": f"{artifact_base_url}/artifacts/error-map",
        "valid_comparison_mask": f"{artifact_base_url}/artifacts/valid-mask",
    }
    metadata = TerrainTwinMetadata(
        terrain_twin_id=terrain_twin_id,
        candidate_id=candidate.candidate_id,
        discovery_run_id=candidate.discovery_run_id,
        discovery_status=candidate.discovery_status,
        ranking=candidate.ranking,
        source_dataset_id=source_manifest.id,
        source_product=source_manifest.product,
        source_sha256=source_manifest.checksum_sha256,
        geographic_bounds_wgs84=(west, south, east, north),
        candidate_boundary_wgs84=candidate.geographic_boundary_wgs84,
        source_crs=source_manifest.crs,
        mesh_crs=mesh_crs.to_string(),
        horizontal_transformation=(
            f"{source_manifest.crs} to {mesh_crs.to_string()} using GDAL bilinear resampling"
        ),
        source_vertical_units=source_manifest.vertical_units,
        source_vertical_reference=source_manifest.vertical_reference,
        vertical_transformation=(
            "no datum conversion; vertical exaggeration is applied around the median elevation"
        ),
        vertical_exaggeration=vertical_exaggeration,
        source_raster_resolution=source_res,
        source_resolution_unit=source_manifest.resolution_unit,
        mesh_resolution_m=mesh_res,
        source_dimensions=source_dimensions,
        candidate_crop_dimensions=(source_crop.shape[0], source_crop.shape[1]),
        mesh_dimensions=(target_width, target_height),
        simplification_stride=stride,
        max_vertices=max_vertices,
        actual_vertex_count=vertex_count,
        chunk_count=chunk_count,
        source_valid_cell_count=source_crop_valid_count,
        source_nodata_cell_count=source_nodata_cell_count,
        source_candidate_exterior_cell_count=source_candidate_exterior_cell_count,
        mesh_valid_cell_count=int(valid.sum()),
        mesh_nodata_cell_count=int(valid.size - valid.sum()),
        elevation_range_m=(float(np.min(elevations)), float(np.max(elevations))),
        validation_status=validation_status,
        validation_reason=validation_reason,
        reference_dataset_id=reference_manifest.id if reference_manifest else None,
        reference_sha256=reference_sha256,
        validation_metrics=validation_metrics,
        artifacts=artifacts,
        warnings=warnings,
        software={
            "engine": ENGINE_VERSION,
            "rasterio": rasterio.__version__,
            "gdal": rasterio.__gdal_version__,
            "pyproj": pyproj.__version__,
            "numpy": np.__version__,
        },
    )
    (output_directory / "metadata.json").write_text(metadata.model_dump_json(indent=2) + "\n")
    return metadata
