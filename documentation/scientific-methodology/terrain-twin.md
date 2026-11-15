# Terrain Twin reconstruction and validation method

## Scope and interpretation

Terrain Twin converts an actual selected Earth DEM window to a georeferenced,
chunked glTF 2.0 binary (`.glb`) mesh. It is a DEM-to-mesh visualization. It
does not estimate depth from imagery, infer subsurface materials, or upgrade an
analogue-discovery status. A discovery window marked `insufficient_evidence`
stays unranked in the reconstruction record and viewer.

## Source and footprint

The API accepts a candidate ID from the newest stored discovery report whose
Earth source manifest is a checksum-verified `bare_earth_dtm`. The candidate
must also have its complete WGS84 boundary covered by that raw raster. The API
retains discovery ranking order among supported windows. It resolves the
dataset ID to the unique manifest and checksummed raw raster under the
configured data directory. Public requests do not accept filesystem paths. The
selected polygon is transformed to the source CRS, masked and cropped. Source
rasters are read only.

The current demonstrated source is the USGS 1 m bare-earth lidar DTM,
`USGS_1M_12_x36y481_ID_SouthernID_2018_D19`, in UTM zone 12N, with NAVD88 metre
elevations. Copernicus GLO-30 is a DSM and is excluded as a bare-earth terrain
source for this workflow.

## Horizontal and vertical coordinates

The candidate centroid determines its WGS 84 / UTM zone, EPSG:32643 for the
demonstrated window. GDAL/Rasterio transforms the source grid to this local
projected metric grid. The target posting is the coarser of the two source
ground sample spacings estimated at the source bounds; this avoids claiming
new detail from geographic-grid conversion. Elevation samples use bilinear
resampling; validity is transformed separately as categorical data with
nearest-neighbour sampling. The resulting mesh horizontal axes are east and
north in metres. Vertical values remain source metres and EGM2008 orthometric
reference; no vertical datum conversion is performed.

Default vertical exaggeration is 1. User-selected exaggeration is bounded to
`(0, 10]` and applied around the median valid elevation, so the mesh retains
its documented vertical reference and range. It is recorded in the response,
`metadata.json`, and glTF asset extras.

## Validity, triangles and mesh budget

Validity uses source raster masks plus finite elevation checks. The source
candidate footprint is counted independently from NoData: cells outside the
polygon are reported as candidate exterior, not as missing terrain. The
projected raster separately reports valid and invalid cells; the latter can
include both footprint-edge cells and source NoData propagated through the
projection.

Mesh stride is a deterministic integer chosen to meet the configured vertex
budget, while retaining the last row and column. Normals use metric finite
differences, one-sided at boundaries and across one-sided valid neighbours;
invalid samples remain excluded. A coarse cell produces two triangles only
when its complete source footprint and four sampled vertices are valid. This
conservative test prevents triangles from spanning NoData holes. Cell chunks
share boundary positions but are emitted as independent glTF mesh primitives.
There is no additional geometric simplifier in this phase; the documented
stride sampling is the resolution reduction.

GLB coordinates use east, up, north axes; chunk positions are centered
horizontally and elevation is anchored around the valid median. The GLB extras
include the WGS84 candidate bounds and polygon, source dataset/checksum, source
and mesh CRS, vertical reference/units, posting, stride, vertex budget,
exaggeration and validation status. API metadata also includes original raster,
candidate-crop and projected raster dimensions.

## Independent validation

Validation requires a separately ingested reference raster, a different
checksum and dataset identity, disjoint recorded lineage, single-band
georeferenced elevation, documented metre units, and an identical declared
vertical reference. Validation rasterizes the exported mesh's decimated,
piecewise-planar triangle surface, then area-averages both that surface and the
reference to a common metric support no finer than either source's nominal
support. A separately propagated valid-fraction mask defines common support.
Only common finite cells contribute to MAE,
RMSE, median absolute error, bias, signed and absolute error percentiles,
sample count, valid area and coverage. The present workflow does not apply a
geoid or other vertical datum transformation. Product effective resolution is
not available for the demonstrated pair, so the reported 10.285 m support is
nominally matched and is not a claim of equivalent effective resolution.

If a reference is missing or incompatible, status is `unvalidated`; metrics
are null. Error-map and comparison-mask artifacts explicitly state that no
comparison is available. The same input checksum is rejected as not
independent.

The current displayed example uses the USGS 1 m 2018 lidar bare-earth DTM
(`ID_SouthernID_2018_D19`) and a separately acquired USGS historical 1/3 arc
second NED DEM dated 2002 (`USGS_13_n44w113_20021201`). Both declare NAVD88
metres; their recorded source lineage identifiers differ. Validation is
relative to that older, coarser DEM and must not be read as contemporary
absolute ground truth. The Copernicus GLO-30 product is identified as a DSM
and is not offered as an independent bare-earth reference in the Terrain Twin
interface. A DSM may include vegetation and structures and is not treated as
bare-earth terrain evidence.

## Outputs and resource bounds

Each deterministic run writes `terrain.glb`, `candidate_metric_elevation.tif`,
elevation and slope PNG previews, explicit unavailable SVGs for error and
comparison mask when appropriate, and a JSON metadata sidecar beneath
`data/derived/terrain_twins/<id>/`. The source DEM remains immutable. The API
limits a candidate source crop and projected raster to eight million cells,
mesh vertices to 250,000 maximum, chunk cell width to 512, and exaggeration to
10. Long-running reconstruction executes in FastAPI's synchronous worker
pool; a distributed task queue is not introduced.

The browser loads the GLB with Three.js `GLTFLoader`, and camera orbit, pan and
zoom use `OrbitControls`. Elevation colors are embedded in the mesh. Slope
colors are calculated from the delivered mesh normals for rendering only; they
are not a replacement for the documented raster terrain-analytics products.
The viewer provides a 1×–10× vertical display-scale control (default 6×) to
make subtle relief visible. This transform is applied in the browser around the
mesh's vertical midpoint. It does not rewrite the GLB, source elevations or
validation values; the interface labels the display factor separately from
the exported mesh's recorded vertical exaggeration.

For validated meshes, the comparison-support image is a binary spatial mask:
green cells were included in the independent DEM error calculation and dark
cells were outside common valid support. The interface displays valid sample
count, coverage and comparison-cell support with a legend. It is not an
elevation or error surface. The adjacent error raster uses a diverging color
scale centered at zero, with blue indicating the mesh is lower and red that it
is higher than the independent reference.

## Demonstrated real output

The actual selected candidate covers WGS84 bounds `77.2629323271, 18.5416816623,
77.4561456863, 18.7258740890`. It was projected to EPSG:32643 at 30.7462 m
posting, resulting in 673 × 673 cells, a stride-2 mesh with 114,921 vertices in
nine chunks, and a 6.77 MB GLB. The source crop had 460,548 cells inside the
candidate footprint, zero source NoData cells, and 1,596 cells in the crop
rectangle outside the candidate polygon. Projected support had 13,542 invalid
cells, primarily because the rectangular projected extent includes cells
outside the transformed candidate footprint. Values range from 372.50 to
527.55 m. The raw input checksum was verified before and after processing.

## References

- [Three.js GLTFLoader documentation](https://threejs.org/docs/pages/GLTFLoader.html)
- [Three.js OrbitControls documentation](https://threejs.org/docs/pages/OrbitControls.html)
- [Khronos glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
- [NASADEM user guide](https://lpdaac.usgs.gov/documents/2237/NASADEM_User_Guide_V13.pdf)
