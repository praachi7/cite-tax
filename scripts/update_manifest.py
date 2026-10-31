"""Refresh or check the size and sha256 of each source file listed in corpus/sources_manifest.yaml.

    python scripts/update_manifest.py --check     # compare files on disk with the manifest
    python scripts/update_manifest.py --update    # rewrite size and checksum from the files on disk
"""
import argparse
import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "corpus" / "sources_manifest.yaml"
SOURCES = ROOT / "sources"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--update", action="store_true")
    args = ap.parse_args()

    text = MANIFEST.read_text(encoding="utf8")
    header = "".join(line for line in text.splitlines(keepends=True) if line.startswith("#"))
    data = yaml.safe_load(text)
    bad = 0
    for row in data["sources"]:
        p = SOURCES / row["file"]
        if not p.exists():
            print("MISSING:", row["file"])
            bad += 1
            continue
        raw = p.read_bytes()
        size, digest = len(raw), hashlib.sha256(raw).hexdigest()
        if (size, digest) != (row.get("size_bytes"), row.get("sha256")):
            if args.update:
                row["size_bytes"], row["sha256"] = size, digest
                print("UPDATED:", row["file"])
            else:
                print("DIFFERENT:", row["file"])
                bad += 1
    if args.update:
        with open(MANIFEST, "w", encoding="utf8", newline="\n") as fh:
            fh.write(header)
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True, width=110)
    print("OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
