from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from equity_platform.text_ie.learned import (
    PINNED_SPAN_MODEL_SPECS,
    download_span_model_snapshots,
    load_verified_span_model_snapshots,
)


def test_registered_span_models_download_to_pinned_content_addressed_directories(
    tmp_path,
) -> None:
    calls = []

    def downloader(**kwargs):
        calls.append(kwargs)
        destination = Path(kwargs["local_dir"])
        destination.mkdir(parents=True)
        (destination / "config.json").write_text("{}", encoding="utf-8")
        (destination / "model.safetensors").write_bytes(b"weights")
        return str(destination)

    snapshots = download_span_model_snapshots(
        tmp_path,
        downloader=downloader,
    )

    assert len(snapshots) == 3
    assert {call["repo_id"] for call in calls} == {
        spec.model_id for spec in PINNED_SPAN_MODEL_SPECS
    }
    assert all(call["revision"] for call in calls)
    assert all(call["local_dir"].endswith(call["revision"][:12]) for call in calls)
    assert all(snapshot.config_path.is_file() for snapshot in snapshots)
    assert all(snapshot.weight_path.is_file() for snapshot in snapshots)


def test_downloaded_model_snapshot_rejects_missing_weights(tmp_path) -> None:
    def downloader(**kwargs):
        destination = Path(kwargs["local_dir"])
        destination.mkdir(parents=True)
        (destination / "config.json").write_text("{}", encoding="utf-8")
        return str(destination)

    try:
        download_span_model_snapshots(
            tmp_path,
            specs=(PINNED_SPAN_MODEL_SPECS[0],),
            downloader=downloader,
        )
    except RuntimeError as exc:
        assert "weight" in str(exc).casefold()
    else:
        raise AssertionError("missing model weights must fail closed")


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def test_model_manifest_resolves_only_verified_local_snapshot(tmp_path) -> None:
    model_dir = tmp_path / PINNED_SPAN_MODEL_SPECS[0].storage_name
    model_dir.mkdir()
    config = b"{}"
    weights = b"verified-weights"
    (model_dir / "config.json").write_bytes(config)
    (model_dir / "model.safetensors").write_bytes(weights)
    manifest = tmp_path / "model_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.0.0",
        "runtime_authority": "RESEARCH_CHALLENGER_ONLY",
        "models": [{
            "model_id": PINNED_SPAN_MODEL_SPECS[0].model_id,
            "revision": PINNED_SPAN_MODEL_SPECS[0].revision,
            "local_path": str(model_dir),
            "config_sha256": _hash(config),
            "weight_sha256": _hash(weights),
        }],
    }), encoding="utf-8")

    snapshots = load_verified_span_model_snapshots(
        manifest,
        specs=(PINNED_SPAN_MODEL_SPECS[0],),
    )

    assert snapshots[0].local_path == model_dir.resolve()
    assert snapshots[0].model_id == PINNED_SPAN_MODEL_SPECS[0].model_id


def test_model_manifest_fails_closed_after_weight_tampering(tmp_path) -> None:
    model_dir = tmp_path / PINNED_SPAN_MODEL_SPECS[0].storage_name
    model_dir.mkdir()
    config = b"{}"
    original = b"original"
    weight_path = model_dir / "model.safetensors"
    (model_dir / "config.json").write_bytes(config)
    weight_path.write_bytes(original)
    manifest = tmp_path / "model_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.0.0",
        "runtime_authority": "RESEARCH_CHALLENGER_ONLY",
        "models": [{
            "model_id": PINNED_SPAN_MODEL_SPECS[0].model_id,
            "revision": PINNED_SPAN_MODEL_SPECS[0].revision,
            "local_path": str(model_dir),
            "config_sha256": _hash(config),
            "weight_sha256": _hash(original),
        }],
    }), encoding="utf-8")
    weight_path.write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="weight checksum"):
        load_verified_span_model_snapshots(
            manifest,
            specs=(PINNED_SPAN_MODEL_SPECS[0],),
        )


def test_model_manifest_fails_closed_when_a_required_snapshot_is_missing(tmp_path) -> None:
    manifest = tmp_path / "model_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "1.0.0",
        "runtime_authority": "RESEARCH_CHALLENGER_ONLY",
        "models": [],
    }), encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing pinned span model"):
        load_verified_span_model_snapshots(
            manifest,
            specs=(PINNED_SPAN_MODEL_SPECS[0],),
        )
