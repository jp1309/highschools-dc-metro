"""Validate and materialize a complete, licensed school-rating delivery.

This script never scrapes provider pages and never downloads provider data. It
accepts a JSON or CSV delivery that the operator is already authorized to store,
combine and publish. Preview is the default; --apply is transactional and also
requires --license-confirmed.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"^\d{4}(?:-(?:0[1-9]|1[0-2]))?$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
ALLOWED_STATUSES = {"verified", "not_available"}
REQUIRED_COLUMNS = {
    "school_id",
    "rating",
    "rating_status",
    "rating_source",
    "rating_source_url",
    "rating_source_school_id",
    "rating_as_of",
    "rating_checked_at",
    "rating_method",
}


class ImportError(ValueError):
    """Raised when an authorized delivery is incomplete or inconsistent."""


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = _load_json(path)
        if isinstance(data, dict):
            data = data.get("ratings")
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ImportError("JSON input must be an array, or an object with a ratings array")
        return data
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    raise ImportError("Input must be .json or .csv")


def _nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _rating(value: Any) -> int | None:
    text = _nullable_text(value)
    if text is None:
        return None
    try:
        number = int(text)
    except (TypeError, ValueError) as exc:
        raise ImportError(f"rating must be a whole number or blank, got {value!r}") from exc
    if str(number) != text and not (isinstance(value, int) and not isinstance(value, bool)):
        raise ImportError(f"rating must be a whole number or blank, got {value!r}")
    return number


def _parse_utc(value: str, label: str) -> datetime:
    if not UTC_RE.fullmatch(value):
        raise ImportError(f"{label} must be RFC 3339 UTC with a trailing Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed > datetime.now(timezone.utc):
        raise ImportError(f"{label} must not be in the future")
    return parsed


def _source_config(root: Path) -> dict[str, Any]:
    config = _load_json(root / "config" / "rating-sources.json")
    sources = config.get("sources") if isinstance(config, dict) else None
    if not isinstance(sources, list):
        raise ImportError("config/rating-sources.json must contain a sources array")
    greatschools = next(
        (item for item in sources if isinstance(item, dict) and item.get("id") == "greatschools"),
        None,
    )
    if greatschools is None:
        raise ImportError("rating source configuration is missing greatschools")
    return greatschools


def _validate_row(
    raw: dict[str, Any],
    school_ids: set[str],
    source: dict[str, Any],
    row_number: int,
) -> dict[str, Any]:
    label = f"row {row_number}"
    missing = sorted(REQUIRED_COLUMNS - set(raw))
    if missing:
        raise ImportError(f"{label} is missing columns: {missing}")

    school_id = _nullable_text(raw.get("school_id"))
    if school_id not in school_ids:
        raise ImportError(f"{label} references unknown school_id {school_id!r}")
    status = _nullable_text(raw.get("rating_status"))
    if status not in ALLOWED_STATUSES:
        raise ImportError(f"{label}.rating_status must be verified or not_available")
    rating = _rating(raw.get("rating"))
    if status == "verified" and rating is None:
        raise ImportError(f"{label} verified record requires a rating")
    if status == "not_available" and rating is not None:
        raise ImportError(f"{label} not_available record must have a blank rating")
    if rating is not None and not source["rating_min"] <= rating <= source["rating_max"]:
        raise ImportError(f"{label}.rating is outside the configured scale")

    source_name = _nullable_text(raw.get("rating_source"))
    if source_name != source["name"]:
        raise ImportError(f"{label}.rating_source must be {source['name']!r}")
    method = _nullable_text(raw.get("rating_method"))
    if method != "authorized_bulk_feed":
        raise ImportError(f"{label}.rating_method must be authorized_bulk_feed")

    source_url = _nullable_text(raw.get("rating_source_url"))
    if source_url is None:
        raise ImportError(f"{label} requires the provider's individual school URL")
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or parsed_url.hostname not in source["allowed_hosts"]:
        raise ImportError(f"{label}.rating_source_url must be an allowed HTTPS provider URL")
    if "/search/" in parsed_url.path or not parsed_url.path.rstrip("/"):
        raise ImportError(f"{label}.rating_source_url must be an individual school URL")

    provider_id = _nullable_text(raw.get("rating_source_school_id"))
    if provider_id is None:
        raise ImportError(f"{label} requires rating_source_school_id")
    rating_as_of = _nullable_text(raw.get("rating_as_of"))
    if rating_as_of is not None and not DATE_RE.fullmatch(rating_as_of):
        raise ImportError(f"{label}.rating_as_of must be YYYY, YYYY-MM or blank")
    checked_at = _nullable_text(raw.get("rating_checked_at"))
    if checked_at is None:
        raise ImportError(f"{label} requires rating_checked_at")
    checked_date = _parse_utc(checked_at, f"{label}.rating_checked_at")
    if rating_as_of is not None and int(rating_as_of[:4]) > checked_date.year:
        raise ImportError(f"{label}.rating_as_of cannot be later than rating_checked_at")

    return {
        "school_id": school_id,
        "rating": rating,
        "rating_status": status,
        "rating_source": source_name,
        "rating_source_url": source_url,
        "rating_source_school_id": provider_id,
        "rating_as_of": rating_as_of,
        "rating_checked_at": checked_at,
        "rating_method": method,
    }


def validate_delivery(
    rows: list[dict[str, Any]], schools: list[dict[str, Any]], source: dict[str, Any]
) -> list[dict[str, Any]]:
    school_ids = {school["id"] for school in schools}
    normalized = [
        _validate_row(row, school_ids, source, index)
        for index, row in enumerate(rows, start=2)
    ]
    delivered_ids = [row["school_id"] for row in normalized]
    duplicates = sorted({value for value in delivered_ids if delivered_ids.count(value) > 1})
    if duplicates:
        raise ImportError(f"duplicate school_id values: {duplicates}")
    if set(delivered_ids) != school_ids:
        missing = sorted(school_ids - set(delivered_ids))
        extra = sorted(set(delivered_ids) - school_ids)
        raise ImportError(
            f"delivery must cover all {len(school_ids)} schools; missing={missing}, extra={extra}"
        )
    provider_ids = [row["rating_source_school_id"] for row in normalized]
    duplicates = sorted({value for value in provider_ids if provider_ids.count(value) > 1})
    if duplicates:
        raise ImportError(f"duplicate rating_source_school_id values: {duplicates}")
    return normalized


def materialize(
    schools: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    by_id = {row["school_id"]: row for row in rows}
    latest_check = max(row["rating_checked_at"] for row in rows)
    run_id = f"greatschools-authorized-{latest_check.replace(':', '').replace('-', '')}"
    attempts: list[dict[str, Any]] = []
    changed = 0
    updated: list[dict[str, Any]] = []
    for school in schools:
        row = by_id[school["id"]]
        evidence_id = f"{run_id}:{school['id']}"
        next_school = {
            **school,
            "rating": row["rating"],
            "rating_status": row["rating_status"],
            "rating_source": row["rating_source"],
            "rating_source_url": row["rating_source_url"],
            "rating_source_school_id": row["rating_source_school_id"],
            "rating_as_of": row["rating_as_of"],
            "rating_checked_at": row["rating_checked_at"],
            "rating_method": row["rating_method"],
            "rating_evidence_id": evidence_id,
            "provenance_note": "Rating supplied through an authorized provider delivery and matched by stable local ID.",
        }
        comparable = (school.get("rating"), school.get("rating_status"))
        if comparable != (next_school["rating"], next_school["rating_status"]):
            changed += 1
        updated.append(next_school)
        attempts.append({
            "evidence_id": evidence_id,
            **row,
            "outcome": row["rating_status"],
        })

    next_evidence = dict(evidence)
    runs = list(next_evidence.get("runs", []))
    if any(run.get("run_id") == run_id for run in runs if isinstance(run, dict)):
        raise ImportError(f"evidence already contains run_id {run_id!r}")
    runs.append({
        "run_id": run_id,
        "completed_at": latest_check,
        "source": "GreatSchools",
        "method": "authorized_bulk_feed",
        "coverage": len(attempts),
        "attempts": attempts,
    })
    next_evidence["runs"] = runs
    return updated, next_evidence, changed


def _atomic_write(path: Path, data: Any) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Authorized .json or .csv delivery")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--apply", action="store_true", help="Materialize the validated delivery")
    parser.add_argument(
        "--license-confirmed",
        action="store_true",
        help="Confirm the written license permits storage, combination and public redistribution",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    try:
        if args.apply and not args.license_confirmed:
            raise ImportError("--apply requires --license-confirmed")
        schools_path = root / "data" / "schools.json"
        evidence_path = root / "data" / "rating-evidence.json"
        schools = _load_json(schools_path)
        evidence = _load_json(evidence_path)
        if not isinstance(schools, list) or not isinstance(evidence, dict):
            raise ImportError("project rating files have an invalid structure")
        rows = validate_delivery(_load_rows(args.input), schools, _source_config(root))
        updated, next_evidence, changed = materialize(schools, rows, evidence)
        print(f"Validated {len(rows)} ratings; {changed} values/statuses would change.")
        if not args.apply:
            print("Preview only. Use --apply --license-confirmed after confirming written rights.")
            return 0
        _atomic_write(schools_path, updated)
        _atomic_write(evidence_path, next_evidence)
        print("Applied authorized ratings and appended evidence.")
        return 0
    except (OSError, json.JSONDecodeError, ImportError) as exc:
        print(f"Rating import failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
