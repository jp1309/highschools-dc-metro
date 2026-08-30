"""Validate the repository's materialized school and boundary data.

The validator intentionally depends only on Python's standard library so it can
run locally and in CI before any site build or deployment.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCHOOL_COUNT = 84
SCHOOL_ID_RE = re.compile(r"^[a-z0-9_]+:[a-z0-9_]+$")
SCHOOL_YEAR_RE = re.compile(r"^\d{4}-\d{4}$")
RATING_DATE_RE = re.compile(r"^\d{4}(?:-(0[1-9]|1[0-2]))?$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
REGION_LAT = (38.4, 39.5)
REGION_LNG = (-77.8, -76.5)
JURISDICTION_PREFIXES = {
    "Arlington, VA": "arlington_va",
    "Fairfax County, VA": "fairfax_county_va",
    "Falls Church City, VA": "falls_church_city_va",
    "Alexandria City, VA": "alexandria_city_va",
    "Montgomery County, MD": "montgomery_county_md",
    "Prince George's County, MD": "prince_georges_county_md",
    "Washington, DC": "washington_dc",
}
SCHOOL_FIELDS = {
    "id": str,
    "name": str,
    "address": str,
    "rating": (int, type(None)),
    "lat": (int, float),
    "lng": (int, float),
    "jurisdiction": str,
    "rating_status": str,
    "rating_source": str,
    "rating_source_url": (str, type(None)),
    "rating_source_school_id": (str, type(None)),
    "rating_as_of": (str, type(None)),
    "rating_checked_at": (str, type(None)),
    "rating_method": str,
    "rating_evidence_id": (str, type(None)),
    "provenance_note": str,
}
MANIFEST_FIELDS = {
    "path": str,
    "jurisdiction": str,
    "source_name": str,
    "source_url": (str, type(None)),
    "name_field": str,
    "school_year": str,
    "boundary_type": str,
}


@dataclass
class ValidationResult:
    """Structured result suitable for the CLI and unit tests."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load_json(path: Path, result: ValidationResult) -> Any | None:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        result.errors.append(f"Missing required file: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"Cannot parse JSON {path}: {exc}")
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_school_schema(
    schools_data: Any, result: ValidationResult
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(schools_data, list):
        result.errors.append("data/schools.json must contain a JSON array")
        return [], {}

    schools: list[dict[str, Any]] = []
    for index, school in enumerate(schools_data):
        label = f"schools[{index}]"
        if not isinstance(school, dict):
            result.errors.append(f"{label} must be an object")
            continue
        schools.append(school)
        for key, expected_type in SCHOOL_FIELDS.items():
            if key not in school:
                result.errors.append(f"{label} is missing {key!r}")
                continue
            value = school[key]
            if key in {"lat", "lng"}:
                valid_type = _is_number(value)
            elif key == "rating":
                valid_type = value is None or (isinstance(value, int) and not isinstance(value, bool))
            else:
                valid_type = isinstance(value, expected_type)
            if not valid_type:
                result.errors.append(f"{label}.{key} has the wrong type")

        school_id = school.get("id")
        jurisdiction = school.get("jurisdiction")
        if isinstance(school_id, str):
            if not SCHOOL_ID_RE.fullmatch(school_id):
                result.errors.append(f"{label}.id is not a stable slug ID: {school_id!r}")
            expected_prefix = JURISDICTION_PREFIXES.get(jurisdiction)
            if expected_prefix is None:
                result.errors.append(f"{label} has an unknown jurisdiction: {jurisdiction!r}")
            elif not school_id.startswith(expected_prefix + ":"):
                result.errors.append(
                    f"{label}.id prefix does not match {jurisdiction!r}: {school_id!r}"
                )

        for key in ("name", "address", "provenance_note"):
            if isinstance(school.get(key), str) and not school[key].strip():
                result.errors.append(f"{label}.{key} must not be blank")

        rating = school.get("rating")
        if isinstance(rating, int) and not isinstance(rating, bool) and not 1 <= rating <= 10:
            result.errors.append(f"{label}.rating must be between 1 and 10")

        lat, lng = school.get("lat"), school.get("lng")
        if _is_number(lat) and (not math.isfinite(lat) or not REGION_LAT[0] <= lat <= REGION_LAT[1]):
            result.errors.append(f"{label}.lat is outside the DC metro region: {lat!r}")
        if _is_number(lng) and (not math.isfinite(lng) or not REGION_LNG[0] <= lng <= REGION_LNG[1]):
            result.errors.append(f"{label}.lng is outside the DC metro region: {lng!r}")

        status = school.get("rating_status")
        method = school.get("rating_method")
        source_url = school.get("rating_source_url")
        source_school_id = school.get("rating_source_school_id")
        checked_at = school.get("rating_checked_at")
        evidence_id = school.get("rating_evidence_id")
        if status not in {"verified", "not_available", "legacy_unverified"}:
            result.errors.append(f"{label}.rating_status is invalid")
        elif status == "legacy_unverified":
            if rating is None:
                result.errors.append(f"{label} legacy_unverified requires its inherited rating")
            if method != "legacy_transcription":
                result.errors.append(f"{label} legacy_unverified must use legacy_transcription")
            if any(value is not None for value in (source_url, source_school_id, checked_at, evidence_id)):
                result.errors.append(f"{label} legacy_unverified cannot claim verification evidence")
        else:
            if method not in {"authorized_bulk_feed", "user_supplied_manual_verification"}:
                result.errors.append(f"{label} current rating method is invalid")
            if status == "verified" and rating is None:
                result.errors.append(f"{label} verified rating must be numeric")
            if status == "not_available" and rating is not None:
                result.errors.append(f"{label} not_available rating must be null")
            if not isinstance(source_url, str) or not source_url.startswith("https://"):
                result.errors.append(f"{label} current rating requires an HTTPS source URL")
            if not isinstance(source_school_id, str) or not source_school_id.strip():
                result.errors.append(f"{label} current rating requires a provider school ID")
            if not isinstance(evidence_id, str) or not evidence_id.strip():
                result.errors.append(f"{label} current rating requires an evidence ID")
            if not isinstance(checked_at, str) or not UTC_RE.fullmatch(checked_at):
                result.errors.append(f"{label}.rating_checked_at must be RFC 3339 UTC")
            elif datetime.fromisoformat(checked_at.replace("Z", "+00:00")) > datetime.now(timezone.utc):
                result.errors.append(f"{label}.rating_checked_at must not be in the future")
        rating_as_of = school.get("rating_as_of")
        if rating_as_of is not None and (
            not isinstance(rating_as_of, str) or not RATING_DATE_RE.fullmatch(rating_as_of)
        ):
            result.errors.append(f"{label}.rating_as_of must use YYYY, YYYY-MM or null")

    if len(schools) != EXPECTED_SCHOOL_COUNT:
        result.errors.append(
            f"Expected {EXPECTED_SCHOOL_COUNT} school records, found {len(schools)}"
        )

    ids = [s.get("id") for s in schools if isinstance(s.get("id"), str)]
    names = [s.get("name", "").strip().casefold() for s in schools if isinstance(s.get("name"), str)]
    for school_id, count in Counter(ids).items():
        if count > 1:
            result.errors.append(f"Duplicate school ID: {school_id!r}")
    for name, count in Counter(names).items():
        if name and count > 1:
            result.errors.append(f"Duplicate school name (case-insensitive): {name!r}")

    return schools, {s["id"]: s for s in schools if isinstance(s.get("id"), str)}


def _validate_manifest_schema(
    manifest_data: Any, root: Path, result: ValidationResult
) -> list[dict[str, Any]]:
    if not isinstance(manifest_data, list):
        result.errors.append("data/boundary-manifest.json must contain a JSON array")
        return []

    manifest: list[dict[str, Any]] = []
    for index, item in enumerate(manifest_data):
        label = f"boundary-manifest[{index}]"
        if not isinstance(item, dict):
            result.errors.append(f"{label} must be an object")
            continue
        manifest.append(item)
        for key, expected_type in MANIFEST_FIELDS.items():
            if key not in item:
                result.errors.append(f"{label} is missing {key!r}")
            elif not isinstance(item[key], expected_type):
                result.errors.append(f"{label}.{key} has the wrong type")

        relative_path = item.get("path")
        if isinstance(relative_path, str):
            candidate = Path(relative_path)
            if candidate.is_absolute() or ".." in candidate.parts:
                result.errors.append(f"{label}.path must stay inside the project")
            elif candidate.suffix.lower() not in {".json", ".geojson"}:
                result.errors.append(f"{label}.path is not a JSON/GeoJSON file")

        jurisdiction = item.get("jurisdiction")
        if isinstance(jurisdiction, str) and jurisdiction not in JURISDICTION_PREFIXES:
            result.errors.append(f"{label} has an unknown jurisdiction: {jurisdiction!r}")
        school_year = item.get("school_year")
        if isinstance(school_year, str) and school_year != "unknown" and not SCHOOL_YEAR_RE.fullmatch(school_year):
            result.errors.append(f"{label}.school_year must be YYYY-YYYY or 'unknown'")
        if item.get("boundary_type") not in {"attendance_boundary", "municipal_boundary"}:
            result.errors.append(f"{label}.boundary_type is invalid")
        if isinstance(item.get("source_name"), str) and not item["source_name"].strip():
            result.errors.append(f"{label}.source_name must not be blank")
        source_url = item.get("source_url")
        if isinstance(source_url, str) and not source_url.startswith("https://"):
            result.errors.append(f"{label}.source_url must use HTTPS or be null")

    paths = [item.get("path") for item in manifest if isinstance(item.get("path"), str)]
    for path, count in Counter(paths).items():
        if count > 1:
            result.errors.append(f"Duplicate boundary path in manifest: {path!r}")

    alexandria = next((item for item in manifest if item.get("path") == "Alexandria.geojson"), None)
    if alexandria is None:
        result.errors.append("Manifest must include Alexandria.geojson")
    elif alexandria.get("boundary_type") != "municipal_boundary":
        result.errors.append("Alexandria.geojson must be declared as municipal_boundary")

    falls_church = next(
        (item for item in manifest if item.get("path") == "falls_church_city_boundary.geojson"),
        None,
    )
    if falls_church is None:
        result.errors.append("Manifest must include falls_church_city_boundary.geojson")
    elif falls_church.get("boundary_type") != "municipal_boundary":
        result.errors.append(
            "falls_church_city_boundary.geojson must be declared as municipal_boundary"
        )

    return manifest


def _validate_position(position: Any, label: str, result: ValidationResult) -> None:
    if not isinstance(position, list) or len(position) < 2:
        result.errors.append(f"{label} is not a valid GeoJSON position")
        return
    lng, lat = position[0], position[1]
    if not _is_number(lng) or not _is_number(lat):
        result.errors.append(f"{label} must start with numeric longitude/latitude")
        return
    if not math.isfinite(lng) or not math.isfinite(lat):
        result.errors.append(f"{label} contains a non-finite coordinate")
    elif not (REGION_LNG[0] <= lng <= REGION_LNG[1] and REGION_LAT[0] <= lat <= REGION_LAT[1]):
        result.errors.append(f"{label} is outside the DC metro region: {[lng, lat]!r}")


def _validate_ring(ring: Any, label: str, result: ValidationResult) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        result.errors.append(f"{label} must have at least four positions")
        return
    if ring[0] != ring[-1]:
        result.errors.append(f"{label} is not closed")
    for position_index, position in enumerate(ring):
        _validate_position(position, f"{label}[{position_index}]", result)


def _validate_geometry(geometry: Any, label: str, result: ValidationResult) -> None:
    if not isinstance(geometry, dict):
        result.errors.append(f"{label} must be an object")
        return
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        if not isinstance(coordinates, list) or not coordinates:
            result.errors.append(f"{label}.coordinates must contain polygon rings")
            return
        for ring_index, ring in enumerate(coordinates):
            _validate_ring(ring, f"{label}.coordinates[{ring_index}]", result)
    elif geometry_type == "MultiPolygon":
        if not isinstance(coordinates, list) or not coordinates:
            result.errors.append(f"{label}.coordinates must contain polygons")
            return
        for polygon_index, polygon in enumerate(coordinates):
            if not isinstance(polygon, list) or not polygon:
                result.errors.append(
                    f"{label}.coordinates[{polygon_index}] must contain rings"
                )
                continue
            for ring_index, ring in enumerate(polygon):
                _validate_ring(
                    ring,
                    f"{label}.coordinates[{polygon_index}][{ring_index}]",
                    result,
                )
    else:
        result.errors.append(f"{label}.type must be Polygon or MultiPolygon, got {geometry_type!r}")


def _validate_geojson(
    path: Path, name_field: str, result: ValidationResult
) -> list[str]:
    data = _load_json(path, result)
    if data is None:
        return []
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        result.errors.append(f"{path} must be a GeoJSON FeatureCollection")
        return []
    features = data.get("features")
    if not isinstance(features, list) or not features:
        result.errors.append(f"{path} must contain at least one feature")
        return []

    names: list[str] = []
    for index, feature in enumerate(features):
        label = f"{path.name}.features[{index}]"
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            result.errors.append(f"{label} must be a GeoJSON Feature")
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            result.errors.append(f"{label}.properties must be an object")
        else:
            name = properties.get(name_field)
            if not isinstance(name, str) or not name.strip():
                result.errors.append(f"{label} lacks non-blank name field {name_field!r}")
            else:
                names.append(name)
        _validate_geometry(feature.get("geometry"), f"{label}.geometry", result)

    for name, count in Counter(names).items():
        if count > 1:
            result.errors.append(f"{path.name} has duplicate feature name {name!r}")
    return names


def _validate_crosswalk(
    crosswalk_data: Any,
    manifest: list[dict[str, Any]],
    features_by_path: dict[str, list[str]],
    schools_by_id: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> tuple[int, int, set[str]]:
    if not isinstance(crosswalk_data, list):
        result.errors.append("data/boundary-crosswalk.json must contain a JSON array")
        return 0, 0, set()

    files: dict[str, dict[str, Any]] = {}
    for index, file_entry in enumerate(crosswalk_data):
        label = f"boundary-crosswalk[{index}]"
        if not isinstance(file_entry, dict):
            result.errors.append(f"{label} must be an object")
            continue
        path = file_entry.get("path")
        mappings = file_entry.get("mappings")
        if not isinstance(path, str):
            result.errors.append(f"{label}.path must be a string")
            continue
        if path in files:
            result.errors.append(f"Duplicate crosswalk path: {path!r}")
        else:
            files[path] = file_entry
        if not isinstance(mappings, list):
            result.errors.append(f"{label}.mappings must be an array")

    manifest_by_path = {item["path"]: item for item in manifest if isinstance(item.get("path"), str)}
    if set(files) != set(manifest_by_path):
        missing = sorted(set(manifest_by_path) - set(files))
        extra = sorted(set(files) - set(manifest_by_path))
        if missing:
            result.errors.append(f"Crosswalk is missing manifest files: {missing}")
        if extra:
            result.errors.append(f"Crosswalk contains files absent from manifest: {extra}")

    matched = 0
    unmatched = 0
    matched_school_ids: set[str] = set()
    for path, manifest_item in manifest_by_path.items():
        file_entry = files.get(path)
        if not file_entry or not isinstance(file_entry.get("mappings"), list):
            continue
        mappings = file_entry["mappings"]
        expected_names = features_by_path.get(path, [])
        mapped_names: list[str] = []
        for index, mapping in enumerate(mappings):
            label = f"crosswalk[{path}].mappings[{index}]"
            if not isinstance(mapping, dict):
                result.errors.append(f"{label} must be an object")
                continue
            feature_name = mapping.get("feature_name")
            status = mapping.get("status")
            school_id = mapping.get("school_id")
            if not isinstance(feature_name, str) or not feature_name.strip():
                result.errors.append(f"{label}.feature_name must be non-blank")
            else:
                mapped_names.append(feature_name)
            if status == "matched":
                matched += 1
                if not isinstance(school_id, str):
                    result.errors.append(f"{label}.school_id must be a string when matched")
                    continue
                school = schools_by_id.get(school_id)
                if school is None:
                    result.errors.append(f"{label} references unknown school ID {school_id!r}")
                    continue
                if school.get("jurisdiction") != manifest_item.get("jurisdiction"):
                    result.errors.append(
                        f"{label} crosses jurisdictions: {school.get('jurisdiction')!r} != "
                        f"{manifest_item.get('jurisdiction')!r}"
                    )
                if school_id in matched_school_ids:
                    result.errors.append(f"School ID is matched more than once: {school_id!r}")
                matched_school_ids.add(school_id)
            elif status == "unmatched":
                unmatched += 1
                if school_id is not None:
                    result.errors.append(f"{label}.school_id must be null when unmatched")
                reason = mapping.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    result.errors.append(f"{label}.reason is required when unmatched")
            else:
                result.errors.append(f"{label}.status must be 'matched' or 'unmatched'")

        if Counter(mapped_names) != Counter(expected_names):
            missing = sorted((Counter(expected_names) - Counter(mapped_names)).elements())
            extra = sorted((Counter(mapped_names) - Counter(expected_names)).elements())
            if missing:
                result.errors.append(f"Crosswalk {path!r} is missing features: {missing}")
            if extra:
                result.errors.append(f"Crosswalk {path!r} has unknown/duplicate features: {extra}")

    return matched, unmatched, matched_school_ids


def _validate_source_snapshot(root: Path, result: ValidationResult) -> int:
    """Ensure published boundary bytes match the recorded refresh evidence."""

    config = _load_json(root / "config" / "sources.json", result)
    snapshot = _load_json(root / "data" / "source-snapshot.json", result)
    if not isinstance(config, dict) or not isinstance(config.get("sources"), list):
        result.errors.append("config/sources.json must contain a sources array")
        return 0
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("sources"), list):
        result.errors.append("data/source-snapshot.json must contain a sources array")
        return 0

    configured = {
        item.get("id"): item
        for item in config["sources"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    recorded = {
        item.get("id"): item
        for item in snapshot["sources"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if set(configured) != set(recorded):
        result.errors.append(
            "Source snapshot IDs do not match config: "
            f"missing={sorted(set(configured) - set(recorded))}, "
            f"extra={sorted(set(recorded) - set(configured))}"
        )

    verified = 0
    for source_id, source in configured.items():
        record = recorded.get(source_id)
        if record is None:
            continue
        output = source.get("output")
        if not isinstance(output, str):
            result.errors.append(f"Source {source_id!r} lacks a valid output path")
            continue
        path = (root / output).resolve()
        if root not in path.parents or not path.is_file():
            result.errors.append(f"Source {source_id!r} output is missing or unsafe: {output!r}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record.get("sha256"):
            result.errors.append(
                f"Source {source_id!r} hash differs from data/source-snapshot.json; "
                "run scripts/refresh_boundaries.py --apply or document the snapshot change"
            )
        if record.get("features") != source.get("expected_features"):
            result.errors.append(
                f"Source {source_id!r} recorded {record.get('features')!r} features; "
                f"expected {source.get('expected_features')!r}"
            )
        if record.get("query_url") != source.get("query_url"):
            result.errors.append(f"Source {source_id!r} query_url differs from its snapshot")
        if record.get("where", "1=1") != source.get("where", "1=1"):
            result.errors.append(f"Source {source_id!r} where filter differs from its snapshot")
        verified += 1
    return verified


def _validate_rating_evidence(
    root: Path,
    schools_by_id: dict[str, dict[str, Any]],
    result: ValidationResult,
) -> dict[str, int]:
    """Validate rating-source policy and cross-reference materialized evidence."""

    config = _load_json(root / "config" / "rating-sources.json", result)
    evidence = _load_json(root / "data" / "rating-evidence.json", result)
    if not isinstance(config, dict) or not isinstance(config.get("sources"), list):
        result.errors.append("config/rating-sources.json must contain a sources array")
        return {}
    if not isinstance(evidence, dict) or not isinstance(evidence.get("runs"), list):
        result.errors.append("data/rating-evidence.json must contain a runs array")
        return {}

    sources = {
        item.get("name"): item
        for item in config["sources"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not sources:
        result.errors.append("No rating sources are configured")

    attempts: dict[str, dict[str, Any]] = {}
    for run_index, run in enumerate(evidence["runs"]):
        label = f"rating-evidence.runs[{run_index}]"
        if not isinstance(run, dict) or not isinstance(run.get("attempts"), list):
            result.errors.append(f"{label}.attempts must be an array")
            continue
        rows = run["attempts"]
        provider_ids: set[str] = set()
        if run.get("method") == "user_supplied_manual_verification":
            workbook = run.get("source_workbook")
            if not isinstance(workbook, dict):
                result.errors.append(f"{label}.source_workbook must be an object")
            else:
                repository_path = workbook.get("repository_path")
                expected_hash = workbook.get("sha256")
                filename = workbook.get("filename")
                if not isinstance(repository_path, str) or not repository_path:
                    result.errors.append(f"{label}.source_workbook.repository_path is required")
                elif Path(repository_path).is_absolute():
                    result.errors.append(f"{label}.source_workbook.repository_path must be relative")
                else:
                    workbook_path = (root / repository_path).resolve()
                    try:
                        workbook_path.relative_to(root.resolve())
                    except ValueError:
                        result.errors.append(f"{label}.source_workbook.repository_path escapes the repository")
                    else:
                        if not workbook_path.is_file():
                            result.errors.append(f"{label}.source_workbook file does not exist")
                        elif filename != workbook_path.name:
                            result.errors.append(f"{label}.source_workbook filename differs from repository_path")
                        elif not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                            result.errors.append(f"{label}.source_workbook.sha256 is invalid")
                        elif hashlib.sha256(workbook_path.read_bytes()).hexdigest() != expected_hash:
                            result.errors.append(f"{label}.source_workbook SHA-256 does not match the preserved file")
        if run.get("coverage") != len(schools_by_id) or len(rows) != len(schools_by_id):
            result.errors.append(f"{label} must contain a complete {len(schools_by_id)}-school run")
        run_school_ids: list[str] = []
        for attempt_index, attempt in enumerate(rows):
            item_label = f"{label}.attempts[{attempt_index}]"
            if not isinstance(attempt, dict):
                result.errors.append(f"{item_label} must be an object")
                continue
            evidence_id = attempt.get("evidence_id")
            school_id = attempt.get("school_id")
            if not isinstance(evidence_id, str) or not evidence_id:
                result.errors.append(f"{item_label}.evidence_id must be non-blank")
            elif evidence_id in attempts:
                result.errors.append(f"Duplicate rating evidence ID: {evidence_id!r}")
            else:
                attempts[evidence_id] = attempt
            if school_id not in schools_by_id:
                result.errors.append(f"{item_label} references unknown school ID {school_id!r}")
            else:
                run_school_ids.append(school_id)
            provider_id = attempt.get("rating_source_school_id")
            if not isinstance(provider_id, str) or not provider_id:
                result.errors.append(f"{item_label} requires rating_source_school_id")
            elif provider_id in provider_ids:
                result.errors.append(f"Duplicate provider school ID in evidence: {provider_id!r}")
            else:
                provider_ids.add(provider_id)
        if len(set(run_school_ids)) != len(schools_by_id):
            result.errors.append(f"{label} does not cover each school exactly once")

    status_counts = Counter()
    rating_urls: set[str] = set()
    for school_id, school in schools_by_id.items():
        status = school.get("rating_status")
        status_counts[status] += 1
        source = sources.get(school.get("rating_source"))
        if source is None:
            result.errors.append(f"School {school_id!r} uses an unconfigured rating source")
            continue
        if status in {"verified", "not_available"}:
            source_url = school.get("rating_source_url")
            if isinstance(source_url, str):
                if source_url in rating_urls:
                    result.errors.append(f"Duplicate rating source URL: {source_url!r}")
                else:
                    rating_urls.add(source_url)
                host = urlparse(source_url).hostname
                if host not in source.get("allowed_hosts", []):
                    result.errors.append(f"School {school_id!r} has a disallowed rating URL host")
            if school.get("rating_method") not in source.get("allowed_methods", []):
                result.errors.append(f"School {school_id!r} uses a disallowed rating method")
            attempt = attempts.get(school.get("rating_evidence_id"))
            if attempt is None:
                result.errors.append(f"School {school_id!r} has no matching rating evidence")
            else:
                pairs = {
                    "school_id": school_id,
                    "rating": school.get("rating"),
                    "rating_status": status,
                    "rating_source": school.get("rating_source"),
                    "rating_source_url": source_url,
                    "rating_source_school_id": school.get("rating_source_school_id"),
                    "rating_as_of": school.get("rating_as_of"),
                    "rating_checked_at": school.get("rating_checked_at"),
                    "rating_method": school.get("rating_method"),
                }
                for key, value in pairs.items():
                    if attempt.get(key) != value:
                        result.errors.append(
                            f"School {school_id!r} differs from rating evidence for {key}"
                        )
    return {str(key): value for key, value in status_counts.items()}


def validate_project(root: Path | str = PROJECT_ROOT) -> ValidationResult:
    """Validate all materialized data files below *root*."""

    project_root = Path(root).resolve()
    result = ValidationResult()
    schools_data = _load_json(project_root / "data" / "schools.json", result)
    manifest_data = _load_json(project_root / "data" / "boundary-manifest.json", result)
    crosswalk_data = _load_json(project_root / "data" / "boundary-crosswalk.json", result)
    if schools_data is None or manifest_data is None or crosswalk_data is None:
        return result

    schools, schools_by_id = _validate_school_schema(schools_data, result)
    manifest = _validate_manifest_schema(manifest_data, project_root, result)

    features_by_path: dict[str, list[str]] = {}
    for item in manifest:
        path = item.get("path")
        name_field = item.get("name_field")
        if not isinstance(path, str) or not isinstance(name_field, str):
            continue
        features_by_path[path] = _validate_geojson(project_root / path, name_field, result)

    matched, unmatched, matched_school_ids = _validate_crosswalk(
        crosswalk_data,
        manifest,
        features_by_path,
        schools_by_id,
        result,
    )
    source_snapshots = _validate_source_snapshot(project_root, result)
    rating_counts = _validate_rating_evidence(project_root, schools_by_id, result)
    total_features = sum(len(names) for names in features_by_path.values())
    result.summary = {
        "schools": len(schools),
        "boundary_files": len(manifest),
        "boundary_features": total_features,
        "matched_features": matched,
        "unmatched_features": unmatched,
        "schools_with_boundary": len(matched_school_ids),
        "schools_without_boundary": len(schools_by_id) - len(matched_school_ids),
        "source_snapshots": source_snapshots,
        "ratings_verified": rating_counts.get("verified", 0),
        "ratings_not_available": rating_counts.get("not_available", 0),
        "ratings_legacy_unverified": rating_counts.get("legacy_unverified", 0),
    }
    return result


def _print_report(result: ValidationResult) -> None:
    state = "PASS" if result.ok else "FAIL"
    print(f"Data validation: {state}")
    for key, value in result.summary.items():
        print(f"  {key.replace('_', ' ')}: {value}")
    if result.warnings:
        print(f"Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  - {warning}")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root (defaults to the parent of this script directory)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = validate_project(args.root)
    _print_report(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
