"""Validate the independently materialized middle-school data products."""

from __future__ import annotations

import argparse
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
    )
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    from import_manual_ratings import (  # type: ignore[no-redef]
        CHECKED_AT,
        EXPECTED_RECORDS,
        JURISDICTION_SLUGS,
        RUN_ID,
        SOURCE_FILENAME,
        SOURCE_SHA256,
        sha256_file,
    )


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


def _load_json(path: Path, result: ValidationResult):
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


def _validate_schools(project_root: Path, result: ValidationResult) -> dict[str, dict[str, object]]:
    schools = _load_json(project_root / "data" / "schools.json", result)
    if not isinstance(schools, list):
        result.errors.append("data/schools.json must be an array")
        return {}
    result.summary["schools"] = len(schools)
    if len(schools) != EXPECTED_RECORDS:
        result.errors.append(f"Expected {EXPECTED_RECORDS} schools, found {len(schools)}")

    required = {
        "id",
        "source_row_number",
        "name",
        "jurisdiction",
        "city",
        "school_type",
        "grades_label",
        "grades_served",
        "grade_min",
        "grade_max",
        "contains_middle",
        "attendance_model",
        "attendance_model_note",
        "district",
        "operational_status",
        "operational_status_source_url",
        "rating",
        "rating_status",
        "rating_source",
        "rating_source_url",
        "rating_source_school_id",
        "rating_as_of",
        "rating_checked_at",
        "rating_method",
        "rating_evidence_id",
        "provenance_note",
    }
    for index, school in enumerate(schools, start=1):
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
            result.errors.append(f"{label}.id is not a stable composite slug: {school_id!r}")
        jurisdiction = school["jurisdiction"]
        if jurisdiction not in JURISDICTION_SLUGS:
            result.errors.append(f"{label}.jurisdiction is unsupported: {jurisdiction!r}")
        elif isinstance(school_id, str) and not school_id.startswith(JURISDICTION_SLUGS[jurisdiction] + ":"):
            result.errors.append(f"{label}.id jurisdiction prefix does not match")
        if school["source_row_number"] != index + 5:
            result.errors.append(f"{label}.source_row_number is not contiguous")
        if school["school_type"] not in {"public", "charter"}:
            result.errors.append(f"{label}.school_type is invalid")
        for field_name in ("name", "city", "grades_label", "provenance_note"):
            if not isinstance(school[field_name], str) or not school[field_name].strip():
                result.errors.append(f"{label}.{field_name} must be non-empty text")
        if school["district"] is not None and (not isinstance(school["district"], str) or not school["district"].strip()):
            result.errors.append(f"{label}.district must be text or null")
        grade_min = school["grade_min"]
        grade_max = school["grade_max"]
        if not isinstance(grade_min, int) or isinstance(grade_min, bool) or not -1 <= grade_min <= 12:
            result.errors.append(f"{label}.grade_min is invalid")
        if not isinstance(grade_max, int) or isinstance(grade_max, bool) or not 1 <= grade_max <= 12:
            result.errors.append(f"{label}.grade_max is invalid")
        if isinstance(grade_min, int) and isinstance(grade_max, int) and grade_min > grade_max:
            result.errors.append(f"{label} has descending grade bounds")
        grades_served = school["grades_served"]
        if (
            not isinstance(grades_served, list)
            or not grades_served
            or any(not isinstance(grade, int) or isinstance(grade, bool) for grade in grades_served)
            or grades_served != sorted(set(grades_served))
            or grades_served[0] != grade_min
            or grades_served[-1] != grade_max
        ):
            result.errors.append(f"{label}.grades_served is inconsistent")
        if school["contains_middle"] is not True or not set(grades_served).intersection({6, 7, 8}):
            result.errors.append(f"{label} must include grade 6, 7, or 8")
        if school["attendance_model"] not in {"zoned", "charter_no_zone", "choice_no_zone", "municipal_context", "unknown"}:
            result.errors.append(f"{label}.attendance_model is invalid")
        if school["school_type"] == "charter" and school["attendance_model"] != "charter_no_zone":
            result.errors.append(f"{label} charter must use charter_no_zone")
        if school["school_type"] == "public" and school["attendance_model"] == "charter_no_zone":
            result.errors.append(f"{label} public school cannot use charter_no_zone")
        if not isinstance(school["attendance_model_note"], str) or not school["attendance_model_note"].strip():
            result.errors.append(f"{label}.attendance_model_note is required")
        expected_operational = (
            "closed_historical"
            if school_id == "prince_georges_county_md:turning_point_academy_public_charter"
            else "not_verified"
        )
        if school["operational_status"] != expected_operational:
            result.errors.append(f"{label}.operational_status is inconsistent")
        if expected_operational == "closed_historical":
            status_url = school["operational_status_source_url"]
            if not isinstance(status_url, str) or not status_url.startswith("https://www.pgcps.org/"):
                result.errors.append(f"{label} lacks official closure evidence")
        elif school["operational_status_source_url"] is not None:
            result.errors.append(f"{label}.operational_status_source_url must be null")
        rating = school["rating"]
        if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 10:
            result.errors.append(f"{label}.rating must be an integer from 1 to 10")
        if school["rating_status"] != "verified_user_supplied":
            result.errors.append(f"{label}.rating_status is invalid")
        if school["rating_source"] != "GreatSchools":
            result.errors.append(f"{label}.rating_source is invalid")
        parsed = urlparse(school["rating_source_url"] if isinstance(school["rating_source_url"], str) else "")
        if parsed.scheme != "https" or parsed.hostname != "www.greatschools.org":
            result.errors.append(f"{label}.rating_source_url is invalid")
        if not isinstance(school["rating_source_school_id"], str) or not PROVIDER_ID_PATTERN.fullmatch(school["rating_source_school_id"]):
            result.errors.append(f"{label}.rating_source_school_id is invalid")
        if school["rating_as_of"] is not None:
            result.errors.append(f"{label}.rating_as_of must be null because the workbook gives no rating period")
        if school["rating_checked_at"] != CHECKED_AT or school["rating_method"] != "user_supplied_workbook":
            result.errors.append(f"{label} has inconsistent rating provenance")
        expected_evidence_id = f"{RUN_ID}:{school_id}"
        if school["rating_evidence_id"] != expected_evidence_id:
            result.errors.append(f"{label}.rating_evidence_id is inconsistent")

    for field_name in ("id", "rating_source_url", "rating_source_school_id", "rating_evidence_id"):
        duplicates = _duplicates(school.get(field_name) for school in schools if isinstance(school, dict))
        if duplicates:
            result.errors.append(f"Duplicate {field_name} values: {duplicates}")
    attendance_counts: dict[str, int] = {}
    for school in schools:
        if isinstance(school, dict) and isinstance(school.get("attendance_model"), str):
            model = school["attendance_model"]
            attendance_counts[model] = attendance_counts.get(model, 0) + 1
    expected_attendance_counts = {"zoned": 121, "municipal_context": 1, "charter_no_zone": 61, "unknown": 9}
    if attendance_counts != expected_attendance_counts:
        result.errors.append(
            f"Attendance model counts mismatch: expected {expected_attendance_counts}, found {attendance_counts}"
        )
    result.summary["attendance_zoned"] = attendance_counts.get("zoned", 0)
    result.summary["attendance_municipal_context"] = attendance_counts.get("municipal_context", 0)
    result.summary["attendance_charter_no_zone"] = attendance_counts.get("charter_no_zone", 0)
    result.summary["attendance_unknown"] = attendance_counts.get("unknown", 0)
    return {school["id"]: school for school in schools if isinstance(school, dict) and isinstance(school.get("id"), str)}


