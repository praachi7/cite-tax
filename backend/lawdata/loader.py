"""Load the law-as-data YAML files into validated models."""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import Assumption, ConcordanceEntry, ManifestEntry, ParamFile, SourceEntry

ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = ROOT / "corpus"
PARAMS_DIR = ROOT / "params"
SOURCES_DIR = ROOT / "sources"


def _read(path: Path) -> dict:
    with open(path, encoding="utf8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def load_registry(path: Path = CORPUS_DIR / "registry.yaml") -> list[SourceEntry]:
    return [SourceEntry(**row) for row in _read(path)["sources"]]


def load_manifest(path: Path = CORPUS_DIR / "sources_manifest.yaml") -> list[ManifestEntry]:
    return [ManifestEntry(**row) for row in _read(path)["sources"]]


def load_concordance(path: Path = CORPUS_DIR / "concordance.yaml") -> list[ConcordanceEntry]:
    return [ConcordanceEntry(**row) for row in _read(path)["concordance"]]


def load_assumptions(path: Path = CORPUS_DIR / "assumptions.yaml") -> list[Assumption]:
    return [Assumption(**row) for row in _read(path)["assumptions"]]


def load_param_file(path: Path) -> ParamFile:
    return ParamFile(**_read(path))


def load_all_param_files(directory: Path = PARAMS_DIR) -> dict[str, ParamFile]:
    return {p.name: load_param_file(p) for p in sorted(directory.glob("*.yaml"))}
