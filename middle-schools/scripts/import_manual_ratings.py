"""Materialize middle-school ratings from the immutable user-supplied workbook.

The workbook is parsed with Python's standard library only.  The script never
connects to GreatSchools, and it refuses a workbook whose SHA-256 differs from
the reviewed source snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile


RUN_ID = "ratings-manual-20260830"
CHECKED_AT = "2026-08-30T00:00:00Z"
SOURCE_FILENAME = "middle_schools_greatschools_DC_area.xlsx"
SOURCE_SHA256 = "6072c6d2e43289ccfff8cd0596493296d6f96a30f586ae1d18485f595a011ce8"
SOURCE_SHEET = "Middle Schools"
EXPECTED_RECORDS = 192
TURNING_POINT_ID = "prince_georges_county_md:turning_point_academy_public_charter"
TURNING_POINT_STATUS_URL = "https://www.pgcps.org/schools/kenilworth-elementary/faculty-directory-page/clomax-rhonda"
EXPECTED_HEADERS = [
    "N.",
    "Escuela",
    "Jurisdiccion",
    "Ciudad",
    "Tipo",
    "Grados",
    "Score (1-10)",
    "Distrito escolar",
    "URL de la ficha",
]

JURISDICTION_SLUGS = {
    "Arlington, VA": "arlington_va",
    "Fairfax County, VA": "fairfax_county_va",
    "Falls Church City, VA": "falls_church_city_va",
    "Alexandria City, VA": "alexandria_city_va",
    "Montgomery County, MD": "montgomery_county_md",
    "Prince George's County, MD": "prince_georges_county_md",
    "Washington, DC": "washington_dc",
}
JURISDICTION_STATE_PATHS = {
    "Arlington, VA": ("virginia", "va"),
    "Fairfax County, VA": ("virginia", "va"),
    "Falls Church City, VA": ("virginia", "va"),
    "Alexandria City, VA": ("virginia", "va"),
    "Montgomery County, MD": ("maryland", "md"),
    "Prince George's County, MD": ("maryland", "md"),
    "Washington, DC": ("washington-dc", "dc"),
}
SCHOOL_TYPES = {"Publica": "public", "Charter": "charter"}
GRADE_VALUE = {"PK": -1, "K": 0}

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class ImportFailure(ValueError):
    """Raised when the source workbook violates the import contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference)
    if not letters:
        raise ImportFailure(f"Invalid cell reference: {cell_reference!r}")
    value = 0
    for character in letters.group(0):
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.findall(f".//{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _sheet_target(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relation_id = None
    for sheet in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if sheet.get("name") == sheet_name:
            relation_id = sheet.get(f"{{{DOC_REL_NS}}}id")
            break
    if relation_id is None:
        raise ImportFailure(f"Workbook does not contain sheet {sheet_name!r}")

    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relationship in relationships.findall(f"{{{PKG_REL_NS}}}Relationship"):
        if relationship.get("Id") == relation_id:
            target = relationship.get("Target") or ""
            if target.startswith("/"):
                return target.lstrip("/")
            return posixpath.normpath(posixpath.join("xl", target))
    raise ImportFailure(f"Missing relationship for sheet {sheet_name!r}")


def _cell_value(cell: ET.Element, shared_strings: list[str]):
    cell_type = cell.get("t")
    if cell.find(f"{{{MAIN_NS}}}f") is not None:
        raise ImportFailure(f"Formula found in immutable source cell {cell.get('r')}")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{{{MAIN_NS}}}t"))
    value_node = cell.find(f"{{{MAIN_NS}}}v")
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw)]
    if cell_type in {"str", "e"}:
        return raw
    if cell_type == "b":
        return raw == "1"
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except ValueError:
        return raw


def read_sheet_rows(workbook_path: Path, sheet_name: str) -> dict[int, list[object]]:
    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings = _shared_strings(archive)
        sheet_root = ET.fromstring(archive.read(_sheet_target(archive, sheet_name)))
    rows: dict[int, list[object]] = {}
    for row_node in sheet_root.findall(f".//{{{MAIN_NS}}}sheetData/{{{MAIN_NS}}}row"):
        row_number = int(row_node.get("r", "0"))
        cells: dict[int, object] = {}
        for cell in row_node.findall(f"{{{MAIN_NS}}}c"):
            cells[_column_index(cell.get("r", ""))] = _cell_value(cell, shared_strings)
        if cells:
            max_column = max(cells)
            rows[row_number] = [cells.get(index) for index in range(max_column + 1)]
    return rows


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().replace("&", " and ").replace("'", "")
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", normalized)).strip("_")


