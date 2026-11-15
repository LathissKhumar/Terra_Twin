# TerraTwin scientific validation audit

**Audit date:** 2026-11-15  
**Scope:** implemented ScaleBridge, terrain analytics, analogue discovery, Terrain Twin validation, mission assessment and the latest persisted real-data discovery run. This is an independent review of scientific validity, not a feature implementation.  
**Decision: FAIL — high-severity findings remain.** The current evidence supports exploratory, bounded surface-morphology comparisons. It does not yet support treating all ranked windows as validated rover-terrain analogues.

No scientific code or methodology was changed during this audit. The corrections below require an explicit methodological decision and a versioned methodology update before implementation.

## Audit evidence

The latest discovery artifact inspected was `data/results/analogue_discovery/a2070ff303aaf4cf075e/report.json` (engine `0.6.0`, run `a2070ff303aaf4cf075e`). It records:

- Mars: HiRISE Jezero DTM `DTEEC_048842_1985_048908_1985_U01`, manifest/checksum `9e723a990ef2694474bbc2486039098c885d09b938e70b903d60c15cbf704008`, nominal posting about 1.01 m, effective resolution unavailable, vertical reference Mars 2000 areoid.
- Earth: Copernicus DEM GLO-30 Public DSM `COP-DEM-GLO30-18-77`, manifest/checksum `51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989`, 1 arc-second geographic posting, effective resolution unavailable, EGM2008 orthometric metres. Its manifest identifies the product as a DSM.
- ScaleBridge output posting: 30.7461555 m. Mars support: 66 × 66 cells, 2,029.25 m actual width; Earth support: 326 × 326 cells, 10,023.25 m actual width. The planetary and Earth supports use separate local metric CRSs and have no paired-cell mask.
- Discovery: bounded Earth envelope `77.4525300846, 18.4547161710, 77.5474699154, 18.5452776689` (west, south, east, north); 25 generated/evaluated windows; 2,000 m requested width and stride; 25 eligible. Ranked distances and 94.03% evidence coverage are reproducible from the saved feature comparisons. This is a roughly 10 km bounded test, not a broad or global search.
- Terrain Twin: saved status `UNVALIDATED`; no independent reference metrics were found. The UI/report correctly has no validation accuracy claim for this run.

The current methodology documentation still describes the older MOLA/463 m/20 km search as the actual discovery run. That discrepancy is recorded below.

## Findings

### SV-01 — Landform classes are normalized on incompatible raster extents

**Severity: HIGH**  
**Affected module:** Terrain Analytics → Analogue Discovery  
**Exact locations:** `backend/app/engines/terrain_analytics/engine.py`, `classify_relative_landform` (lines 277–292), invoked over the entire raster by `analyze_terrain_raster` (around line 510); `backend/app/engines/analogue_discovery/engine.py`, `compare_feature_distributions` (lines 153–180).

**Scientific issue:** TPI classes use each input raster's own raster-wide TPI standard deviation. In the current run the Mars raster is about 2 km across, while the Earth source raster used to create the feature map is about 10 km across. Candidate windows are then cropped from Earth classes that were thresholded using the full Earth raster's distribution, while the planetary window's classes were thresholded using the planetary raster's distribution. The low/neutral/high class definitions are therefore not on a common threshold. Expanding or changing the Earth search raster can change class proportions inside an otherwise identical candidate. Those proportions contribute 0.08 of the mission weighted distance.

**Why it matters:** The categorical total-variation distance compares labels whose decision thresholds differ by body and search extent. It can shift candidate distances/ranks and makes a candidate's morphology score depend on unrelated terrain outside its footprint.

**Reproducible example:** `classify_relative_landform(np.array([[0., 0., 1.]]))[0, 2]` returns `+1`; append 100 unrelated cells of value `10` to the right and reclassify, and the unchanged value-`1` cell returns `0`. The raster-wide standard deviation changes from `0.4714` to `1.6275`. Production path: the Earth full-raster class map is computed before `run_discovery` crops candidate windows.

**Required correction:** Define and version one commensurate class thresholding rule for both planetary and Earth profiles. Possible choices include common physical TPI thresholds or a shared standardization scale fitted from a declared reference population and applied unchanged to Earth. Do not silently choose between them. Record the expected effect on class proportions and candidate rankings in the methodology decision.

**Regression test required:** Use a fixed candidate TPI window embedded in two different larger contexts and assert that its class labels and class fractions remain invariant under the selected comparison rule. Add a cross-body test proving the exact same TPI values map to the same classes.

### SV-02 — Copernicus DSM surface objects are not separated from terrain

