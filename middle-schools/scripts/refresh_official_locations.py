"""Refresh school coordinates from configured official public-sector layers.

Exact normalized names are accepted only within the configured jurisdiction and
school type.  Every non-exact match must be declared in data/location-aliases.json.
NCES EDGE is the final jurisdiction-aware fallback.
"""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RUN_ID = "locations-official-20260830"
RETRIEVED_AT = "2026-08-30T00:00:00Z"
PAGE_SIZE = 2000
USER_AGENT = "highschools-dc-metro reproducible data refresh"

JURISDICTION_COUNTIES = {
    "Arlington, VA": {"arlington county"},
    "Fairfax County, VA": {"fairfax county"},
    "Falls Church City, VA": {"falls church city"},
    "Alexandria City, VA": {"alexandria city"},
    "Montgomery County, MD": {"montgomery county"},
    "Prince George's County, MD": {"prince georges county"},
    "Washington, DC": {"district of columbia"},
}


class RefreshFailure(ValueError):
    """Raised when an official refresh cannot satisfy its contract."""


def _load_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ").replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def match_key(value: object) -> str:
    """Apply only documented institutional-suffix equivalences, never fuzzy matching."""
    tokens = normalize(value).split()
    tokens = ["public charter" if token == "pcs" else token for token in tokens]
    flattened = " ".join(tokens).replace("public charter public charter", "public charter")
    tokens = flattened.split()
    terminal_sequences = (
        ["middle", "school"],
        ["middle"],
        ["ms"],
        ["school"],
    )
    for suffix in terminal_sequences:
        if len(tokens) > len(suffix) and tokens[-len(suffix) :] == suffix:
            tokens = tokens[: -len(suffix)]
            break
    return " ".join(tokens)


def _first(properties: dict[str, object], fields: list[str]):
    for field in fields:
        value = properties.get(field)
        if value is not None and str(value).strip():
            return value
    return None


def _official_address(properties: dict[str, object], fields: list[str]) -> str | None:
    parts: list[str] = []
    for field in fields:
        value = properties.get(field)
        if value is not None and str(value).strip():
            text = str(value).strip()
            if not parts or normalize(text) != normalize(parts[-1]):
                parts.append(text)
    return ", ".join(parts) if parts else None


