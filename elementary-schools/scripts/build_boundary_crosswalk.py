"""Build an explicit, jurisdiction-aware boundary crosswalk.

Only normalized exact names are linked automatically. Non-exact relationships
must be declared in config/boundary-aliases.json. Every remaining source feature
is retained as an explained unmatched record; no polygon is inferred for a
charter or choice school.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import html
import json
from pathlib import Path
import re
import tempfile
import unicodedata


def load(path: Path):
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write(path: Path, payload: object) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)


def normalize(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace("&", " and ").replace("'", "")
    tokens = re.sub(r"[^a-z0-9]+", " ", text).split()
    replacements = {"elem": "elementary", "es": "elementary", "sch": "school", "st": "saint"}
    tokens = [replacements.get(token, token) for token in tokens]
    removable = {"elementary", "school"}
    while tokens and tokens[-1] in removable:
        tokens.pop()
    return " ".join(tokens)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    schools = load(root / "data" / "schools.json")
    manifest = load(root / "data" / "boundary-manifest.json")
    aliases_doc = load(root / "config" / "boundary-aliases.json")
    school_by_id = {school["id"]: school for school in schools}
    aliases = {
        (alias["path"], str(alias["source_name"])): alias
        for alias in aliases_doc.get("aliases", [])
    }
    if len(aliases) != len(aliases_doc.get("aliases", [])):
        raise ValueError("Duplicate layer/source_name entries in boundary-aliases.json")

    files = []
    suggestions = []
    matched = unmatched = 0
    for layer in manifest["entries"]:
        path = layer["path"]
        jurisdiction = layer["jurisdiction"]
        name_field = layer["name_field"]
        geojson = load(root / path)
        source_names = list(dict.fromkeys(str(f["properties"][name_field]) for f in geojson["features"]))
        candidates = [
            school for school in schools
            if school["jurisdiction"] == jurisdiction and school["school_type"] != "charter"
        ]
        by_key: dict[str, list[dict[str, object]]] = {}
        for school in candidates:
            by_key.setdefault(normalize(school["name"]), []).append(school)
        mappings = {}
        for source_name in source_names:
            alias = aliases.get((path, source_name))
            if alias:
                target_ids = alias.get("school_ids") or ([alias["school_id"]] if alias.get("school_id") else [])
                if target_ids:
                    for school_id in target_ids:
                        school = school_by_id.get(school_id)
                        if not school or school["jurisdiction"] != jurisdiction or school["school_type"] == "charter":
                            raise ValueError(f"Invalid alias target for {path}:{source_name}: {school_id!r}")
                    status = "matched_context" if layer["boundary_type"] == "municipal_boundary" else "matched_alias"
                    mappings[source_name] = {
                        "status": status,
                        "school_id": target_ids[0] if len(target_ids) == 1 else None,
                        "school_ids": target_ids,
                        "reason": alias["reason"],
                    }
                    matched += 1
                else:
                    mappings[source_name] = {"status": "unmatched", "school_id": None, "reason": alias["reason"]}
                    unmatched += 1
                continue

            exact = by_key.get(normalize(source_name), [])
            if len(exact) == 1 and layer["boundary_type"] == "attendance_boundary":
                mappings[source_name] = {"status": "matched", "school_id": exact[0]["id"]}
                matched += 1
                continue

            scored = sorted(
                (
                    (SequenceMatcher(None, normalize(source_name), normalize(school["name"])).ratio(), school)
                    for school in candidates
                ),
                key=lambda item: (-item[0], str(item[1]["name"])),
            )
            mappings[source_name] = {
                "status": "unmatched",
                "school_id": None,
                "reason": "No exact rated-school record in the user workbook; no polygon was inferred."
            }
            unmatched += 1
            suggestions.append({
                "path": path,
                "source_name": source_name,
                "jurisdiction": jurisdiction,
                "candidates": [
                    {"similarity": round(score, 4), "school_id": school["id"], "school_name": school["name"]}
                    for score, school in scored[:3]
                ],
            })
        files.append({"path": path, "feature_name_field": name_field, "mappings": mappings})

    write(root / "data" / "boundary-crosswalk.json", {
        "schema_version": 1,
        "generated_at": "2026-09-12T00:00:00Z",
        "matching_policy": "Exact normalized names within the same jurisdiction plus documented explicit aliases. Charter and choice schools never receive inferred polygons.",
        "files": files,
    })
    write(root / "data-sources" / "boundary-match-suggestions.json", {
        "schema_version": 1,
        "generated_at": "2026-09-12T00:00:00Z",
        "note": "Diagnostic candidates only; similarity never creates a link.",
        "suggestions": suggestions,
    })
    print(f"PASS: matched={matched}; unmatched={unmatched}; suggestions={len(suggestions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