def _validate_evidence(project_root: Path, schools: dict[str, dict[str, object]], result: ValidationResult) -> None:
    evidence = _load_json(project_root / "data" / "rating-evidence.json", result)
    if not isinstance(evidence, dict) or not isinstance(evidence.get("runs"), list):
        result.errors.append("data/rating-evidence.json must contain runs")
        return
    matching_runs = [run for run in evidence["runs"] if isinstance(run, dict) and run.get("run_id") == RUN_ID]
    if len(matching_runs) != 1:
        result.errors.append(f"Expected exactly one evidence run {RUN_ID!r}")
        return
    run = matching_runs[0]
    attempts = run.get("attempts")
    if run.get("coverage") != len(schools) or not isinstance(attempts, list) or len(attempts) != len(schools):
        result.errors.append("Evidence coverage does not match schools")
        return
    source_workbook = run.get("source_workbook")
    if not isinstance(source_workbook, dict):
        result.errors.append("Evidence run lacks source_workbook")
        return
    if source_workbook.get("sha256") != SOURCE_SHA256 or source_workbook.get("filename") != SOURCE_FILENAME:
        result.errors.append("Evidence workbook identity is inconsistent")
    workbook_path = project_root / str(source_workbook.get("repository_path", ""))
    if not workbook_path.is_file():
        result.errors.append(f"Evidence workbook does not exist: {workbook_path}")
    elif sha256_file(workbook_path) != SOURCE_SHA256:
        result.errors.append("Evidence workbook hash mismatch")

    attempts_by_school: dict[str, dict[str, object]] = {}
    for index, attempt in enumerate(attempts, start=1):
        if not isinstance(attempt, dict) or attempt.get("school_id") not in schools:
            result.errors.append(f"attempts[{index}] has unknown school_id")
            continue
        school_id = attempt["school_id"]
        if school_id in attempts_by_school:
            result.errors.append(f"Duplicate evidence for {school_id}")
            continue
        attempts_by_school[school_id] = attempt
        school = schools[school_id]
        for field_name in (
            "rating",
            "rating_status",
            "rating_source",
            "rating_source_url",
            "rating_source_school_id",
            "rating_as_of",
            "rating_checked_at",
            "rating_method",
        ):
            if attempt.get(field_name) != school.get(field_name):
                result.errors.append(f"Evidence mismatch for {school_id}.{field_name}")
        if attempt.get("evidence_id") != school.get("rating_evidence_id"):
            result.errors.append(f"Evidence ID mismatch for {school_id}")
    if set(attempts_by_school) != set(schools):
        result.errors.append("Evidence does not cover every school exactly once")
    result.summary["rating_evidence"] = len(attempts_by_school)


