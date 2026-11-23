"""Phase C step C2: extract the text of every registry source into build/text/<ID>.txt.

Uses `pdftotext -layout` (poppler); US documents (IRS_*, IRC_*) use reading order instead. Pages stay separated by form feeds (\\f), so
page N of the PDF is text.split("\\f")[N - 1]. Plain-text sources are copied as is.
Existing outputs are skipped unless --force is given.

Run from the repo root:  .venv/Scripts/python scripts/extract_text.py [--force] [ID ...]
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from lawdata.loader import load_registry  # noqa: E402

SOURCES = ROOT / "sources"
OUT = ROOT / "build" / "text"


def extract(source_id: str, file_name: str, force: bool) -> str:
    src = SOURCES / file_name
    dst = OUT / f"{source_id}.txt"
    if not src.exists():
        return f"MISSING  {source_id}: {file_name}"
    if dst.exists() and not force:
        return f"skip     {source_id}"
    if src.suffix.lower() == ".pdf":
        # US documents are set in two columns; -layout interleaves them, reading order does not.
        layout = [] if source_id.startswith(("IRS_", "IRC_")) else ["-layout"]
        subprocess.run(["pdftotext", *layout, "-enc", "UTF-8", str(src), str(dst)], check=True)
    else:
        shutil.copyfile(src, dst)
    pages = dst.read_text(encoding="utf-8", errors="replace").count("\f") or 1
    return f"ok       {source_id}: {pages} pages"


def main(argv: list[str]) -> int:
    force = "--force" in argv
    wanted = {a for a in argv if not a.startswith("--")}
    OUT.mkdir(parents=True, exist_ok=True)
    failed = False
    for s in load_registry():
        if wanted and s.id not in wanted:
            continue
        line = extract(s.id, s.file, force)
        failed |= line.startswith("MISSING")
        print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
