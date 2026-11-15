# Development roadmap and acceptance gates

| Phase | Scope | State |
|---|---|---|
| 1 | Independent frontend/backend foundation, health, database and quality checks | Implemented |
| 2 | Planetary and Earth source ingestion, product manifests and checksums | Implemented for MOLA regional source and Copernicus GLO-30 tile; LOLA/HiRISE/NASADEM product downloaders remain limited/deferred as documented |
| 3 | ScaleBridge spatial support, CRS, resolution, vertical metadata and NoData handling | Implemented and tested |
| 4 | Independent terrain feature calculations and feature reports | Implemented and tested; low MOLA valid support limits regional conclusions |
| 5 | Bounded candidate window discovery, distances, evidence gates, ranks and provenance | Implemented; actual run returned no rankable candidates at current coverage |
| 6 | DEM-derived mesh, export and independent validation status | Implemented; current candidate mesh is visualization-only and unvalidated |
| 7 | Deterministic experiment assessment and JSON/PDF Evidence Passport | Implemented |
| 8 | Product/API integration, durable jobs, comparison maps, frontend journey, reliability/security/performance checks | In progress; see Phase 8 report and open gates |

Phase completion is based on executed acceptance evidence, not implementation
presence. No production-ready claim is valid until the clean-install workflow,
reliability and deployment gates in the Phase 8 specification are all
demonstrated. Broader planetary/Earth coverage and Moon acquisition are
subsequent scientific data work, not implied by the initial local workflow.