def _validate_locations(project_root: Path, schools: dict[str, dict[str, object]], result: ValidationResult) -> None:
    registry = _load_json(project_root / "data" / "school-locations.json", result)
    if not isinstance(registry, dict) or not isinstance(registry.get("locations"), list):
        result.errors.append("data/school-locations.json must contain locations")
        return
    locations = registry["locations"]
    if len(locations) != len(schools):
        result.errors.append("Location registry must contain one row per school")
    verified = 0
    historical = 0
    pending = 0
    ids: list[object] = []
    for index, location in enumerate(locations, start=1):
        label = f"locations[{index}]"
        if not isinstance(location, dict):
            result.errors.append(f"{label} must be an object")
            continue
        school_id = location.get("school_id")
        ids.append(school_id)
        if school_id not in schools:
            result.errors.append(f"{label}.school_id is unknown")
        status = location.get("location_status")
        if status not in LOCATION_STATUSES:
            result.errors.append(f"{label}.location_status is invalid")
            continue
        if status == "pending_official_source":
            pending += 1
            for field_name in (
                "address",
                "lat",
                "lng",
                "source_name",
                "source_url",
                "coordinate_source_url",
                "source_dataset_id",
                "source_record_id",
                "retrieved_at",
            ):
                if location.get(field_name) is not None:
                    result.errors.append(f"{label}.{field_name} must be null while pending")
        else:
            verified += 1
            if status == "verified_official_historical":
                historical += 1
                if location.get("operational_status") != "closed_historical":
                    result.errors.append(f"{label} historical location must be marked closed_historical")
            elif location.get("operational_status") != "current_official_record":
                result.errors.append(f"{label} current official location has inconsistent operational_status")
            if not isinstance(location.get("address"), str) or not location["address"].strip():
                result.errors.append(f"{label}.address is required")
            lat = location.get("lat")
            lng = location.get("lng")
            if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not 37.5 <= lat <= 39.6:
                result.errors.append(f"{label}.lat is outside the DC region")
            if not isinstance(lng, (int, float)) or isinstance(lng, bool) or not -78.2 <= lng <= -76.2:
                result.errors.append(f"{label}.lng is outside the DC region")
            parsed = urlparse(location.get("source_url") or "")
            if parsed.scheme != "https" or not parsed.hostname:
                result.errors.append(f"{label}.source_url must be official HTTPS evidence")
            coordinate_url = urlparse(location.get("coordinate_source_url") or "")
            if coordinate_url.scheme != "https" or not coordinate_url.hostname:
                result.errors.append(f"{label}.coordinate_source_url must be official HTTPS evidence")
            if (
                not location.get("source_name")
                or not location.get("source_dataset_id")
                or not location.get("source_record_id")
                or not location.get("retrieved_at")
            ):
                result.errors.append(f"{label} lacks official source provenance")
    duplicates = _duplicates(ids)
    if duplicates:
        result.errors.append(f"Duplicate location school_ids: {duplicates}")
    if set(ids) != set(schools):
        result.errors.append("Location registry school IDs do not equal schools.json")
    summary = registry.get("summary")
    expected_summary = {"schools": len(locations), "verified_official": verified, "pending_official_source": pending}
    if summary != expected_summary:
        result.errors.append(f"Location summary mismatch: expected {expected_summary}, found {summary}")
    result.summary["locations_verified_official"] = verified
    result.summary["locations_verified_historical"] = historical
    result.summary["locations_pending"] = pending