**Severity: HIGH**  
**Affected module:** Data provenance → Terrain Analytics → Analogue Discovery  
**Exact locations:** Earth manifest `data/manifests/51587b0a9af347ff0bfe95b51ccd4d145ffdf0f74fdf18ce0213028f8041d989.json`, `product_metadata.surface_type = "DSM"`; `backend/app/engines/terrain_analytics/engine.py`, `analyze_terrain_raster`; `backend/app/engines/analogue_discovery/engine.py`, `run_discovery`.

**Scientific issue:** The actual Earth input is a digital surface model. Copernicus documentation says GLO-30 represents the reflective surface, including buildings, infrastructure and vegetation; it is not a bare-earth terrain model. The current feature extraction and candidate scoring do not mask or otherwise distinguish these objects from landform geometry. A DSM can therefore produce slope, relief, roughness and curvature signals from canopy or structures.

**Why it matters:** Rover mobility terrain analogues should not silently interpret vegetation/buildings as natural ground morphology. A valid score is presently a similarity between sampled elevation surfaces, which may include above-ground objects, rather than a controlled comparison of bare-earth terrain. The manifest records the distinction, but it is not reflected as a candidate evidence gate or a per-result interpretation warning.

**Reproducible example:** Re-run the saved discovery run using the recorded Copernicus DSM manifest and inspect `candidate.feature_comparisons`; all 25 windows are eligible although the Earth surface type is DSM. There is no land-cover or surface-object exclusion in the pipeline.

**Required correction:** Make surface type part of the analysis contract and report. For a bare-earth terrain claim, require a suitable DTM or a documented object/land-cover screening method with its own uncertainty. Otherwise label candidates as DSM-surface matches and prevent the assessment from implying natural-terrain transferability. Product documentation explicitly distinguishes DSM from DTM and describes included vegetation/infrastructure [Copernicus DEM product documentation](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM).

**Regression test required:** A DSM input without an approved screening policy must not receive an unqualified bare-earth terrain assessment. Test that surface type is propagated from manifest through feature report, candidate, assessment and passport.

### SV-03 — Independent validation can be asserted without proving the file or lineage is independent

**Severity: HIGH**  
**Affected module:** Terrain Twin → validation  
**Exact locations:** `backend/app/engines/validation/engine.py`, `compare_independent_dem` (lines 59–83); `backend/app/engines/terrain_twin/engine.py`, `create_terrain_twin` validation call (lines 697–710).

**Scientific issue:** The validation helper rejects equal caller-provided SHA strings, but does not calculate either file's checksum, verify the reference raster against its manifest, or establish source-product lineage. Two byte-distinct files derived from the same DEM can pass as “independent.” I reproduced a more direct contract failure: passing the exact same GeoTIFF as `source_path` and `reference_path` with two different supplied SHA strings returns validation metrics with MAE 0, RMSE 0 and 25 valid samples. The application route currently resolves its reference through a checksum-checked manifest, reducing arbitrary-path exposure, but the scientific engine interface itself does not enforce the independence claim and distinct checksums alone do not prove independent measurement.

The validation call also compares the projected `candidate_metric_elevation.tif` intermediate to the reference; it does not rasterize the exported GLB mesh or test the exported mesh's simplified geometry/topology. Its metrics are therefore raster-pair agreement metrics, not necessarily mesh-reconstruction validation metrics.

**Why it matters:** A numerically perfect or small error can be produced against the same measurement or a derivative of it and then misrepresented as independent reconstruction validation. Current saved Terrain Twin is correctly `UNVALIDATED`, so this failure is latent in the path for future reference-backed runs.

**Reproducible example:** In backend environment, create a small GeoTIFF and run `compare_independent_dem(p, p, source_sha256="claimed-source-sha", reference_sha256="claimed-different-sha", source_vertical_reference="EGM2008", reference_vertical_reference="EGM2008", source_vertical_units="m", reference_vertical_units="m")`. Observed result: accepted, MAE 0, RMSE 0, sample count 25.

**Required correction:** Verify actual path checksums against validated manifests inside the service boundary; record and check dataset parent/source lineage, not only file-byte hashes; reject a reference derived from the reconstruction input. Decide whether validation is intended to validate the source raster or exported mesh. For mesh validation, compare the actual exported/simplified mesh surface on common spatial support. Otherwise rename and document the metric as source-raster comparison and keep mesh validation unavailable.

**Regression test required:** Same path with forged distinct hashes must reject; byte-different copies/re-encodings with shared source lineage must reject as independent; file/manifest checksum mismatch must reject; simplified mesh and source-raster comparisons must be separate tests/statuses.

