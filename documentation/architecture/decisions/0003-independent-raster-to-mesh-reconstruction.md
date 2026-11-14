# ADR 0003: Independent DEM reconstruction
Status: planned; not implemented.
The first Terrain Twin will use TerraTwin-owned raster-to-mesh code. It will
preserve geographic metadata, vertical units and valid samples, exclude triangles
across NoData gaps, and disclose vertical exaggeration.
A DEM mesh is not monocular image-depth reconstruction. Reproducing source samples
does not establish independent accuracy. Without an independent elevation
reference, the result must be labeled visualization-only.

