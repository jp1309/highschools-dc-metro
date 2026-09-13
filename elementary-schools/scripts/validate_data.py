"""Validate elementary-school ratings, locations, and boundary semantics."""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

try:
    from scripts.import_manual_ratings import (
        CHECKED_AT,
        EXPECTED_RECORDS,
        JURISDICTION_SLUGS,
        RUN_ID,
        SOURCE_FILENAME,
        SOURCE_SHA256,
        sha256_file,
        workbook_records,
    )
    from scripts.validate_boundaries import validate_boundaries
except ModuleNotFoundError:
    from import_manual_ratings import (  # type: ignore[no-redef]
        CHECKED_AT,
        EXPECTED_RECORDS,
        JURISDICTION_SLUGS,
        RUN_ID,
        SOURCE_FILENAME,
        SOURCE_SHA256,
        sha256_file,
        workbook_records,
    )
    from validate_boundaries import validate_boundaries  # type: ignore[no-redef]


SCHOOL_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*:[a-z0-9]+(?:_[a-z0-9]+)*$")
PROVIDER_ID_PATTERN = re.compile(r"^(va|md|dc)-\d+$")
LOCATION_STATUSES = {"pending_official_source", "verified_official", "verified_official_historical"}


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load(path: Path, result: ValidationResult):
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        result.errors.append(f"{path}: {error}")
        return None


def _duplicates(values) -> list[object]:
    seen: set[object] = set()
    repeated: set[object] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated, key=str)


def _https(value: object) -> bool:
    parsed = urlparse(value if isinstance(value, str) else "")
    return parsed.scheme == "https" and bool(parsed.hostname)


