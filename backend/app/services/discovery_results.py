"""Lookup helpers for immutable, persisted analogue discovery runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.core.config import settings

_CANDIDATE_ID = re.compile(r"^[0-9a-f]{24}$")


def report_for_candidate(candidate_id: str) -> tuple[Path, dict[str, Any]]:
    """Return the exact stored discovery report containing this candidate."""
    if not _CANDIDATE_ID.fullmatch(candidate_id):
        raise HTTPException(status_code=404, detail="Candidate was not found")

    report_paths = sorted(
        (settings.results_dir / "analogue_discovery").glob("*/report.json"),
        key=lambda item: item.stat().st_mtime_ns,
        reverse=True,
    )
    for report_path in report_paths:
        try:
            report = json.loads(report_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        candidates = report.get("candidates") if isinstance(report, dict) else None
        if isinstance(candidates, list) and any(
            isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id
            for candidate in candidates
        ):
            return report_path, report
    raise HTTPException(
        status_code=404, detail="Candidate is not present in completed discovery results"
    )