def _float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _feature_coordinates(feature: dict[str, object], source: dict[str, object]) -> tuple[float | None, float | None]:
    properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    lat = _float(_first(properties, source.get("latitude_fields", [])))
    lng = _float(_first(properties, source.get("longitude_fields", [])))
    geometry = feature.get("geometry")
    if (lat is None or lng is None) and isinstance(geometry, dict) and geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, list) and len(coordinates) >= 2:
            lng = _float(coordinates[0])
            lat = _float(coordinates[1])
    return lat, lng


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fetch_arcgis(source: dict[str, object]) -> tuple[list[dict[str, object]], str]:
    features: list[dict[str, object]] = []
    offset = 0
    where = str(source.get("query_where") or "1=1")
    while True:
        query = urlencode(
            {
                "where": where,
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "orderByFields": "OBJECTID",
            }
        )
        request = Request(f"{source['source_url']}/query?{query}", headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
        page = payload.get("features")
        if not isinstance(page, list):
            raise RefreshFailure(f"{source['id']} did not return a GeoJSON feature array")
        features.extend(item for item in page if isinstance(item, dict))
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
    return features, _canonical_hash(features)


def normalize_features(source: dict[str, object], raw_features: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for feature in raw_features:
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        name = _first(properties, source.get("name_fields", []))
        record_id = _first(properties, source.get("record_id_fields", []))
        lat, lng = _feature_coordinates(feature, source)
        if not name or record_id is None or lat is None or lng is None:
            continue
        if not 37.5 <= lat <= 39.6 or not -78.2 <= lng <= -76.2:
            continue
        normalized.append(
            {
                "source_id": source["id"],
                "source_name": source["name"],
                "source_url": source["source_url"],
                "source_record_id": str(record_id),
                "official_name": str(name).strip(),
                "normalized_name": match_key(name),
                "address": _official_address(properties, source.get("address_fields", [])),
                "city": str(properties.get("CITY") or "").strip() or None,
                "county": str(properties.get(source.get("county_field", "")) or "").strip() or None,
                "lat": lat,
                "lng": lng,
                "record_sha256": _canonical_hash(feature),
            }
        )
    return normalized


def _eligible(feature: dict[str, object], source: dict[str, object], school: dict[str, object]) -> bool:
    if source.get("jurisdiction") not in {school["jurisdiction"], "regional_fallback"}:
        return False
    if source.get("school_type") and source["school_type"] != school["school_type"]:
        return False
    if source.get("jurisdiction") == "regional_fallback":
        county = normalize(feature.get("county"))
        if county not in JURISDICTION_COUNTIES[school["jurisdiction"]]:
            return False
    return True


def _resolve_alias(
    alias: dict[str, object],
    features_by_source: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    candidates = features_by_source.get(str(alias.get("source_id")), [])
    record_id = alias.get("source_record_id")
    official_name = alias.get("official_name")
    if record_id is not None:
        candidates = [item for item in candidates if item["source_record_id"] == str(record_id)]
    if official_name:
        candidates = [item for item in candidates if item["normalized_name"] == match_key(official_name)]
    if len(candidates) != 1:
        raise RefreshFailure(
            f"Alias for {alias.get('school_id')} resolved to {len(candidates)} records in {alias.get('source_id')}"
        )
    return candidates[0]


def _exact_match(
    school: dict[str, object],
    sources: list[dict[str, object]],
    features_by_source: dict[str, list[dict[str, object]]],
) -> dict[str, object] | None:
    wanted_name = match_key(school["name"])
    wanted_city = normalize(school["city"])
    for source in sources:
        if source.get("transport") != "arcgis_feature_layer":
            continue
        candidates = [
            feature
            for feature in features_by_source.get(source["id"], [])
            if _eligible(feature, source, school) and feature["normalized_name"] == wanted_name
        ]
        if len(candidates) > 1:
            city_candidates = [item for item in candidates if normalize(item.get("city")) == wanted_city]
            candidates = city_candidates or candidates
        if len(candidates) == 1:
            return candidates[0]
    return None


def _supplement_address(
    school: dict[str, object],
    selected_feature: dict[str, object],
    source_by_id: dict[str, dict[str, object]],
    features_by_source: dict[str, list[dict[str, object]]],
) -> dict[str, object] | None:
    if selected_feature.get("address"):
        return None
    source_id = "nces_edge_public_school_locations_2024_2025"
    source = source_by_id[source_id]
    keys = {match_key(school["name"]), selected_feature["normalized_name"]}
    candidates = [
        feature
        for feature in features_by_source.get(source_id, [])
        if _eligible(feature, source, school) and feature.get("address") and feature["normalized_name"] in keys
    ]
    if len(candidates) > 1:
        city = normalize(school["city"])
        city_candidates = [feature for feature in candidates if normalize(feature.get("city")) == city]
        candidates = city_candidates or candidates
    return candidates[0] if len(candidates) == 1 else None


def _suggestions(
    school: dict[str, object],
    sources: list[dict[str, object]],
    features_by_source: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    wanted_name = match_key(school["name"])
    scored: list[tuple[float, dict[str, object]]] = []
    for source in sources:
        for feature in features_by_source.get(source.get("id"), []):
            if not _eligible(feature, source, school):
                continue
            score = SequenceMatcher(None, wanted_name, feature["normalized_name"]).ratio()
            scored.append((score, feature))
    return [
        {
            "similarity": round(score, 4),
            "source_id": feature["source_id"],
            "source_record_id": feature["source_record_id"],
            "official_name": feature["official_name"],
            "city": feature["city"],
        }
        for score, feature in sorted(scored, key=lambda item: (-item[0], item[1]["official_name"]))[:5]
    ]


def refresh(project_root: Path) -> dict[str, int]:
    schools = _load_json(project_root / "data" / "schools.json")
    configuration = _load_json(project_root / "config" / "location-sources.json")
    alias_payload = _load_json(project_root / "data" / "location-aliases.json")
    override_payload = _load_json(project_root / "data" / "location-overrides.json")
    sources = [source for source in configuration["sources"] if source.get("status") == "approved"]
    source_by_id = {source["id"]: source for source in sources}
    aliases = {alias["school_id"]: alias for alias in alias_payload.get("aliases", [])}
    overrides = {override["school_id"]: override for override in override_payload.get("overrides", [])}
    if len(aliases) != len(alias_payload.get("aliases", [])):
        raise RefreshFailure("Duplicate school_id values in data/location-aliases.json")
    if len(overrides) != len(override_payload.get("overrides", [])):
        raise RefreshFailure("Duplicate school_id values in data/location-overrides.json")

    features_by_source: dict[str, list[dict[str, object]]] = {}
    source_snapshots: list[dict[str, object]] = []
    for source in sources:
        if source.get("transport") != "arcgis_feature_layer":
            continue
        try:
            raw_features, response_hash = fetch_arcgis(source)
            normalized = normalize_features(source, raw_features)
            features_by_source[source["id"]] = normalized
            source_snapshots.append(
                {
                    "source_id": source["id"],
                    "source_url": source["source_url"],
                    "retrieved_at": RETRIEVED_AT,
                    "status": "fetched",
                    "feature_count": len(raw_features),
                    "usable_point_count": len(normalized),
                    "response_sha256": response_hash,
                }
            )
        except Exception as error:  # A failed local source may fall back to NCES, but is recorded.
            features_by_source[source["id"]] = []
            source_snapshots.append(
                {
                    "source_id": source["id"],
                    "source_url": source["source_url"],
                    "retrieved_at": RETRIEVED_AT,
                    "status": "error",
                    "error": str(error),
                }
            )

    locations: list[dict[str, object]] = []
    evidence_matches: list[dict[str, object]] = []
    unmatched: list[dict[str, object]] = []
    used_records: set[tuple[str, str]] = set()
    for school in schools:
        override = overrides.get(school["id"])
        if override:
            lat = _float(override.get("lat"))
            lng = _float(override.get("lng"))
            if lat is None or lng is None or not 37.5 <= lat <= 39.6 or not -78.2 <= lng <= -76.2:
                raise RefreshFailure(f"Historical override for {school['id']} has invalid coordinates")
            if override.get("location_status") != "verified_official_historical":
                raise RefreshFailure(f"Historical override for {school['id']} has invalid status")
            locations.append(
                {
                    "school_id": school["id"],
                    "address": override["address"],
                    "lat": lat,
                    "lng": lng,
                    "location_status": "verified_official_historical",
                    "operational_status": override["operational_status"],
                    "source_name": override["source_name"],
                    "source_url": override["source_url"],
                    "coordinate_source_url": override["coordinate_source_url"],
                    "source_dataset_id": override["source_dataset_id"],
                    "source_record_id": override["source_record_id"],
                    "retrieved_at": override["retrieved_at"],
                    "note": override["note"],
                }
            )
            evidence_matches.append(
                {
                    "school_id": school["id"],
                    "match_method": "explicit_official_historical_override",
                    "location_status": "verified_official_historical",
                    "operational_status": override["operational_status"],
                    "source_dataset_id": override["source_dataset_id"],
                    "source_record_id": override["source_record_id"],
                    "official_name": school["name"],
                    "address": override["address"],
                    "lat": lat,
                    "lng": lng,
                    "record_sha256": _canonical_hash(override),
                }
            )
            continue
        alias = aliases.get(school["id"])
        if alias:
            source = source_by_id.get(alias.get("source_id"))
            if source is None:
                raise RefreshFailure(f"Alias source is not configured: {alias.get('source_id')}")
            feature = _resolve_alias(alias, features_by_source)
            if not _eligible(feature, source, school):
                raise RefreshFailure(f"Alias for {school['id']} crosses jurisdiction or school type")
            match_method = "explicit_alias"
        else:
            feature = _exact_match(school, sources, features_by_source)
            match_method = "exact_normalized"
        if feature is None:
            unmatched.append(
                {
                    "school_id": school["id"],
                    "name": school["name"],
                    "jurisdiction": school["jurisdiction"],
                    "city": school["city"],
                    "suggestions": _suggestions(school, sources, features_by_source),
                }
            )
            locations.append(
                {
                    "school_id": school["id"],
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
                    "retrieved_at": None,
                    "note": "No unique jurisdiction-aware official match; see the refresh report.",
                }
            )
            continue
        record_key = (feature["source_id"], feature["source_record_id"])
        if record_key in used_records:
            raise RefreshFailure(f"Official source record reused by multiple schools: {record_key}")
        used_records.add(record_key)
        address_feature = _supplement_address(school, feature, source_by_id, features_by_source)
        address = feature["address"] or (address_feature["address"] if address_feature else None)
        locations.append(
            {
                "school_id": school["id"],
                "address": address,
                "lat": feature["lat"],
                "lng": feature["lng"],
                "location_status": "verified_official",
                "operational_status": "current_official_record",
                "source_name": feature["source_name"],
                "source_url": feature["source_url"],
                "coordinate_source_url": feature["source_url"],
                "address_source_dataset_id": address_feature["source_id"] if address_feature else feature["source_id"],
                "address_source_record_id": address_feature["source_record_id"] if address_feature else feature["source_record_id"],
                "source_dataset_id": feature["source_id"],
                "source_record_id": feature["source_record_id"],
                "retrieved_at": RETRIEVED_AT,
                "note": f"{match_method}; official source name: {feature['official_name']}",
            }
        )
        evidence_matches.append(
            {
                "school_id": school["id"],
                "match_method": match_method,
                "location_status": "verified_official",
                "operational_status": "current_official_record",
                "source_dataset_id": feature["source_id"],
                "source_record_id": feature["source_record_id"],
                "official_name": feature["official_name"],
                "address": address,
                "lat": feature["lat"],
                "lng": feature["lng"],
                "record_sha256": feature["record_sha256"],
                "address_record_sha256": address_feature["record_sha256"] if address_feature else feature["record_sha256"],
            }
        )

    summary = {
        "schools": len(schools),
        "verified_official": len(evidence_matches),
        "pending_official_source": len(unmatched),
        "verified_official_historical": sum(
            match["location_status"] == "verified_official_historical" for match in evidence_matches
        ),
        "explicit_aliases_used": sum(match["match_method"] == "explicit_alias" for match in evidence_matches),
        "exact_normalized_matches": sum(match["match_method"] == "exact_normalized" for match in evidence_matches),
    }
    registry = {
        "schema_version": 1,
        "policy": "Only approved official public-sector sources may populate addresses or coordinates.",
        "summary": {key: summary[key] for key in ("schools", "verified_official", "pending_official_source")},
        "locations": locations,
    }
    evidence = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "retrieved_at": RETRIEVED_AT,
        "summary": summary,
        "source_snapshots": source_snapshots,
        "matches": evidence_matches,
    }
    report = {"schema_version": 1, "run_id": RUN_ID, "summary": summary, "unmatched": unmatched}
    _write_json(project_root / "data" / "school-locations.json", registry)
    _write_json(project_root / "data" / "location-evidence.json", evidence)
    _write_json(project_root / "outputs" / RUN_ID / "location-match-report.json", report)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allow-incomplete", action="store_true")
    arguments = parser.parse_args()
    try:
        summary = refresh(arguments.project_root.resolve())
    except (RefreshFailure, OSError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1
    print(
        f"Official location refresh: {summary['verified_official']}/{summary['schools']} matched; "
        f"aliases={summary['explicit_aliases_used']}; pending={summary['pending_official_source']}."
    )
    if summary["pending_official_source"] and not arguments.allow_incomplete:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