def _validate_schools(root: Path, result: ValidationResult) -> dict[str, dict[str, object]]:
    payload = _load(root / "data" / "schools.json", result)
    if not isinstance(payload, list):
        result.errors.append("data/schools.json must be an array")
        return {}
    result.summary["schools"] = len(payload)
    if len(payload) != EXPECTED_RECORDS:
        result.errors.append(f"Expected {EXPECTED_RECORDS} schools, found {len(payload)}")

    snapshot = root / "outputs" / RUN_ID / SOURCE_FILENAME
    expected = workbook_records(snapshot) if snapshot.is_file() else []
    if not snapshot.is_file():
        result.errors.append(f"Missing immutable rating workbook: {snapshot}")
    elif sha256_file(snapshot) != SOURCE_SHA256:
        result.errors.append("Immutable rating workbook SHA-256 mismatch")
    expected_by_row = {item["source_row_number"]: item for item in expected}

    required = {
        "id", "source_row_number", "source_name", "name", "name_normalization_note",
        "source_jurisdiction", "jurisdiction", "jurisdiction_resolution_note", "city",
        "school_type", "grades_label", "grades_served", "grade_min", "grade_max",
        "contains_elementary", "attendance_model", "attendance_model_note", "district",
        "operational_status", "operational_status_source_url", "rating", "rating_status",
        "rating_source", "rating_source_url", "rating_source_school_id", "rating_as_of",
        "rating_checked_at", "rating_method", "rating_evidence_id", "provenance_note",
    }
    comparable = required - {"attendance_model", "attendance_model_note"}
    valid: dict[str, dict[str, object]] = {}
    for index, school in enumerate(payload, start=1):
        label = f"schools[{index}]"
        if not isinstance(school, dict):
            result.errors.append(f"{label} must be an object")
            continue
        missing = sorted(required - school.keys())
        if missing:
            result.errors.append(f"{label} missing fields: {missing}")
            continue
        school_id = school["id"]
        if not isinstance(school_id, str) or not SCHOOL_ID_PATTERN.fullmatch(school_id):
            result.errors.append(f"{label}.id is invalid: {school_id!r}")
            continue
        if school_id in valid:
            result.errors.append(f"Duplicate school id: {school_id}")
        valid[school_id] = school
        if school["source_row_number"] != index + 5:
            result.errors.append(f"{label}.source_row_number is not contiguous")
        source_record = expected_by_row.get(school["source_row_number"])
        if not source_record:
            result.errors.append(f"{label} has no workbook source row")
        else:
            for key in comparable:
                if school.get(key) != source_record.get(key):
                    result.errors.append(f"{label}.{key} differs from the immutable workbook materialization")
        jurisdiction = school["jurisdiction"]
        if jurisdiction not in JURISDICTION_SLUGS:
            result.errors.append(f"{label}.jurisdiction is unsupported")
        elif not school_id.startswith(JURISDICTION_SLUGS[jurisdiction] + ":"):
            result.errors.append(f"{label}.id prefix differs from canonical jurisdiction")
        if school["source_jurisdiction"] not in JURISDICTION_SLUGS:
            result.errors.append(f"{label}.source_jurisdiction is unsupported")
        for key in ("name", "jurisdiction", "city"):
            value = school[key]
            if not isinstance(value, str) or not value.strip() or html.unescape(value) != value:
                result.errors.append(f"{label}.{key} must be canonical non-empty text without HTML entities")
        if school["source_name"] != school["name"]:
            if not school["name_normalization_note"]:
                result.errors.append(f"{label} normalized name lacks an audit note")
        elif school["name_normalization_note"] is not None:
            result.errors.append(f"{label} has an unnecessary name normalization note")
        if school["source_jurisdiction"] != school["jurisdiction"]:
            if not school["jurisdiction_resolution_note"]:
                result.errors.append(f"{label} resolved jurisdiction lacks an audit note")
        elif school["jurisdiction_resolution_note"] is not None:
            result.errors.append(f"{label} has an unnecessary jurisdiction resolution note")
        if school["school_type"] not in {"public", "charter"}:
            result.errors.append(f"{label}.school_type is invalid")
        grades = school["grades_served"]
        if not isinstance(grades, list) or not grades or grades != sorted(set(grades)):
            result.errors.append(f"{label}.grades_served is invalid")
        elif school["grade_min"] != grades[0] or school["grade_max"] != grades[-1]:
            result.errors.append(f"{label} grade bounds differ from grades_served")
        if school["contains_elementary"] is not True or not set(grades or []).intersection(range(0, 6)):
            result.errors.append(f"{label} does not serve an elementary grade")
        if school["attendance_model"] not in {
            "zoned", "charter_no_zone", "choice_no_zone", "municipal_context", "unknown"
        }:
            result.errors.append(f"{label}.attendance_model is invalid")
        if school["school_type"] == "charter" and school["attendance_model"] != "charter_no_zone":
            result.errors.append(f"{label} charter must use charter_no_zone")
        if not isinstance(school["attendance_model_note"], str) or not school["attendance_model_note"].strip():
            result.errors.append(f"{label}.attendance_model_note is required")
        rating = school["rating"]
        if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 10:
            result.errors.append(f"{label}.rating must be an integer from 1 to 10")
        if school["rating_status"] != "verified_user_supplied" or school["rating_source"] != "GreatSchools":
            result.errors.append(f"{label} rating provenance is invalid")
        if not _https(school["rating_source_url"]) or urlparse(school["rating_source_url"]).hostname != "www.greatschools.org":
            result.errors.append(f"{label}.rating_source_url is invalid")
        if not isinstance(school["rating_source_school_id"], str) or not PROVIDER_ID_PATTERN.fullmatch(school["rating_source_school_id"]):
            result.errors.append(f"{label}.rating_source_school_id is invalid")
        if school["rating_as_of"] is not None or school["rating_checked_at"] != CHECKED_AT:
            result.errors.append(f"{label} rating date provenance is invalid")
        if school["rating_method"] != "user_supplied_workbook" or school["rating_evidence_id"] != f"{RUN_ID}:{school_id}":
            result.errors.append(f"{label} rating method/evidence ID is invalid")

    for key in ("rating_source_url", "rating_source_school_id", "rating_evidence_id"):
        repeated = _duplicates(school.get(key) for school in payload if isinstance(school, dict))
        if repeated:
            result.errors.append(f"Duplicate {key} values: {repeated}")
    return valid


def _validate_rating_evidence(root: Path, schools: dict[str, dict[str, object]], result: ValidationResult) -> None:
    evidence = _load(root / "data" / "rating-evidence.json", result)
    if not isinstance(evidence, dict) or not isinstance(evidence.get("runs"), list):
        result.errors.append("data/rating-evidence.json must contain runs")
        return
    runs = [run for run in evidence["runs"] if isinstance(run, dict) and run.get("run_id") == RUN_ID]
    if len(runs) != 1:
        result.errors.append(f"Expected exactly one rating evidence run {RUN_ID}")
        return
    run = runs[0]
    source = run.get("source_workbook")
    attempts = run.get("attempts")
    if not isinstance(source, dict) or source.get("sha256") != SOURCE_SHA256:
        result.errors.append("Rating evidence workbook identity is invalid")
    if not isinstance(attempts, list) or len(attempts) != len(schools) or run.get("coverage") != len(schools):
        result.errors.append("Rating evidence coverage differs from schools")
        return
    by_id = {attempt.get("school_id"): attempt for attempt in attempts if isinstance(attempt, dict)}
    if len(by_id) != len(attempts) or set(by_id) != set(schools):
        result.errors.append("Rating evidence must cover every school exactly once")
    fields = (
        "source_row_number", "source_name", "name", "name_normalization_note",
        "source_jurisdiction", "jurisdiction", "jurisdiction_resolution_note", "rating",
        "rating_status", "rating_source", "rating_source_url", "rating_source_school_id",
        "rating_as_of", "rating_checked_at", "rating_method",
    )
    for school_id, attempt in by_id.items():
        school = schools.get(school_id)
        if not school:
            continue
        if attempt.get("evidence_id") != school["rating_evidence_id"]:
            result.errors.append(f"Rating evidence ID mismatch for {school_id}")
        for key in fields:
            if attempt.get(key) != school.get(key):
                result.errors.append(f"Rating evidence mismatch for {school_id}.{key}")
    result.summary["rating_evidence"] = len(by_id)


