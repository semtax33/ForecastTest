from __future__ import annotations

import json
import tomllib

import pandas as pd

from equity_platform.artifacts import sha256_file
from scripts.architecture.v26_fourth_holdout_annotations import ANNOTATIONS
from scripts.architecture.v26_fourth_holdout_candidates import CANDIDATES, CONFIG, verify_code_snapshot


def test_fourth_holdout_artifacts_are_frozen_and_exhaustive() -> None:
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    verify_code_snapshot(config)
    assert sha256_file(CANDIDATES) == config["candidate_artifact"]["sha256"]
    assert sha256_file(ANNOTATIONS) == config["annotation_artifact"]["sha256"]
    candidates = pd.read_csv(CANDIDATES)
    annotations = [json.loads(line) for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines() if line]
    assert len(candidates) == len(annotations) == 100
    assert set(candidates["candidate_id"]) == {item["candidate_id"] for item in annotations}
