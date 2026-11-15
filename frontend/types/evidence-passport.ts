export type PassportFeature = {
  evidence_status: "SUPPORTED_WITH_LIMITS" | "INSUFFICIENT_EVIDENCE";
  interpretation: string;
  comparison: {
    method: string;
    units: string;
    reference_median: number | null;
    candidate_median: number | null;
    median_difference: number | null;
    normalized_distance: number | null;
    distance_standard_error: number | null;
    reference_sample_count: number;
    candidate_sample_count: number;
    reference_coverage: number;
    candidate_coverage: number;
    reference_summary: Record<string, number>;
    candidate_summary: Record<string, number>;
  };
};

export type AssessmentConclusion = {
  conclusion_id: string;
  category: string;
  conclusion: string;
  evidence_status: string;
  evidence_interpretation: string;
  evidence: { source_type: string; source_record_id: string; source_dataset_id: string | null; comparison_method: string; measurement: Record<string, unknown> }[];
  missing_information: string[];
  limitations: string[];
};

export type EvidencePassport = {
  passport_schema_version: string;
  passport_id: string;
  created_at_utc: string;
  reproducibility_sha256: string;
  candidate: {
    candidate_id: string;
    discovery_run_id: string;
    discovery_status: "eligible" | "insufficient_evidence";
    ranking: number | null;
    centroid_wgs84: [number, number];
    geographic_boundary_wgs84: [number, number][];
    evidence_coverage: number;
  };
  planetary_reference: { body: string; product: string; dataset_id: string; reference_boundary_body_lon_lat: [number, number, number, number]; coordinate_body: string; width_m: number; height_m: number; effective_resolution_m: number | null; effective_resolution_status: string };
  mission_profile: { profile_id: string; version: string; experiment_name: string; profile_status: string; weights: Record<string, number>; weight_justifications: Record<string, string>; required_features: string[]; optional_evidence: string[]; additional_evidence_required: string[]; not_reproducible_by_earth_site_alone: string[]; known_limitations: string[] };
  source_datasets: { dataset_id: string; target_body: string; provider: string; product: string; version: string | null; source_url: string | null; raw_checksum_sha256: string; crs: string; dimensions: [number, number]; pixel_resolution: [number, number]; resolution_unit: string; vertical_units: string; vertical_reference: string }[];
  feature_evidence: Record<string, PassportFeature>;
  weighted_distance: { value: number | null; standard_error: number | null; interpretation: string; method: string };
  evidence_coverage: { overall: number; minimum_required_coverage: number; minimum_required_samples_per_surface: number; missing_features: string[]; by_feature: Record<string, number> };
  uncertainty: { method: string; instrument_or_dem_measurement_uncertainty: string; interpretation: string };
  terrain_twin: { terrain_twin_id: string; validation_status: string; validation_reason: string | null; validation_metrics: Record<string, unknown> | null; source_product: string; artifacts: Record<string, string> } | null;
  terrain_twin_validation_status: "validated" | "unvalidated" | "unavailable";
  assessment: { overall_evidence_status: string; conclusions: AssessmentConclusion[]; limitations: string[] };
  missing_evidence: string[];
  limitations: string[];
  processing: { discovery_engine_version: string; discovery_configuration: Record<string, unknown>; discovery_processing_configuration_sha256: string; scale_bridge: { run_id: string; target_resolution_m: number; target_resolution_basis: string; resampling: string; vertical_comparison_status: string; vertical_normalization: string }; terrain_analytics_run_ids: Record<string, string>; profile_configuration_sha256: string; terrain_twin_engine_version: string | null };
  provenance: { discovery_report_sha256: string; scale_bridge_report_sha256: string; dataset_manifest_sha256: Record<string, string>; terrain_twin_metadata_sha256: string | null; terrain_mesh_sha256: string | null; reproducibility_inputs: string[] };
};