def _validate_location_evidence(
    project_root: Path, schools: dict[str, dict[str, object]], result: ValidationResult
) -> None:
    evidence = _load_json(project_root / "data" / "location-evidence.json", result)
    registry = _load_json(project_root / "data" / "school-locations.json", result)
    configuration = _load_json(project_root / "config" / "location-sources.json", result)
    aliases = _load_json(project_root / "data" / "location-aliases.json", result)
    overrides = _load_json(project_root / "data" / "location-overrides.json", result)
    if not all(isinstance(item, dict) for item in (evidence, registry, configuration, aliases, overrides)):
        return
    matches = evidence.get("matches")
    locations = registry.get("locations")
    if not isinstance(matches, list) or not isinstance(locations, list):
        result.errors.append("Location evidence and registry must contain arrays")
        return
    matches_by_id = {match.get("school_id"): match for match in matches if isinstance(match, dict)}
    locations_by_id = {location.get("school_id"): location for location in locations if isinstance(location, dict)}
    if len(matches_by_id) != len(matches) or set(matches_by_id) != set(schools):
        result.errors.append("Location evidence must cover every school exactly once")
    approved_source_ids = {
        source.get("id")
        for source in configuration.get("sources", [])
        if isinstance(source, dict) and source.get("official") is True and source.get("status") == "approved"
    }
    for school_id, match in matches_by_id.items():
        if match.get("source_dataset_id") not in approved_source_ids:
            result.errors.append(f"Location evidence for {school_id} uses an unapproved source")
        location = locations_by_id.get(school_id)
        if not location:
            continue
        for field_name in ("address", "lat", "lng", "source_dataset_id", "source_record_id"):
            if match.get(field_name) != location.get(field_name):
                result.errors.append(f"Location evidence mismatch for {school_id}.{field_name}")
    alias_rows = aliases.get("aliases")
    if not isinstance(alias_rows, list):
        result.errors.append("data/location-aliases.json must contain aliases")
    else:
        alias_ids = [alias.get("school_id") for alias in alias_rows if isinstance(alias, dict)]
        if _duplicates(alias_ids):
            result.errors.append("Location aliases contain duplicate school IDs")
        for alias in alias_rows:
            if (
                not isinstance(alias, dict)
                or alias.get("school_id") not in schools
                or alias.get("source_id") not in approved_source_ids
                or not alias.get("reason")
            ):
                result.errors.append(f"Invalid explicit location alias: {alias!r}")
    override_rows = overrides.get("overrides")
    if not isinstance(override_rows, list) or len(override_rows) != 1:
        result.errors.append("Exactly one historical location override is expected")
    elif override_rows[0].get("school_id") != "prince_georges_county_md:turning_point_academy_public_charter":
        result.errors.append("Historical location override targets the wrong school")
    result.summary["location_evidence"] = len(matches_by_id)


def _validate_configs(project_root: Path, result: ValidationResult) -> None:
    ratings = _load_json(project_root / "config" / "rating-sources.json", result)
    if not isinstance(ratings, dict) or ratings.get("score_input_policy") != "only_user_supplied_workbook":
        result.errors.append("Rating config must enforce the user workbook as the only score input")
    else:
        sources = ratings.get("sources")
        if not isinstance(sources, list) or len(sources) != 1:
            result.errors.append("Rating config must contain exactly one source")
        else:
            source = sources[0]
            if source.get("method") != "user_supplied_workbook" or source.get("workbook_sha256") != SOURCE_SHA256:
                result.errors.append("Rating source config does not match the immutable workbook")
            if source.get("automated_provider_access") is not False:
                result.errors.append("Rating config must not claim automated provider access")
    locations = _load_json(project_root / "config" / "location-sources.json", result)
    if not isinstance(locations, dict) or not isinstance(locations.get("sources"), list):
        result.errors.append("Location source config must contain sources")
    else:
        source_ids = []
        for index, source in enumerate(locations["sources"], start=1):
            if not isinstance(source, dict):
                result.errors.append(f"location source {index} must be an object")
                continue
            source_ids.append(source.get("id"))
            if source.get("official") is not True or source.get("status") != "approved":
                result.errors.append(f"location source {source.get('id')!r} is not approved official")
            parsed = urlparse(source.get("source_url") or "")
            if parsed.scheme != "https" or parsed.hostname not in source.get("allowed_hosts", []):
                result.errors.append(f"location source {source.get('id')!r} has an invalid URL/host contract")
        duplicates = _duplicates(source_ids)
        if duplicates:
            result.errors.append(f"Duplicate location source IDs: {duplicates}")


def validate_project(project_root: Path) -> ValidationResult:
    result = ValidationResult()
    schools = _validate_schools(project_root, result)
    _validate_evidence(project_root, schools, result)
    _validate_locations(project_root, schools, result)
    _validate_location_evidence(project_root, schools, result)
    _validate_configs(project_root, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    result = validate_project(arguments.project_root.resolve())
    if result.ok:
        summary = ", ".join(f"{key}={value}" for key, value in sorted(result.summary.items()))
        print(f"PASS: middle-school data validation succeeded ({summary}).")
        return 0
    print(f"FAIL: {len(result.errors)} validation error(s):")
    for error in result.errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
