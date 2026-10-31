"""Consistency checks across the law-as-data files.

Run from the repository root:

    python -m lawdata.validate            # structure and cross-references
    python -m lawdata.validate --files    # also check source files and checksums on disk

(Set PYTHONPATH=backend, or run through pytest, which is configured to do so.)
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from .loader import (PARAMS_DIR, SOURCES_DIR, load_all_param_files, load_assumptions,
                     load_concordance, load_manifest, load_registry)
from .models import DocType, ParamFile, ParamScope

# authority_rank that each document type must carry (see registry.yaml header)
RANK_BY_DOCTYPE = {
    DocType.statute: 1, DocType.rule: 1, DocType.us_statute: 1,
    DocType.notification: 2, DocType.form: 2,
    DocType.treaty: 3, DocType.protocol: 3, DocType.mou: 3,
    DocType.faq: 4, DocType.us_guidance: 4,
}


def check_registry_and_manifest(sources_dir: Path | None = None) -> list[str]:
    """Return a list of problems (empty if everything is consistent)."""
    problems: list[str] = []
    registry = load_registry()
    manifest = load_manifest()

    ids = [s.id for s in registry]
    if len(ids) != len(set(ids)):
        problems.append("duplicate source ids in registry.yaml")
    files = [s.file for s in registry]
    if len(files) != len(set(files)):
        problems.append("a file appears twice in registry.yaml")

    for s in registry:
        want = RANK_BY_DOCTYPE[s.doc_type]
        if s.authority_rank != want:
            problems.append(f"{s.id}: doc_type {s.doc_type.value} needs authority_rank {want}, found {s.authority_rank}")
        if s.tax_year_first and s.tax_year_last and s.tax_year_first > s.tax_year_last:
            problems.append(f"{s.id}: tax_year_first is after tax_year_last")
        if s.valid_from and s.valid_to and s.valid_from > s.valid_to:
            problems.append(f"{s.id}: valid_from is after valid_to")

    reg_by_id = {s.id: s for s in registry}
    man_by_id = {m.id: m for m in manifest}
    for i in reg_by_id.keys() - man_by_id.keys():
        problems.append(f"{i}: in registry but missing from manifest")
    for i in man_by_id.keys() - reg_by_id.keys():
        problems.append(f"{i}: in manifest but missing from registry")
    for i in reg_by_id.keys() & man_by_id.keys():
        if reg_by_id[i].file != man_by_id[i].file:
            problems.append(f"{i}: file name differs between registry and manifest")

    if sources_dir is not None:
        for m in manifest:
            p = sources_dir / m.file
            if not p.exists():
                problems.append(f"{m.id}: file not found in {sources_dir}: {m.file}")
                continue
            data = p.read_bytes()
            if m.size_bytes is not None and len(data) != m.size_bytes:
                problems.append(f"{m.id}: size differs from manifest")
            if m.sha256 and hashlib.sha256(data).hexdigest() != m.sha256:
                problems.append(f"{m.id}: sha256 differs from manifest (file changed?)")
    return problems


def check_param_files(files: dict[str, ParamFile] | None = None) -> list[str]:
    """Citation prefixes must exist in the registry; all parameter files share one key set."""
    problems: list[str] = []
    files = load_all_param_files(PARAMS_DIR) if files is None else files
    prefixes = {s.cite_prefix for s in load_registry()}
    for name, pf in files.items():
        for key, param in pf.params.items():
            for c in param.sources:
                if c.split(":", 1)[0] not in prefixes:
                    problems.append(f"{name}: {key}: unknown citation prefix in {c!r}")
    # Files for different Acts and tax years must define exactly the same keys.
    year_files = [n for n, pf in files.items() if pf.scope == ParamScope.india_tax_year]
    if len(year_files) > 1:
        first = year_files[0]
        base = set(files[first].params)
        for n in year_files[1:]:
            keys = set(files[n].params)
            for k in sorted(base - keys):
                problems.append(f"{n}: missing key {k} (present in {first})")
            for k in sorted(keys - base):
                problems.append(f"{first}: missing key {k} (present in {n})")
    # Each year file must be for a distinct Act/tax-year pair.
    pairs = [(files[n].act_id, files[n].tax_year) for n in year_files]
    if len(pairs) != len(set(pairs)):
        problems.append("two parameter files are for the same Act and tax year")
    return problems


def check_concordance() -> list[str]:
    """Both sides of every row must use a known citation prefix; no row may repeat."""
    problems: list[str] = []
    prefixes = {s.cite_prefix for s in load_registry()}
    seen: set[tuple[str, str]] = set()
    for row in load_concordance():
        for ref in (row.old_ref, row.new_ref):
            if ref.split(":", 1)[0] not in prefixes:
                problems.append(f"concordance: unknown citation prefix in {ref!r}")
        key = (row.old_ref, row.new_ref)
        if key in seen:
            problems.append(f"concordance: duplicate row {row.old_ref} -> {row.new_ref}")
        seen.add(key)
        if row.old_ref == row.new_ref:
            problems.append(f"concordance: {row.old_ref} maps to itself")
    return problems


def check_assumptions(files: dict[str, ParamFile] | None = None) -> list[str]:
    """Ids and flags unique; citation prefixes known; used_by keys exist in every year file."""
    problems: list[str] = []
    files = load_all_param_files(PARAMS_DIR) if files is None else files
    prefixes = {s.cite_prefix for s in load_registry()}
    year_files = {n: pf for n, pf in files.items() if pf.scope == ParamScope.india_tax_year}
    assumptions = load_assumptions()
    ids = [a.id for a in assumptions]
    if len(ids) != len(set(ids)):
        problems.append("assumptions: duplicate ids")
    flags = [a.config_flag for a in assumptions]
    if len(flags) != len(set(flags)):
        problems.append("assumptions: two assumptions share a config flag")
    for a in assumptions:
        for r in a.readings:
            for c in r.citations:
                if c.split(":", 1)[0] not in prefixes:
                    problems.append(f"{a.id}: unknown citation prefix in {c!r}")
        if a.status.value == "contested" and not any(r.citations for r in a.readings):
            problems.append(f"{a.id}: a contested assumption must cite the provisions behind its readings")
        for key in a.used_by:
            for n, pf in year_files.items():
                if key not in pf.params:
                    problems.append(f"{a.id}: used_by key {key} is missing from {n}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", action="store_true", help="also verify source files and checksums on disk")
    args = ap.parse_args(argv)
    problems = check_registry_and_manifest(SOURCES_DIR if args.files else None)
    problems += check_concordance()
    problems += check_param_files()
    problems += check_assumptions()
    for p in problems:
        print("PROBLEM:", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