### SV-04 — Validation resamples any reference onto source cells without resolution compatibility checks

**Severity: HIGH**  
**Affected module:** Independent validation  
**Exact location:** `backend/app/engines/validation/engine.py`, `compare_independent_dem` (lines 85–131).

**Scientific issue:** The reference is always bilinearly reprojected to every source pixel, and the resulting pixel count and source-cell area are reported as the valid comparison sample count and area. The function does not compare source/reference nominal or effective resolution, choose common support, aggregate the finer source, or warn when this is an upsampling of a coarser reference.

**Why it matters:** Bilinear interpolation does not create independent observations. A 90 m reference reprojected onto a 1 m source grid could produce thousands of highly correlated “samples” per original reference cell and misleadingly precise coverage/error summaries. The metrics would not represent matched spatial support.

**Reproducible example:** Supply a coarse reference raster and a much finer source raster covering the same footprint. The current helper creates a source-grid-sized comparison with no resolution warning; `valid_sample_count` scales with fine source pixels.

**Required correction:** Add effective-resolution-aware support matching. Aggregate to a justified common support (or reject the comparison if effective support is unknown/incompatible), report the chosen support and resampling/aggregation, and calculate valid area from the resulting common cells. Do not label bilinear upsampling as matched-resolution validation.

**Regression test required:** Coarse-to-fine and fine-to-coarse cases must prove that reported independent sample count is not inflated by upsampling and that unsupported resolution pairs return an explicit unavailable status.

### SV-05 — Discovery standard errors assume spatially independent pixels and independent feature errors

**Severity: MEDIUM**  
**Affected module:** Analogue Discovery  
**Exact locations:** `backend/app/engines/analogue_discovery/engine.py`, `_bootstrap_wasserstein_standard_error` (lines 43–92), bootstrap branches in `compare_feature_distributions` (lines 182–196 and 236–244), weighted standard-error combination (lines 336–351).

**Scientific issue:** Bootstrap resampling samples individual raster cells with replacement. Nearby terrain cells are spatially autocorrelated; additionally, slope, relief, roughness, curvature and TPI are derived from the same DEM and are correlated. Weighted score uncertainty combines per-feature errors under an independence assumption. The report warns about both limitations, but these values remain displayed as standard errors and may be read as candidate confidence.

**Why it matters:** The effective sample size can be far smaller than the pixel count. The current standard errors can materially understate ranking uncertainty, especially with only 30 replicates in the saved run.

**Reproducible example:** In `compare_feature_distributions`, compare a spatially smooth raster field with an iid permutation of the same values. The implementation sees identical marginal distributions and sample counts, and its iid bootstrap has no representation of the smooth field's spatial dependence.

**Required correction:** Use spatial block/bootstrap or another spatially defensible uncertainty method with block scale tied to feature support/correlation length; propagate cross-feature covariance when combining score uncertainty. Until then, use a name and UI treatment that unambiguously says “naive iid pixel-bootstrap variability,” or suppress it from confidence-like summaries. Report ranking stability separately.

**Regression test required:** A correlated synthetic field and iid permutation with identical histograms must yield materially different spatial uncertainty under the adopted method; test weighted covariance propagation and ranking stability.

### SV-06 — Elevation-dispersion “roughness” includes regional slope and is counted alongside slope

**Severity: MEDIUM**  
**Affected module:** Terrain Analytics and rover mission profile  
**Exact locations:** `backend/app/engines/terrain_analytics/engine.py`, `_focal_features` (lines 142 onward), `calculate_terrain_roughness` (around line 229); profile rationale in `backend/config/mission_profiles/`.

**Scientific issue:** The configured roughness is the standard deviation of neighborhood elevations, not detrended microrelief, vector ruggedness or TRI. On a perfect plane with gradient components 3 and 4 m per cell, a 3×3 sample has slope 78.690° and elevation SD 4.082 m despite having zero departure from the fitted plane. The descriptor therefore mixes macro-slope with roughness and then both are weighted in the mobility distance.

**Why it matters:** A ranking can count the same broad inclination signal twice and label part of it as roughness. The code and docs disclose the statistic, so the value is not mislabeled as TRI; its use as an independent rover roughness feature still needs a scientific rationale.

**Reproducible example:** Construct `z = 3*x + 4*y` over a 3×3 neighborhood. Direct NumPy population SD is 4.0824829 m while residual roughness after exact plane removal is zero.

