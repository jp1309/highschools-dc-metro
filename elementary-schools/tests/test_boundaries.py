"""Regression tests for official middle-school boundary snapshots."""

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_boundaries import validate_boundaries  # noqa: E402


class ElementaryBoundaryTests(unittest.TestCase):
    def test_boundaries_and_crosswalk_are_complete(self):
        result = validate_boundaries(ROOT)
        self.assertTrue(result.ok, "\n".join(result.errors))
        self.assertEqual(result.summary["layers"], 7)
        self.assertEqual(result.summary["features"], 500)
        self.assertGreater(result.summary["matched_features"], 0)
        self.assertEqual(
            result.summary["matched_features"] + result.summary["unmatched_features"],
            result.summary["features"],
        )

    def test_falls_church_is_shared_municipal_context(self):
        crosswalk = json.loads((ROOT / "data" / "boundary-crosswalk.json").read_text(encoding="utf-8"))
        falls = next(item for item in crosswalk["files"] if "falls_church" in item["path"])
        mapping = falls["mappings"]["1"]
        self.assertEqual(mapping["status"], "matched_context")
        self.assertEqual(
            mapping["school_ids"],
            ["falls_church_city_va:mt_daniel_school", "falls_church_city_va:oak_street_elementary_school"],
        )

    def test_locations_are_complete_and_officially_sourced(self):
        registry = json.loads((ROOT / "data" / "school-locations.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT / "data" / "location-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["summary"], {"schools": 552, "verified_official": 552, "pending_official_source": 0})
        self.assertEqual(len(registry["locations"]), 552)
        self.assertEqual(len({item["school_id"] for item in registry["locations"]}), 552)
        self.assertEqual(len(evidence["matches"]), 552)
        self.assertTrue(all(item["address"] and item["source_url"].startswith("https://") for item in registry["locations"]))
        historical = [item for item in registry["locations"] if item["location_status"] == "verified_official_historical"]
        self.assertEqual([item["school_id"] for item in historical], ["prince_georges_county_md:middleton_valley_academy"])


if __name__ == "__main__":
    unittest.main()
