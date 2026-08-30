"""Build the minimal static artifact published by GitHub Pages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (ROOT / "_site").resolve()


def copy_file(relative_path: str) -> None:
    source = (ROOT / relative_path).resolve()
    if ROOT not in source.parents:
        raise RuntimeError(f"Refusing path outside repository: {relative_path}")
    if not source.is_file():
        raise FileNotFoundError(relative_path)
    destination = OUTPUT / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> int:
    if OUTPUT.parent != ROOT or OUTPUT.name != "_site":
        raise RuntimeError(f"Unsafe output path: {OUTPUT}")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()

    manifest_path = ROOT / "data" / "boundary-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for path in (
        "index.html",
        "404.html",
        "data/schools.json",
        "data/boundary-manifest.json",
        "data/boundary-crosswalk.json",
        "data/rating-evidence.json",
        "data/source-snapshot.json",
        "config/rating-sources.json",
    ):
        copy_file(path)

    assets = ROOT / "assets"
    if not assets.is_dir():
        raise FileNotFoundError("assets")
    shutil.copytree(assets, OUTPUT / "assets")

    for entry in manifest:
        copy_file(entry["path"])

    files = sorted(path for path in OUTPUT.rglob("*") if path.is_file())
    total_bytes = sum(path.stat().st_size for path in files)
    print(f"Built {len(files)} files in {OUTPUT.relative_to(ROOT)} ({total_bytes:,} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