**Required correction:** Keep the existing descriptor only if the mission profile explicitly treats elevation dispersion as a scale-dependent combined surface-variation feature and accounts for dependence with slope. Otherwise adopt a documented detrended roughness metric at a justified physical scale. Version the change and assess ranking shifts.

**Regression test required:** Analytic plane test must pin the documented behavior; if detrended roughness is adopted, assert zero for a plane and known residual for a plane plus a localized bump.

### SV-07 — Scientific methodology reports the superseded discovery as current

**Severity: MEDIUM**  
**Affected module:** Scientific documentation and reproducibility  
**Exact location:** `documentation/scientific-methodology/analogue-discovery.md`, section “Actual bounded search — engine 0.5.1” beginning around line 92; related historical run descriptions in `documentation/scientific-methodology/terrain-analytics.md` and `documentation/scientific-methodology/scale-bridge.md`.

**Scientific issue:** The methodology names the MOLA MEGDR/463 m/20 km search as the actual search, while the current report records a HiRISE DTM/30.746 m/2 km/25-window run. Older run results remain useful historical evidence but are not labeled as superseded in the current methods narrative.

**Why it matters:** A scientist following the stated reproducibility procedure may reproduce a different run and misattribute its zero-eligible outcome, coverage and resolution limitations to the latest ranking.

**Reproducible example:** Compare the product IDs and run IDs in the document with the latest artifact cited in this audit. They differ.

**Required correction:** Preserve the older run as a dated historical run, then add the current run, its source IDs, actual settings, coverage, effective-resolution status and result. Explicitly identify which run is current.

**Regression test required:** Documentation check (or a small script) should assert that the “current run” section's run/product IDs match the checked-in/persisted current report.

## Independently checked scientific behavior

- **CRS and horizontal units:** The inspected ScaleBridge implementation transforms each body's inputs to independent local azimuthal-equidistant metric CRSs. Terrain derivatives use metre pixel spacing; discovery rejects non-projected or non-metre feature rasters. No geographic degrees are used as derivative distances.
- **Vertical comparison:** ScaleBridge converts recognized linear vertical units to metres, subtracts each source's own valid-cell median, records both vertical references and explicitly warns that no datum reconciliation or absolute cross-body elevation comparison is performed. This is appropriate for the current relative-morphology scope, provided outputs remain described as such.
- **ScaleBridge NoData/resampling:** It warps elevation and a valid-data fraction separately, rejects cells below the configured valid fraction, and preserves invalid output cells as missing. It does not label upsampling as new information. Effective resolution is null for both current source manifests and warned about; the report correctly calls the selected posting a nominal grid floor, not measurement resolution.
- **Terrain derivatives:** A manually calculated 1 m-grid paraboloid `z=−(x²+y²)` at a point 2 m from its summit gives profile curvature `−2/(1+4²)^(3/2) = −0.0285336 m⁻¹`; the implementation returned `−0.0285336 m⁻¹`, matching the documented sign. Slope uses horizontal spacing, focal support is recorded, and NoData/edge policies are explicit.
- **Feature distance and eligibility:** The current weighted-distance formula matches an independent calculation from stored feature distances and configured weights for ranks 1–5. The run has 25 actual windows and separates coverage (94.031%) from distance. All features are required and the run profile calls its weights provisional; no missing feature is silently treated as zero.
- **Assessment scope:** Deterministic assessment labels soil, traction, material and environmental conditions as unavailable/additional evidence; it does not claim that similarity establishes rover safety or performance.
- **Validation status:** The actual persisted Terrain Twin is `UNVALIDATED`, correctly with no invented error metrics. The defects in SV-03/SV-04 apply to the future reference-backed validation path.

## Commands and results

