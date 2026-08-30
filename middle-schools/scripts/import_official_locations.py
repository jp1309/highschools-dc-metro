"""Import school locations only from a pre-approved official-source delivery."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse


class LocationImportFailure(ValueError):
    """Raised when a location delivery is incomplete or not approved."""


def _load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: object) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def import_delivery(delivery_path: Path, project_root: Path, allow_partial: bool = False) -> dict[str, object]:
    delivery = _load_json(delivery_path)
    schools = _load_json(project_root / "data" / "schools.json")
    registry = _load_json(project_root / "data" / "school-locations.json")
    configuration = _load_json(project_root / "config" / "location-sources.json")
    schools_by_id = {school["id"]: school for school in schools}
    configured = {source["id"]: source for source in configuration.get("sources", [])}

    source = delivery.get("source")
    if not isinstance(source, dict) or source.get("id") not in configured:
        raise LocationImportFailure("Delivery source is not present in config/location-sources.json")
    approved = configured[source["id"]]
    if approved.get("official") is not True or approved.get("status") != "approved":
        raise LocationImportFailure("Configured source is not explicitly approved as official")
    source_url = source.get("url")
    parsed_source_url = urlparse(source_url or "")
    if parsed_source_url.scheme != "https" or parsed_source_url.hostname not in approved.get("allowed_hosts", []):
        raise LocationImportFailure("Delivery URL is not an approved HTTPS host")
    if not source.get("retrieved_at"):
        raise LocationImportFailure("Delivery must include retrieved_at")

    incoming = delivery.get("locations")
    if not isinstance(incoming, list):
        raise LocationImportFailure("Delivery locations must be an array")
    incoming_by_id: dict[str, dict[str, object]] = {}
    for index, item in enumerate(incoming, start=1):
        if not isinstance(item, dict):
            raise LocationImportFailure(f"locations[{index}] must be an object")
        school_id = item.get("school_id")
        if school_id not in schools_by_id:
            raise LocationImportFailure(f"Unknown school_id: {school_id!r}")
        if school_id in incoming_by_id:
            raise LocationImportFailure(f"Duplicate school_id: {school_id}")
        address = item.get("address")
        lat = item.get("lat")
        lng = item.get("lng")
        source_record_id = item.get("source_record_id")
        if not isinstance(address, str) or not address.strip():
            raise LocationImportFailure(f"{school_id} requires an official address")
        if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not 37.5 <= lat <= 39.6:
            raise LocationImportFailure(f"{school_id} latitude is outside the DC region")
        if not isinstance(lng, (int, float)) or isinstance(lng, bool) or not -78.2 <= lng <= -76.2:
            raise LocationImportFailure(f"{school_id} longitude is outside the DC region")
        if source_record_id is None or not str(source_record_id).strip():
            raise LocationImportFailure(f"{school_id} requires source_record_id")
        incoming_by_id[school_id] = {
            "school_id": school_id,
            "address": address.strip(),
            "lat": float(lat),
            "lng": float(lng),
            "location_status": "verified_official",
            "operational_status": "current_official_record",
            "source_name": approved["name"],
            "source_url": source_url,
            "coordinate_source_url": source_url,
            "source_dataset_id": approved["id"],
            "source_record_id": str(source_record_id),
            "address_source_dataset_id": approved["id"],
            "address_source_record_id": str(source_record_id),
            "retrieved_at": source["retrieved_at"],
            "note": item.get("note") or "Matched to an approved official source delivery.",
        }
    if not allow_partial and set(incoming_by_id) != set(schools_by_id):
        missing = sorted(set(schools_by_id) - set(incoming_by_id))
        raise LocationImportFailure(f"Complete coverage required; missing {len(missing)} schools")

    existing_by_id = {item["school_id"]: item for item in registry["locations"]}
    existing_by_id.update(incoming_by_id)
    records = [existing_by_id[school["id"]] for school in schools]
    verified = sum(
        item["location_status"] in {"verified_official", "verified_official_historical"}
        for item in records
    )
    pending = sum(item["location_status"] == "pending_official_source" for item in records)
    output = {
        "schema_version": 1,
        "policy": registry["policy"],
        "summary": {
            "schools": len(records),
            "verified_official": verified,
            "pending_official_source": pending,
        },
        "locations": records,
    }
    _write_json(project_root / "data" / "school-locations.json", output)
    return output["summary"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("delivery", type=Path)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    try:
        summary = import_delivery(arguments.delivery, arguments.project_root.resolve(), arguments.allow_partial)
    except (LocationImportFailure, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1
    print(
        f"PASS: {summary['verified_official']} official locations; "
        f"{summary['pending_official_source']} pending."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