def _validate_rating_config(root: Path, result: ValidationResult) -> None:
    config = _load(root / "config" / "rating-sources.json", result)
    if not isinstance(config, dict) or config.get("score_input_policy") != "only_user_supplied_workbook":
        result.errors.append("Rating config must enforce the user workbook as the only score source")
        return
    sources = config.get("sources")
    if not isinstance(sources, list) or len(sources) != 1:
        result.errors.append("Rating config must contain exactly one source")
        return
    source = sources[0]
    expected = {
        "method": "user_supplied_workbook", "rating_min": 1, "rating_max": 10,
        "workbook_filename": SOURCE_FILENAME, "workbook_sha256": SOURCE_SHA256,
        "repository_path": f"outputs/{RUN_ID}/{SOURCE_FILENAME}", "sheet": "Elementary Schools",
        "data_range": "A6:I557", "checked_at": CHECKED_AT, "rating_as_of": None,
        "automated_provider_access": False,
    }
    for key, value in expected.items():
        if source.get(key) != value:
            result.errors.append(f"Rating config field {key} is inconsistent")


def _approved_location_sources(root: Path, result: ValidationResult) -> set[str]:
    path = root / "config" / "location-sources.json"
    if not path.is_file():
        return set()
    config = _load(path, result)
    if not isinstance(config, dict) or not isinstance(config.get("sources"), list):
        result.errors.append("Location source config must contain sources")
        return set()
    approved: set[str] = set()
    for source in config["sources"]:
        if not isinstance(source, dict):
            result.errors.append("Location source entries must be objects")
            continue
        source_id = source.get("id")
        if source.get("official") is not True or source.get("status") != "approved":
            result.errors.append(f"Location source {source_id!r} is not approved official")
        elif isinstance(source_id, str):
            approved.add(source_id)
        if not _https(source.get("source_url")) or urlparse(source["source_url"]).hostname not in source.get("allowed_hosts", []):
            result.errors.append(f"Location source {source_id!r} has an invalid URL/host contract")
    if len(approved) != len(config["sources"]):
        result.errors.append("Location source IDs are missing or duplicated")
    return approved


