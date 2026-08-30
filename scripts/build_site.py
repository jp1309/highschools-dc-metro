"""Build the minimal static artifact published by GitHub Pages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (ROOT / "_site").resolve()


def copy_file(relative_path: str, *, source_root: Path = ROOT, destination_root: Path = OUTPUT) -> None:
    source_root = source_root.resolve()
    destination_root = destination_root.resolve()
    source = (source_root / relative_path).resolve()
    if source_root not in source.parents:
        raise RuntimeError(f"Refusing path outside repository: {relative_path}")
    if not source.is_file():
        raise FileNotFoundError(relative_path)
    destination = destination_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_project(source_root: Path, destination_root: Path) -> None:
    """Copy one self-contained map without leaking workbooks, scripts, or tests."""
    manifest_path = source_root / "data" / "boundary-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest if isinstance(manifest, list) else manifest.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(f"Invalid boundary manifest: {manifest_path}")

    for path in (
        "index.html",
        "data/schools.json",
        "data/boundary-manifest.json",
        "data/boundary-crosswalk.json",
        "data/rating-evidence.json",
        "data/source-snapshot.json",
        "config/rating-sources.json",
    ):
        copy_file(path, source_root=source_root, destination_root=destination_root)

    if (source_root / "data" / "school-locations.json").is_file():
        copy_file("data/school-locations.json", source_root=source_root, destination_root=destination_root)

    project_config = source_root / "config" / "project.json"
    if project_config.is_file():
        copy_file("config/project.json", source_root=source_root, destination_root=destination_root)

    assets = source_root / "assets"
    if not assets.is_dir():
        raise FileNotFoundError(assets)
    shutil.copytree(assets, destination_root / "assets")

    for entry in entries:
        relative_path = entry["path"]
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise RuntimeError(f"Unsafe manifest path: {relative_path}")
        copy_file(relative_path, source_root=source_root, destination_root=destination_root)


def main() -> int:
    if OUTPUT.parent != ROOT or OUTPUT.name != "_site":
        raise RuntimeError(f"Unsafe output path: {OUTPUT}")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir()

    copy_project(ROOT, OUTPUT)
    copy_file("404.html")

    middle_root = ROOT / "middle-schools"
    if not middle_root.is_dir():
        raise FileNotFoundError("middle-schools")
    copy_project(middle_root, OUTPUT / "middle-schools")

    forbidden = [path for path in OUTPUT.rglob("*") if path.name == "outputs" or path.suffix.lower() == ".xlsx"]
    if forbidden:
        raise RuntimeError(f"Private/source artifacts leaked into site: {forbidden}")

    files = sorted(path for path in OUTPUT.rglob("*") if path.is_file())
    total_bytes = sum(path.stat().st_size for path in files)
    print(f"Built {len(files)} files in {OUTPUT.relative_to(ROOT)} ({total_bytes:,} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
