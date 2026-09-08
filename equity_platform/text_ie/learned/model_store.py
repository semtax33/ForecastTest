from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
from typing import Callable, Iterable, Mapping


SnapshotDownloader = Callable[..., str]


@dataclass(frozen=True)
class PinnedSpanModelSpec:
    model_id: str
    revision: str

    @property
    def storage_name(self) -> str:
        return f"{self.model_id.replace('/', '--')}--{self.revision[:12]}"


@dataclass(frozen=True)
class DownloadedSpanModel:
    model_id: str
    revision: str
    local_path: Path
    config_path: Path
    weight_path: Path
    size_bytes: int


PINNED_SPAN_MODEL_SPECS = (
    PinnedSpanModelSpec(
        "AAU-NLP/BERT-SL1000",
        "ea3127ed19376e173d0ab9a31f91e61732764954",
    ),
    PinnedSpanModelSpec(
        "AAU-NLP/Cal-BERT-SL1000",
        "fef2bc3a40f347a672d61e9b169471c5c3c72d65",
    ),
    PinnedSpanModelSpec(
        "fastino/gliner2-base-v1",
        "8437ba583a733d87f56ae902f3b197934eedd58e",
    ),
)


_ALLOW_PATTERNS = (
    "config.json",
    "model.safetensors",
    "pytorch_model.bin",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.txt",
    "spm.model",
    "encoder_config/config.json",
)


def _default_downloader(**kwargs) -> str:
    hub = import_module("huggingface_hub")
    return str(hub.snapshot_download(**kwargs))


def download_span_model_snapshots(
    destination: Path,
    *,
    specs: Iterable[PinnedSpanModelSpec] = PINNED_SPAN_MODEL_SPECS,
    downloader: SnapshotDownloader = _default_downloader,
) -> tuple[DownloadedSpanModel, ...]:
    """Materialize pinned, minimal model snapshots into the Bronze model store."""

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    snapshots = []
    for spec in tuple(specs):
        local_dir = destination / spec.storage_name
        downloaded = Path(downloader(
            repo_id=spec.model_id,
            revision=spec.revision,
            local_dir=str(local_dir),
            allow_patterns=list(_ALLOW_PATTERNS),
        ))
        config_path = downloaded / "config.json"
        weight_path = next(
            (
                downloaded / name
                for name in ("model.safetensors", "pytorch_model.bin")
                if (downloaded / name).is_file()
            ),
            None,
        )
        if not config_path.is_file():
            raise RuntimeError(f"downloaded model has no config: {spec.model_id}")
        if weight_path is None:
            raise RuntimeError(f"downloaded model has no weight file: {spec.model_id}")
        size_bytes = sum(
            path.stat().st_size for path in downloaded.rglob("*") if path.is_file()
        )
        snapshots.append(DownloadedSpanModel(
            model_id=spec.model_id,
            revision=spec.revision,
            local_path=downloaded.resolve(),
            config_path=config_path.resolve(),
            weight_path=weight_path.resolve(),
            size_bytes=size_bytes,
        ))
    return tuple(snapshots)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_verified_span_model_snapshots(
    manifest_path: Path,
    *,
    specs: Iterable[PinnedSpanModelSpec] = PINNED_SPAN_MODEL_SPECS,
) -> tuple[DownloadedSpanModel, ...]:
    """Resolve pinned local checkpoints only after provenance and hash checks."""

    manifest_path = Path(manifest_path).resolve()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid span model manifest: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("span model manifest root must be an object")
    if payload.get("schema_version") != "1.0.0":
        raise RuntimeError("unsupported span model manifest schema")
    if payload.get("runtime_authority") != "RESEARCH_CHALLENGER_ONLY":
        raise RuntimeError("span model manifest may not grant valuation authority")
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise RuntimeError("span model manifest requires a model list")

    pinned = {(spec.model_id, spec.revision) for spec in tuple(specs)}
    root = manifest_path.parent
    seen = set()
    snapshots = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise RuntimeError("span model manifest row must be an object")
        identity = (str(row.get("model_id", "")), str(row.get("revision", "")))
        if identity not in pinned:
            raise RuntimeError(f"unpinned span model identity: {identity[0]}")
        if identity in seen:
            raise RuntimeError(f"duplicate span model identity: {identity[0]}")
        seen.add(identity)
        local_path = Path(str(row.get("local_path", ""))).resolve()
        try:
            local_path.relative_to(root)
        except ValueError as exc:
            raise RuntimeError("span model path escapes the manifest store") from exc
        config_path = local_path / "config.json"
        weight_path = next(
            (
                local_path / name
                for name in ("model.safetensors", "pytorch_model.bin")
                if (local_path / name).is_file()
            ),
            None,
        )
        if not config_path.is_file() or weight_path is None:
            raise RuntimeError(f"incomplete span model snapshot: {identity[0]}")
        if _file_sha256(config_path) != str(row.get("config_sha256", "")):
            raise RuntimeError(f"config checksum mismatch: {identity[0]}")
        if _file_sha256(weight_path) != str(row.get("weight_sha256", "")):
            raise RuntimeError(f"weight checksum mismatch: {identity[0]}")
        size_bytes = sum(
            path.stat().st_size for path in local_path.rglob("*") if path.is_file()
        )
        snapshots.append(DownloadedSpanModel(
            model_id=identity[0],
            revision=identity[1],
            local_path=local_path,
            config_path=config_path,
            weight_path=weight_path,
            size_bytes=size_bytes,
        ))
    missing = pinned - seen
    if missing:
        missing_ids = ", ".join(sorted(model_id for model_id, _ in missing))
        raise RuntimeError(f"missing pinned span model snapshot: {missing_ids}")
    return tuple(snapshots)


__all__ = [
    "DownloadedSpanModel",
    "PINNED_SPAN_MODEL_SPECS",
    "PinnedSpanModelSpec",
    "download_span_model_snapshots",
    "load_verified_span_model_snapshots",
]