def _validate_locations(root: Path, schools: dict[str, dict[str, object]], result: ValidationResult) -> None:
    path = root / "data" / "school-locations.json"
    if not path.is_file():
        return
    registry = _load(path, result)
    if not isinstance(registry, dict) or not isinstance(registry.get("locations"), list):
        result.errors.append("Location registry must contain locations")
        return
    approved = _approved_location_sources(root, result)
    locations = registry["locations"]
    ids: list[object] = []
    verified_ids: set[str] = set()
    pending = historical = 0
    for index, location in enumerate(locations, start=1):
        label = f"locations[{index}]"
        if not isinstance(location, dict):
            result.errors.append(f"{label} must be an object")
            continue
        school_id = location.get("school_id")
        ids.append(school_id)
        if school_id not in schools:
            result.errors.append(f"{label}.school_id is unknown: {school_id!r}")
        status = location.get("location_status")
        if status not in LOCATION_STATUSES:
            result.errors.append(f"{label}.location_status is invalid")
            continue
        if status == "pending_official_source":
            pending += 1
            for key in ("address", "lat", "lng", "source_name", "source_url", "coordinate_source_url", "source_dataset_id", "source_record_id", "retrieved_at"):
                if location.get(key) is not None:
                    result.errors.append(f"{label}.{key} must be null while pending")
        else:
            verified_ids.add(school_id)
            historical += status == "verified_official_historical"
            if not isinstance(location.get("address"), str) or not location["address"].strip():
                result.errors.append(f"{label}.address is required")
            lat, lng = location.get("lat"), location.get("lng")
            if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not 37.5 <= lat <= 39.6:
                result.errors.append(f"{label}.lat is outside the DC region")
            if not isinstance(lng, (int, float)) or isinstance(lng, bool) or not -78.2 <= lng <= -76.2:
                result.errors.append(f"{label}.lng is outside the DC region")
            if location.get("source_dataset_id") not in approved or not _https(location.get("source_url")) or not _https(location.get("coordinate_source_url")):
                result.errors.append(f"{label} lacks approved official provenance")
            if not location.get("source_record_id") or not location.get("retrieved_at"):
                result.errors.append(f"{label} lacks official record identity")
    if len(locations) != len(schools) or _duplicates(ids) or set(ids) != set(schools):
        result.errors.append("Location registry must contain every school exactly once")
    expected_summary = {
        "schools": len(locations), "verified_official": len(verified_ids),
        "pending_official_source": pending,
    }
    if registry.get("summary") != expected_summary:
        result.errors.append(f"Location summary mismatch: expected {expected_summary}")
    result.summary.update(
        locations_verified_official=len(verified_ids),
        locations_verified_historical=historical,
        locations_pending=pending,
    )

    evidence_path = root / "data" / "location-evidence.json"
    if not evidence_path.is_file():
        return
    evidence = _load(evidence_path, result)
    if not isinstance(evidence, dict) or not isinstance(evidence.get("matches"), list):
        result.errors.append("Location evidence must contain matches")
        return
    matches = evidence["matches"]
    by_id = {match.get("school_id"): match for match in matches if isinstance(match, dict)}
    if len(by_id) != len(matches) or set(by_id) != verified_ids:
        result.errors.append("Location evidence must cover every verified location exactly once")
    locations_by_id = {location.get("school_id"): location for location in locations if isinstance(location, dict)}
    for school_id, match in by_id.items():
        location = locations_by_id.get(school_id, {})
        if match.get("source_dataset_id") not in approved:
            result.errors.append(f"Location evidence for {school_id} uses an unapproved source")
        for key in ("address", "lat", "lng", "source_dataset_id", "source_record_id"):
            if match.get(key) != location.get(key):
                result.errors.append(f"Location evidence mismatch for {school_id}.{key}")
    summary = evidence.get("summary", {})
    if summary.get("schools") != len(schools) or summary.get("verified_official") != len(verified_ids) or summary.get("pending_official_source") != pending:
        result.errors.append("Location evidence summary differs from registry")
    result.summary["location_evidence"] = len(by_id)


def _validate_boundaries_if_present(root: Path, schools: dict[str, dict[str, object]], result: ValidationResult) -> None:
    manifest_path = root / "data" / "boundary-manifest.json"
    crosswalk_path = root / "data" / "boundary-crosswalk.json"
    if not manifest_path.is_file() and not crosswalk_path.is_file():
        return
    if not manifest_path.is_file() or not crosswalk_path.is_file():
        result.errors.append("Boundary manifest and crosswalk must either both exist or both be absent")
        return
    boundary_result = validate_boundaries(root)
    result.errors.extend(f"boundaries: {error}" for error in boundary_result.errors)
    for key, value in boundary_result.summary.items():
        result.summary[f"boundaries_{key}"] = value

    manifest = _load(manifest_path, result)
    crosswalk = _load(crosswalk_path, result)
    types = {entry.get("path"): entry.get("boundary_type") for entry in manifest.get("entries", [])}
    linked: dict[str, set[str]] = {}
    for file_entry in crosswalk.get("files", []):
        path = file_entry.get("path")
        for mapping in file_entry.get("mappings", {}).values():
            if mapping.get("status") not in {"matched", "matched_alias", "matched_context"}:
                continue
            ids = mapping.get("school_ids")
            if ids is None:
                ids = [mapping.get("school_id")] if mapping.get("school_id") else []
            for school_id in ids:
                school = schools.get(school_id)
                if school and school["school_type"] == "charter":
                    result.errors.append(f"Charter {school_id} must not receive a boundary")
                linked.setdefault(school_id, set()).add(types.get(path, ""))
    for school_id, school in schools.items():
        expected = (
            "charter_no_zone" if school["school_type"] == "charter"
            else "zoned" if "attendance_boundary" in linked.get(school_id, set())
            else "municipal_context" if "municipal_boundary" in linked.get(school_id, set())
            else "unknown"
        )
        if school["attendance_model"] != expected:
            result.errors.append(
                f"Attendance model mismatch for {school_id}: expected {expected}, found {school['attendance_model']}"
            )


def validate_project(project_root: Path) -> ValidationResult:
    result = ValidationResult()
    schools = _validate_schools(project_root, result)
    _validate_rating_evidence(project_root, schools, result)
    _validate_rating_config(project_root, result)
    _validate_locations(project_root, schools, result)
    _validate_boundaries_if_present(project_root, schools, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = validate_project(args.project_root.resolve())
    if result.ok:
        summary = ", ".join(f"{key}={value}" for key, value in sorted(result.summary.items()))
        print(f"PASS: elementary-school data validation succeeded ({summary}).")
        return 0
    print(f"FAIL: {len(result.errors)} validation error(s):")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
