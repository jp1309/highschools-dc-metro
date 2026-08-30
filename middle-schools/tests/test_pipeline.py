"""Regression tests for the middle-school source-to-data pipeline."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_manual_ratings import (  # noqa: E402
    EXPECTED_RECORDS,
    RUN_ID,
    SOURCE_FILENAME,
    SOURCE_SHA256,
    materialize,
    parse_grades,
    sha256_file,
)
from scripts.import_official_locations import LocationImportFailure, import_delivery  # noqa: E402
from scripts.validate_data import validate_project  # noqa: E402


def load_json(relative_path: str):
    with (ROOT / relative_path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


class MiddleSchoolPipelineTests(unittest.TestCase):
    def test_project_validation_passes(self):
        result = validate_project(ROOT)
        self.assertTrue(result.ok, "\n".join(result.errors))
        self.assertEqual(result.summary["schools"], EXPECTED_RECORDS)
        self.assertEqual(result.summary["rating_evidence"], EXPECTED_RECORDS)
        self.assertEqual(result.summary["locations_verified_official"], EXPECTED_RECORDS)
        self.assertEqual(result.summary["locations_verified_historical"], 1)
        self.assertEqual(result.summary["locations_pending"], 0)
        self.assertEqual(result.summary["attendance_zoned"], 121)
        self.assertEqual(result.summary["attendance_municipal_context"], 1)
        self.assertEqual(result.summary["attendance_charter_no_zone"], 61)
        self.assertEqual(result.summary["attendance_unknown"], 9)

    def test_scores_ids_and_jurisdictions(self):
        schools = load_json("data/schools.json")
        self.assertEqual(len(schools), EXPECTED_RECORDS)
        self.assertEqual(len({school["id"] for school in schools}), EXPECTED_RECORDS)
        self.assertEqual(len({school["rating_source_url"] for school in schools}), EXPECTED_RECORDS)
        self.assertEqual(len({school["rating_source_school_id"] for school in schools}), EXPECTED_RECORDS)
        self.assertEqual(min(school["rating"] for school in schools), 1)
        self.assertEqual(max(school["rating"] for school in schools), 10)
        self.assertTrue(all(school["contains_middle"] for school in schools))
        self.assertTrue(all(school["school_type"] in {"public", "charter"} for school in schools))
        self.assertTrue(all(isinstance(school["grades_label"], str) for school in schools))
        self.assertTrue(all(set(school["grades_served"]).intersection({6, 7, 8}) for school in schools))
        attendance_counts = {}
        for school in schools:
            attendance_counts[school["attendance_model"]] = attendance_counts.get(school["attendance_model"], 0) + 1
        self.assertEqual(
            attendance_counts,
            {"zoned": 121, "municipal_context": 1, "charter_no_zone": 61, "unknown": 9},
        )
        counts = {}
        for school in schools:
            counts[school["jurisdiction"]] = counts.get(school["jurisdiction"], 0) + 1
        self.assertEqual(
            counts,
            {
                "Arlington, VA": 6,
                "Fairfax County, VA": 25,
                "Falls Church City, VA": 1,
                "Alexandria City, VA": 3,
                "Montgomery County, MD": 39,
                "Prince George's County, MD": 43,
                "Washington, DC": 75,
            },
        )

    def test_rating_evidence_matches_every_school(self):
        schools = {school["id"]: school for school in load_json("data/schools.json")}
        evidence = load_json("data/rating-evidence.json")
        run = next(item for item in evidence["runs"] if item["run_id"] == RUN_ID)
        self.assertEqual(run["coverage"], EXPECTED_RECORDS)
        self.assertEqual(run["source_workbook"]["sha256"], SOURCE_SHA256)
        attempts = {attempt["school_id"]: attempt for attempt in run["attempts"]}
        self.assertEqual(set(attempts), set(schools))
        for school_id, school in schools.items():
            self.assertEqual(attempts[school_id]["rating"], school["rating"])
            self.assertEqual(attempts[school_id]["rating_source_url"], school["rating_source_url"])

    def test_workbook_snapshot_is_byte_identical(self):
        workbook = ROOT / "outputs" / RUN_ID / SOURCE_FILENAME
        self.assertTrue(workbook.is_file())
        self.assertEqual(sha256_file(workbook), SOURCE_SHA256)

    def test_materialization_is_reproducible(self):
        source = ROOT / "outputs" / RUN_ID / SOURCE_FILENAME
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory)
            (target / "data").mkdir(parents=True)
            for filename in ("boundary-manifest.json", "boundary-crosswalk.json"):
                shutil.copyfile(ROOT / "data" / filename, target / "data" / filename)
            materialize(source, target)
            for relative_path in (
                "data/schools.json",
                "data/rating-evidence.json",
                f"outputs/{RUN_ID}/import-summary.json",
            ):
                self.assertEqual((target / relative_path).read_bytes(), (ROOT / relative_path).read_bytes())

    def test_all_locations_are_official_and_historical_status_is_explicit(self):
        registry = load_json("data/school-locations.json")
        self.assertEqual(registry["summary"], {"schools": 192, "verified_official": 192, "pending_official_source": 0})
        self.assertTrue(all(location["address"] for location in registry["locations"]))
        self.assertTrue(all(location["lat"] is not None and location["lng"] is not None for location in registry["locations"]))
        historical = [
            location for location in registry["locations"]
            if location["location_status"] == "verified_official_historical"
        ]
        self.assertEqual(len(historical), 1)
        self.assertEqual(historical[0]["school_id"], "prince_georges_county_md:turning_point_academy_public_charter")
        self.assertEqual(historical[0]["operational_status"], "closed_historical")

        locations = {location["school_id"]: location for location in registry["locations"]}
        woodridge = locations["washington_dc:friendship_pcs_woodridge_middle"]
        self.assertIn("Woodridge", woodridge["note"])
        self.assertNotIn("Ideal", woodridge["note"])
        digital = locations["washington_dc:digital_pioneers_academy_public_charter_school"]
        self.assertTrue(digital["address"].startswith("709 12TH STREET SE"))

        evidence = load_json("data/location-evidence.json")
        self.assertEqual(len(evidence["matches"]), EXPECTED_RECORDS)
        self.assertEqual(evidence["summary"]["pending_official_source"], 0)

    def test_grade_parser_has_explicit_pk_and_kindergarten_scale(self):
        self.assertEqual(parse_grades("PK, K-8"), (-1, 8, True))
        self.assertEqual(parse_grades("K-12"), (0, 12, True))
        self.assertEqual(parse_grades("4-6"), (4, 6, True))

    def test_point_layer_can_be_toggled_and_restored_from_the_school_list(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="toggle-points"', html)
        self.assertIn('togglePoints: document.querySelector("#toggle-points")', javascript)
        self.assertIn("showPoints && schoolMatches(record.school)", javascript)
        self.assertIn("elements.togglePoints.checked = true", javascript)
        self.assertIn('elements.togglePoints.addEventListener("change", updateView)', javascript)

    def test_unapproved_location_source_is_rejected_without_mutation(self):
        registry_path = ROOT / "data" / "school-locations.json"
        before = registry_path.read_bytes()
        with tempfile.TemporaryDirectory() as temporary_directory:
            delivery_path = Path(temporary_directory) / "delivery.json"
            delivery_path.write_text(
                json.dumps({"source": {"id": "unapproved"}, "locations": []}),
                encoding="utf-8",
            )
            with self.assertRaises(LocationImportFailure):
                import_delivery(delivery_path, ROOT)
        self.assertEqual(registry_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