- `uv run --directory backend pytest tests/scientific -q` — **68 passed in 3.59 s**.
- First attempted command, `uv run --directory backend pytest backend/tests/scientific -q` — failed because that path is incorrect after selecting the backend project directory; no tests ran. Corrected command above passed.
- Independent saved-score calculation for ranks 1–5 reproduced each weighted distance to floating-point precision. Rank 1: `2c36fc1941cc6e7bf528b0e5`, distance `0.11906692734805222`, reported iid bootstrap SE `0.006297975805193287`, evidence coverage `0.9403122130394858`.
- Independent analytic profile-curvature calculation matched the implementation as stated above.
- Validation failure reproduction: same raster path plus caller-supplied different hashes returned MAE/RMSE zero and 25 samples.
- Official product check: Copernicus identifies GLO-30 as DSM and describes buildings, infrastructure and vegetation in the surface [official product documentation](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM). HiRISE explains that DTM post spacing is commonly about four times the source image scale and distinguishes posting from precision [HiRISE DTM documentation](https://hirise.lpl.arizona.edu/dtm/about.php).

## Acceptance decision

**Scientific acceptance: NOT ACCEPTED.** Findings SV-01 through SV-04 are high severity. The present candidate list can be retained as a reproducible exploratory ranking of the recorded DEM-derived surface distributions, with the stated bounds, sources, provisional weights and limitations. It must not be presented as a validated bare-earth analogue ranking or as independently validated mesh accuracy until those findings are corrected and re-audited. No Phase 9 or production-readiness claim is approved by this audit.

The next work should resolve SV-01 through SV-04 in a documented methodology revision, add the specified regression tests, regenerate downstream artifacts under a new processing version, and repeat this audit. This report intentionally does not implement those methodology changes.

## Follow-up implementation evidence — 2026-11-15

The following corrections resolve the specific findings requested for the Terrain Twin/discovery workflow. They do not constitute a blanket claim that all scientific limitations in this report are resolved; see remaining limitations below.

| Finding | Follow-up |
|---|---|
| SV-01: incompatible raster-wide landform thresholds | Terrain Analytics now accepts a shared `landform_standardization_scale_m`; the Earth map uses the planetary reference TPI scale, records it, and discovery rejects mismatched scales. A regression test covers context/extent independence. |
| SV-02: Copernicus DSM treated as terrain | Dataset surface type is propagated into analysis/discovery provenance. Discovery requires Earth `bare_earth_dtm`; the Terrain Twin candidate feed also verifies the source manifest is a bare-earth DTM. Copernicus GLO-30 DSM candidates are excluded from this bare-earth workflow. |
| SV-03: unproven independent lineage | Validation checks source/reference dataset IDs, checksums and recorded lineage intersections, in addition to distinct product identity and compatible vertical metadata. A hash-forgery/same-raster regression test rejects false independence. |
| SV-04: unsupported resolution comparison and intermediate-raster validation | Validation rasterizes the exported decimated mesh's piecewise-planar triangles. The mesh surface and reference are area-averaged to common metric support no finer than their nominal support; valid fractions define common support and are reported. Regression tests cover coarse-reference support. |
| SV-05: pixel-independent bootstrap | Discovery now resamples joint 2-D spatial blocks, preserving feature co-variation and reports the result as a block-bootstrap standard error. This reduces pixel-level pseudoreplication but remains sensitive to the chosen block size and the small number of blocks in small windows; it is not a full spatial covariance model. |

The regenerated bounded discovery is `f723d7a38ca2f4afe877` using HiRISE Jezero and the USGS 2018 bare-earth lidar DTM. It generated/evaluated 25 windows; 25 passed the configured discovery evidence gate. Terrain Twin only lists the 13 windows whose full polygons also fit within the immutable source raster, sorted by their original discovery rank. The top two discovery windows are not mesh-eligible because they extend outside that source coverage. Candidate `b83aee1fc91627b419cbbfd6` is the highest-ranked fully supported window (rank 3), with weighted distance 0.185764, evidence coverage 94.031%, block-bootstrap SE 0.019921 and feature-level distances displayed in the UI. This remains a bounded relative terrain-distribution comparison, not a globally validated analogue claim.

Terrain Twin `ce05abebd2df901499aeb752` was validated against the separate historical USGS NED 1/3 arc-second product `USGS_13_n44w113_20021201` dated 2002. The source is a distinct 2018 lidar project; both declare NAVD88 metres and have distinct manifest lineage IDs. At 10.285 m nominal common support, the exported mesh comparison yielded 38,338 valid samples, 4,055,450.91 m² valid area, 93.956% coverage, MAE 0.58577 m, RMSE 0.74626 m, median absolute error 0.47833 m and bias 0.19758 m. Effective resolution is unavailable for both products, and the older reference is not contemporary ground truth. These metrics validate agreement with that independent reference only; they do not validate cross-planet similarity or rover performance.

## Updated disposition

The named high-severity findings SV-01 through SV-04 have implementation and test evidence for correction. SV-05's uncertainty estimate is now spatial-block-based but still has block-size limitations. SV-06 (roughness definition shares slope-related variation and may be double-counted in the weighted metric) remains a scientific limitation requiring methodology review. Search scope is local and bounded; effective resolution remains undocumented for the demonstrated DEMs. Therefore the earlier blanket “not accepted” statement is superseded for the named corrections, but this report does **not** grant unrestricted scientific acceptance or production readiness. The appropriate claim remains a reproducible bounded morphology comparison with independently reference-compared mesh geometry and explicit limitations.
