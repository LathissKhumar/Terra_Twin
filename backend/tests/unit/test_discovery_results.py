"""Regression tests for looking up candidates across persisted discovery runs."""

import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.services.discovery_results import report_for_candidate


def test_candidate_lookup_finds_a_candidate_in_an_older_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    older = tmp_path / "results" / "analogue_discovery" / "older" / "report.json"
    newer = tmp_path / "results" / "analogue_discovery" / "newer" / "report.json"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    candidate_id = "a" * 24
    older.write_text(
        json.dumps({"run_id": "older", "candidates": [{"candidate_id": candidate_id}]})
    )
    newer.write_text(json.dumps({"run_id": "newer", "candidates": []}))
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer, ns=(2_000_000_000, 2_000_000_000))
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)

    path, report = report_for_candidate(candidate_id)

    assert path == older
    assert report["run_id"] == "older"


def test_candidate_lookup_rejects_unknown_or_malformed_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    with pytest.raises(HTTPException) as missing:
        report_for_candidate("a" * 24)
    assert missing.value.status_code == 404
    with pytest.raises(HTTPException) as malformed:
        report_for_candidate("../etc/passwd")
    assert malformed.value.status_code == 404