def _grade_number(token: str) -> int:
    token = token.strip().upper()
    if token in GRADE_VALUE:
        return GRADE_VALUE[token]
    if token.isdigit():
        return int(token)
    raise ImportFailure(f"Unsupported grade token: {token!r}")


def expand_grades(value: str) -> list[int]:
    covered: set[int] = set()
    for segment in (item.strip() for item in value.split(",")):
        match = re.fullmatch(r"(PK|K|\d+)(?:\s*-\s*(PK|K|\d+))?", segment, re.IGNORECASE)
        if not match:
            raise ImportFailure(f"Unsupported grade range: {value!r}")
        start = _grade_number(match.group(1))
        end = _grade_number(match.group(2)) if match.group(2) else start
        if start > end:
            raise ImportFailure(f"Descending grade range: {value!r}")
        covered.update(range(start, end + 1))
    return sorted(covered)


def parse_grades(value: str) -> tuple[int, int, bool]:
    covered = expand_grades(value)
    return min(covered), max(covered), bool(set(covered).intersection({6, 7, 8}))


def _normalize_place(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", slugify(value).replace("_", " ")).strip()


def parse_provider_url(url: str, jurisdiction: str, city: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "www.greatschools.org":
        raise ImportFailure(f"Unsupported rating URL: {url!r}")
    if parsed.query or parsed.fragment:
        raise ImportFailure(f"Rating URL must not contain query or fragment: {url!r}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3:
        raise ImportFailure(f"Unexpected GreatSchools URL path: {url!r}")
    expected_state_path, state_code = JURISDICTION_STATE_PATHS[jurisdiction]
    if parts[0] != expected_state_path:
        raise ImportFailure(f"URL state does not match jurisdiction: {url!r}")
    if _normalize_place(parts[1]) != _normalize_place(city):
        raise ImportFailure(f"URL city does not match workbook city: {url!r} vs {city!r}")
    match = re.fullmatch(r"(\d+)-(.+)", parts[2])
    if not match:
        raise ImportFailure(f"URL does not expose a numeric provider ID: {url!r}")
    return f"{state_code}-{match.group(1)}", match.group(1)


def _required_text(row: dict[str, object], field: str, label: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ImportFailure(f"{label}.{field} must be non-empty text")
    return value.strip()


def workbook_records(workbook_path: Path) -> list[dict[str, object]]:
    rows = read_sheet_rows(workbook_path, SOURCE_SHEET)
    headers = rows.get(5, [])
    if headers != EXPECTED_HEADERS:
        raise ImportFailure(f"Unexpected headers in row 5: {headers!r}")

    records: list[dict[str, object]] = []
    for excel_row in sorted(number for number in rows if number >= 6):
        values = rows[excel_row]
        padded = values + [None] * (len(EXPECTED_HEADERS) - len(values))
        if all(value in {None, ""} for value in padded[: len(EXPECTED_HEADERS)]):
            continue
        if len(values) > len(EXPECTED_HEADERS) and any(value not in {None, ""} for value in values[len(EXPECTED_HEADERS) :]):
            raise ImportFailure(f"Unexpected populated columns in Excel row {excel_row}")
        source = dict(zip(EXPECTED_HEADERS, padded[: len(EXPECTED_HEADERS)]))
        sequence = source["N."]
        if not isinstance(sequence, int):
            raise ImportFailure(f"Excel row {excel_row} has invalid N.: {sequence!r}")
        label = f"row {sequence}"
        name = _required_text(source, "Escuela", label)
        jurisdiction = _required_text(source, "Jurisdiccion", label)
        city = _required_text(source, "Ciudad", label)
        source_type = _required_text(source, "Tipo", label)
        grades = _required_text(source, "Grados", label)
        district_raw = _required_text(source, "Distrito escolar", label)
        url = _required_text(source, "URL de la ficha", label)
        if jurisdiction not in JURISDICTION_SLUGS:
            raise ImportFailure(f"{label} has unsupported jurisdiction {jurisdiction!r}")
        if source_type not in SCHOOL_TYPES:
            raise ImportFailure(f"{label} has unsupported type {source_type!r}")
        rating = source["Score (1-10)"]
        if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 10:
            raise ImportFailure(f"{label} has invalid score {rating!r}")
        grade_min, grade_max, contains_middle = parse_grades(grades)
        if not contains_middle:
            raise ImportFailure(f"{label} does not include grade 6, 7, or 8")
        provider_id, _ = parse_provider_url(url, jurisdiction, city)
        school_id = f"{JURISDICTION_SLUGS[jurisdiction]}:{slugify(name)}"
        evidence_id = f"{RUN_ID}:{school_id}"
        records.append(
            {
                "id": school_id,
                "source_row_number": excel_row,
                "name": name,
                "jurisdiction": jurisdiction,
                "city": city,
                "school_type": SCHOOL_TYPES[source_type],
                "grades_label": grades,
                "grades_served": expand_grades(grades),
                "grade_min": grade_min,
                "grade_max": grade_max,
                "contains_middle": contains_middle,
                "attendance_model": (
                    "charter_no_zone"
                    if SCHOOL_TYPES[source_type] == "charter"
                    else "municipal_context"
                    if jurisdiction == "Falls Church City, VA"
                    else "unknown"
                ),
                "attendance_model_note": "Pending derivation from the official boundary crosswalk.",
                "district": None if district_raw == "-" else district_raw,
                "operational_status": "closed_historical" if school_id == TURNING_POINT_ID else "not_verified",
                "operational_status_source_url": TURNING_POINT_STATUS_URL if school_id == TURNING_POINT_ID else None,
                "rating": rating,
                "rating_status": "verified_user_supplied",
                "rating_source": "GreatSchools",
                "rating_source_url": url,
                "rating_source_school_id": provider_id,
                "rating_as_of": None,
                "rating_checked_at": CHECKED_AT,
                "rating_method": "user_supplied_workbook",
                "rating_evidence_id": evidence_id,
                "provenance_note": (
                    "Score, grades and URL materialized only from the user-supplied workbook; "
                    "no automated GreatSchools request was made and redistribution permission "
                    "is not documented in this dataset."
                ),
            }
        )
    if len(records) != EXPECTED_RECORDS:
        raise ImportFailure(f"Expected {EXPECTED_RECORDS} records, found {len(records)}")
    expected_sequence = list(range(1, EXPECTED_RECORDS + 1))
    actual_sequence = [record["source_row_number"] - 5 for record in records]
    if actual_sequence != expected_sequence:
        raise ImportFailure("Workbook data rows are not contiguous and ordered")
    _assert_unique(records, "id")
    _assert_unique(records, "rating_source_url")
    _assert_unique(records, "rating_source_school_id")
    return records


def apply_attendance_models(records: list[dict[str, object]], project_root: Path) -> None:
    """Derive enrollment geography only from the explicit official-boundary crosswalk."""
    manifest_path = project_root / "data" / "boundary-manifest.json"
    crosswalk_path = project_root / "data" / "boundary-crosswalk.json"
    if not manifest_path.is_file() or not crosswalk_path.is_file():
        return
    with manifest_path.open("r", encoding="utf-8-sig") as handle:
        manifest = json.load(handle)
    with crosswalk_path.open("r", encoding="utf-8-sig") as handle:
        crosswalk = json.load(handle)
    boundary_types = {entry["path"]: entry["boundary_type"] for entry in manifest.get("entries", [])}
    linked: dict[str, list[tuple[str, str]]] = {}
    for file_entry in crosswalk.get("files", []):
        path = file_entry.get("path")
        for mapping in file_entry.get("mappings", {}).values():
            school_id = mapping.get("school_id")
            status = mapping.get("status")
            if school_id and status in {"matched", "matched_alias", "matched_context"}:
                linked.setdefault(school_id, []).append((path, status))

    for record in records:
        if record["school_type"] == "charter":
            record["attendance_model"] = "charter_no_zone"
            record["attendance_model_note"] = "Charter school; no attendance-zone polygon is assigned."
            continue
        associations = linked.get(record["id"], [])
        attendance_paths = [path for path, _ in associations if boundary_types.get(path) == "attendance_boundary"]
        municipal_paths = [path for path, _ in associations if boundary_types.get(path) == "municipal_boundary"]
        if attendance_paths:
            record["attendance_model"] = "zoned"
            record["attendance_model_note"] = f"Linked to official attendance boundary: {attendance_paths[0]}."
        elif municipal_paths:
            record["attendance_model"] = "municipal_context"
            record["attendance_model_note"] = (
                f"Linked only to municipal context, not a school attendance zone: {municipal_paths[0]}."
            )
        else:
            record["attendance_model"] = "unknown"
            record["attendance_model_note"] = (
                "No official attendance polygon is linked; choice/no-zone status was not inferred."
            )
    counts: dict[str, int] = {}
    for record in records:
        counts[record["attendance_model"]] = counts.get(record["attendance_model"], 0) + 1
    expected = {"zoned": 121, "municipal_context": 1, "charter_no_zone": 61, "unknown": 9}
    if counts != expected:
        raise ImportFailure(f"Unexpected attendance-model derivation: expected {expected}, found {counts}")


def _assert_unique(records: list[dict[str, object]], field: str) -> None:
    values = [record[field] for record in records]
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ImportFailure(f"Duplicate {field} values: {duplicates}")


def build_evidence(records: list[dict[str, object]], workbook_hash: str) -> dict[str, object]:
    attempts = [
        {
            "evidence_id": record["rating_evidence_id"],
            "school_id": record["id"],
            "source_row_number": record["source_row_number"],
            "rating": record["rating"],
            "rating_status": record["rating_status"],
            "rating_source": record["rating_source"],
            "rating_source_url": record["rating_source_url"],
            "rating_source_school_id": record["rating_source_school_id"],
            "rating_as_of": record["rating_as_of"],
            "rating_checked_at": record["rating_checked_at"],
            "rating_method": record["rating_method"],
            "outcome": "materialized_from_user_workbook",
            "note": "The pipeline preserved the workbook value without contacting GreatSchools.",
        }
        for record in records
    ]
    return {
        "schema_version": 1,
        "runs": [
            {
                "run_id": RUN_ID,
                "completed_at": CHECKED_AT,
                "source": "GreatSchools",
                "method": "user_supplied_workbook",
                "coverage": len(records),
                "source_workbook": {
                    "filename": SOURCE_FILENAME,
                    "repository_path": f"outputs/{RUN_ID}/{SOURCE_FILENAME}",
                    "sha256": workbook_hash,
                    "supplied_by": "user",
                    "sheet": SOURCE_SHEET,
                    "data_range": "A6:I197",
                    "source_role": "sole_rating_source",
                },
                "attempts": attempts,
            }
        ],
    }


def build_pending_locations(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": "Only approved official public-sector sources may populate addresses or coordinates.",
        "summary": {"schools": len(records), "verified_official": 0, "pending_official_source": len(records)},
        "locations": [
            {
                "school_id": record["id"],
                "address": None,
                "lat": None,
                "lng": None,
                "location_status": "pending_official_source",
                "operational_status": "not_verified",
                "source_name": None,
                "source_url": None,
                "coordinate_source_url": None,
                "source_dataset_id": None,
                "source_record_id": None,
                "address_source_dataset_id": None,
                "address_source_record_id": None,
                "retrieved_at": None,
                "note": "No official school-location record has been matched with sufficient confidence.",
            }
            for record in records
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def _copy_source(source: Path, destination: Path, workbook_hash: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(destination) != workbook_hash:
            raise ImportFailure(f"Refusing to overwrite different workbook snapshot: {destination}")
        return
    shutil.copyfile(source, destination)
    if sha256_file(destination) != workbook_hash:
        destination.unlink(missing_ok=True)
        raise ImportFailure("Copied workbook hash does not match source")


def materialize(source: Path, project_root: Path) -> dict[str, object]:
    source = source.resolve()
    project_root = project_root.resolve()
    if not source.is_file():
        raise ImportFailure(f"Workbook not found: {source}")
    workbook_hash = sha256_file(source)
    if workbook_hash != SOURCE_SHA256:
        raise ImportFailure(f"Workbook SHA-256 mismatch: expected {SOURCE_SHA256}, found {workbook_hash}")
    records = workbook_records(source)
    apply_attendance_models(records, project_root)
    copied_workbook = project_root / "outputs" / RUN_ID / SOURCE_FILENAME
    _copy_source(source, copied_workbook, workbook_hash)

    schools_path = project_root / "data" / "schools.json"
    evidence_path = project_root / "data" / "rating-evidence.json"
    locations_path = project_root / "data" / "school-locations.json"
    summary_path = project_root / "outputs" / RUN_ID / "import-summary.json"
    _write_json(schools_path, records)
    _write_json(evidence_path, build_evidence(records, workbook_hash))
    if not locations_path.exists():
        _write_json(locations_path, build_pending_locations(records))
    summary = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "completed_at": CHECKED_AT,
        "source_workbook": str(copied_workbook.relative_to(project_root)).replace("\\", "/"),
        "source_sha256": workbook_hash,
        "records": len(records),
        "rating_source": "GreatSchools",
        "rating_input": "user_supplied_workbook_only",
        "outputs": ["data/schools.json", "data/rating-evidence.json", "data/school-locations.json"],
    }
    _write_json(summary_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Path to the user-supplied XLSX")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="middle-schools project directory",
    )
    arguments = parser.parse_args()
    try:
        summary = materialize(arguments.source, arguments.project_root)
    except (ImportFailure, OSError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}")
        return 1
    print(
        f"PASS: materialized {summary['records']} records from the immutable workbook "
        f"({summary['source_sha256']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
