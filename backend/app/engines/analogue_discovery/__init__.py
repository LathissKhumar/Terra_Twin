"""Earth terrain analogue window generation and ranking."""

from app.engines.analogue_discovery.engine import (
    cluster_and_rank_candidates,
    compare_feature_distributions,
    generate_candidate_windows,
    load_mission_profile,
    run_discovery,
    score_feature_profiles,
)

__all__ = [
    "cluster_and_rank_candidates",
    "compare_feature_distributions",
    "generate_candidate_windows",
    "load_mission_profile",
    "run_discovery",
    "score_feature_profiles",
]
