"""Validate the middle-school GeoJSON snapshots and explicit crosswalk."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BoundaryValidation:
    errors: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def validate_boundaries(project_root: Path) -> BoundaryValidation:
    result = BoundaryValidation()
    schools = _load(project_root / "data" / "schools.json")
    school_ids = {school["id"] for school in schools}
    manifest_doc = _load(project_root / "data" / "boundary-manifest.json")
    crosswalk_doc = _load(project_root / "data" / "boundary-crosswalk.json")
    snapshots_doc = _load(project_root / "data" / "source-snapshot.json")
    manifest = manifest_doc.get("entries", [])
    crosswalk = {entry["path"]: entry for entry in crosswalk_doc.get("files", [])}
    snapshots = {entry["output"]: entry for entry in snapshots_doc.get("sources", [])}

    if len(manifest) != 7:
        result.errors.append(f"Expected 7 boundary layers, found {len(manifest)}")
    if len(crosswalk) != len(manifest) or len(snapshots) != len(manifest):
        result.errors.append("Manifest, crosswalk, and source snapshots must cover the same layers")

    feature_total = matched_features = unmatched_features = 0
    linked_school_ids: set[str] = set()
    for entry in manifest:
        relative = Path(entry.get("path", ""))
        label = relative.as_posix()
        if relative.is_absolute() or ".." in relative.parts:
            result.errors.append(f"Unsafe boundary path: {label}")
            continue
        path = project_root / relative
        if not path.is_file():
            result.errors.append(f"Missing boundary: {label}")
            continue
        geojson = _load(path)
        features = geojson.get("features") if isinstance(geojson, dict) else None
        if not isinstance(features, list):
            result.errors.append(f"{label} is not a GeoJSON FeatureCollection")
            continue
        if len(features) != entry.get("feature_count"):
            result.errors.append(f"{label} feature count differs from manifest")
        feature_total += len(features)

        snapshot = snapshots.get(label)
        if not snapshot:
            result.errors.append(f"Missing source snapshot for {label}")
        else:
            payload = path.read_bytes()
            if snapshot.get("bytes") != len(payload):
                result.errors.append(f"{label} byte count differs from snapshot")
            if snapshot.get("sha256") != hashlib.sha256(payload).hexdigest():
                result.errors.append(f"{label} SHA-256 differs from snapshot")
            if snapshot.get("features") != len(features):
                result.errors.append(f"{label} snapshot feature count differs")

        file_crosswalk = crosswalk.get(label)
        if not file_crosswalk or not isinstance(file_crosswalk.get("mappings"), dict):
            result.errors.append(f"Missing crosswalk for {label}")
            continue
        mappings = file_crosswalk["mappings"]
        name_field = entry.get("name_field")
        source_names = [str(feature.get("properties", {}).get(name_field)) for feature in features]
        missing_names = sorted(set(source_names) - set(mappings))
        extra_names = sorted(set(mappings) - set(source_names))
        if missing_names:
            result.errors.append(f"{label} unmapped feature names: {missing_names}")
        if extra_names:
            result.errors.append(f"{label} crosswalk names absent from GeoJSON: {extra_names}")

        for source_name in source_names:
            mapping = mappings.get(source_name, {})
            status = mapping.get("status")
            school_id = mapping.get("school_id")
            if status in {"matched", "matched_alias", "matched_context"}:
                matched_features += 1
                if school_id not in school_ids:
                    result.errors.append(f"{label}:{source_name} points to unknown school {school_id!r}")
                else:
                    linked_school_ids.add(school_id)
            elif status == "unmatched":
                unmatched_features += 1
                if school_id is not None or not mapping.get("reason"):
                    result.errors.append(f"{label}:{source_name} unmatched record needs null ID and reason")
            else:
                result.errors.append(f"{label}:{source_name} has invalid status {status!r}")

        if entry.get("jurisdiction") == "Falls Church City, VA" and entry.get("boundary_type") != "municipal_boundary":
            result.errors.append("Falls Church must remain municipal context, not an attendance boundary")

    result.summary.update(
        layers=len(manifest),
        features=feature_total,
        matched_features=matched_features,
        unmatched_features=unmatched_features,
        linked_schools=len(linked_school_ids),
    )
    return result


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    result = validate_boundaries(project_root)
    if result.ok:
        print("PASS: " + ", ".join(f"{key}={value}" for key, value in result.summary.items()))
        return 0
    print(f"FAIL: {len(result.errors)} boundary validation error(s)")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
