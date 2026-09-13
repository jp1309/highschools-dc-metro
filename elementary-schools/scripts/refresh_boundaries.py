"""Validate configured boundary sources and optionally refresh local GeoJSON.

The command is fail-closed: every enabled response is fully downloaded and
validated before any tracked file is replaced. Use ``--apply`` to write the
validated snapshots; without it the command only checks upstream state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "sources.json"
SNAPSHOT_PATH = ROOT / "data" / "source-snapshot.json"


def _geojson_snapshot_bytes(raw: bytes) -> bytes:
    """Normalize line endings so hashes survive cross-platform checkout."""

    return raw.replace(b"\r\n", b"\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Atomically replace local files after all enabled sources validate.",
    )
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args()


def download_geojson(source: dict[str, Any], timeout: int) -> tuple[bytes, dict[str, Any]]:
    params = {
        "where": source.get("where", "1=1"),
        "outFields": "*",
        "outSR": "4326",
        "returnGeometry": "true",
        "f": "geojson",
    }
    request = Request(
        f"{source['query_url']}?{urlencode(params)}",
        headers={"User-Agent": "highschools-dc-metro/1.0 data-refresh"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        status = response.status
        content_type = response.headers.get("Content-Type", "")

    if status != 200:
        raise RuntimeError(f"HTTP {status}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("response is not JSON") from exc

    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise RuntimeError(f"response is not GeoJSON: keys={list(data)[:8]}")

    features = data["features"]
    expected_features = source["expected_features"]
    if len(features) != expected_features:
        raise RuntimeError(f"expected {expected_features} features, received {len(features)}")

    name_field = source["name_field"]
    names = [feature.get("properties", {}).get(name_field) for feature in features]
    if any(not name for name in names):
        raise RuntimeError(f"{name_field} must be populated")
    if len(set(names)) != len(names) and not source.get("allow_duplicate_names"):
        raise RuntimeError(f"{name_field} must be unique unless allow_duplicate_names is explicit")

    year_field = source.get("year_field")
    year_values = sorted(
        {
            str(feature.get("properties", {}).get(year_field))
            for feature in features
            if year_field and feature.get("properties", {}).get(year_field) is not None
        }
    )
    expected_year = source.get("expected_year")
    if expected_year and year_field and year_values != [expected_year]:
        raise RuntimeError(f"expected {year_field}={expected_year}, received {year_values}")

    normalized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    metadata = {
        "id": source["id"],
        "output": source["output"],
        "query_url": source["query_url"],
        "where": source.get("where", "1=1"),
        "authority": source["authority"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "http_status": status,
        "content_type": content_type,
        "features": len(features),
        "year_values": year_values,
        "sha256": hashlib.sha256(normalized).hexdigest(),
        "bytes": len(normalized),
        "currency_status": source.get("currency_status"),
        "note": source.get("note"),
    }
    return normalized, metadata


def local_snapshot(source: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / source["output"]
    raw = _geojson_snapshot_bytes(path.read_bytes())
    data = json.loads(raw.decode("utf-8-sig"))
    return {
        "id": source["id"],
        "output": source["output"],
        "query_url": source.get("query_url"),
        "where": source.get("where", "1=1"),
        "authority": source["authority"],
        "checked_at": None,
        "http_status": None,
        "features": len(data.get("features", [])),
        "year_values": sorted(
            {
                str(feature.get("properties", {}).get(source["year_field"]))
                for feature in data.get("features", [])
                if source.get("year_field")
                and feature.get("properties", {}).get(source["year_field"]) is not None
            }
        ),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "refresh_enabled": False,
        "note": source.get("note"),
    }


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    pending: list[tuple[Path, bytes]] = []
    snapshots: list[dict[str, Any]] = []
    failures: list[str] = []

    for source in config["sources"]:
        if not source.get("enabled"):
            try:
                snapshots.append(local_snapshot(source))
                print(f"SNAPSHOT {source['id']}: local file retained")
            except Exception as exc:  # surfaced together with upstream failures
                failures.append(f"{source['id']}: local snapshot invalid: {exc}")
            continue

        try:
            content, metadata = download_geojson(source, args.timeout)
            snapshots.append(metadata | {"refresh_enabled": True})
            pending.append((ROOT / source["output"], content))
            print(
                f"OK {source['id']}: {metadata['features']} features, "
                f"years={metadata['year_values'] or ['not provided']}"
            )
        except Exception as exc:
            failures.append(f"{source['id']}: {exc}")

    if failures:
        for failure in failures:
            print(f"ERROR {failure}")
        print("No files were changed.")
        return 1

    if args.apply:
        for path, content in pending:
            atomic_write(path, content)
        snapshot_document = {
            "schema_version": 1,
            "hash_normalization": "crlf_to_lf",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": snapshots,
        }
        atomic_write(
            SNAPSHOT_PATH,
            (json.dumps(snapshot_document, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        print(f"Applied {len(pending)} validated refreshes and wrote {SNAPSHOT_PATH.relative_to(ROOT)}.")
    else:
        print(f"Validated {len(pending)} live sources. Run again with --apply to update files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
