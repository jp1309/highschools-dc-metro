"""Regression tests for the materialized school and boundary data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from scripts.import_authorized_ratings import ImportError, _source_config, validate_delivery
from scripts.validate_data import validate_project


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str):
    with (ROOT / relative_path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


class DataValidationTests(unittest.TestCase):
    def test_level_headers_share_the_same_template(self):
        high_html = (ROOT / "index.html").read_text(encoding="utf-8")
        middle_html = (ROOT / "middle-schools" / "index.html").read_text(encoding="utf-8")

        for html, level, count in (
            (high_html, "High schools", 84),
            (middle_html, "Middle schools", 192),
        ):
            self.assertIn(f"<h1>{level}, ubicaciones y zonas</h1>", html)
            self.assertIn(
                f"Explore {count} escuelas con score, tipo, grados atendidos y límites oficiales "
                "cuando están disponibles.",
                html,
            )
            self.assertIn("<span>Fecha de entrega de scores</span>", html)

    def test_project_data_passes_full_validation(self):
        result = validate_project(ROOT)
        self.assertTrue(result.ok, "\n".join(result.errors))
        self.assertEqual(result.summary["schools"], 84)
        self.assertEqual(result.summary["boundary_files"], 7)
        self.assertEqual(result.summary["boundary_features"], 85)
        self.assertEqual(result.summary["matched_features"], 84)
        self.assertEqual(result.summary["unmatched_features"], 1)
        self.assertEqual(result.summary["schools_with_boundary"], 84)
        self.assertEqual(result.summary["schools_without_boundary"], 0)
        self.assertEqual(result.summary["source_snapshots"], 7)
        self.assertEqual(result.summary["ratings_verified"], 84)
        self.assertEqual(result.summary["ratings_not_available"], 0)
        self.assertEqual(result.summary["ratings_legacy_unverified"], 0)

    def test_school_records_preserve_user_supplied_manual_evidence(self):
        schools = load_json("data/schools.json")
        self.assertEqual(len(schools), 84)
        provider_ids = set()
        for school in schools:
            self.assertEqual(school["rating_source"], "GreatSchools")
            self.assertEqual(school["rating_status"], "verified")
            self.assertEqual(school["rating_method"], "user_supplied_manual_verification")
            self.assertIsNone(school["rating_as_of"])
            self.assertEqual(school["rating_checked_at"], "2026-08-30T00:00:00Z")
            self.assertTrue(school["rating_source_url"].startswith("https://www.greatschools.org/"))
            self.assertTrue(school["rating_source_school_id"])
            self.assertTrue(school["rating_evidence_id"].startswith("user-manual-20260830:"))
            provider_ids.add(school["rating_source_school_id"])
        self.assertEqual(len(provider_ids), 84)

        ratings = {school["id"]: school["rating"] for school in schools}
        self.assertEqual(ratings["arlington_va:yorktown_high_school"], 8)
        self.assertEqual(ratings["fairfax_county_va:falls_church_high_school"], 4)
        self.assertEqual(ratings["falls_church_city_va:meridian_high_school"], 8)
        self.assertEqual(ratings["alexandria_city_va:alexandria_city_high_school"], 2)

    def test_manual_rating_evidence_covers_every_school(self):
        evidence = load_json("data/rating-evidence.json")
        run = next(item for item in evidence["runs"] if item["run_id"] == "user-manual-20260830")
        self.assertEqual(run["coverage"], 84)
        self.assertEqual(run["method"], "user_supplied_manual_verification")
        self.assertEqual(run["source_workbook"]["filename"], "lista_84_escuelas_greatschools.xlsx")
        workbook_path = ROOT / run["source_workbook"]["repository_path"]
        self.assertTrue(workbook_path.is_file())
        self.assertEqual(workbook_path.name, run["source_workbook"]["filename"])
        self.assertEqual(
            hashlib.sha256(workbook_path.read_bytes()).hexdigest(),
            run["source_workbook"]["sha256"],
        )
        self.assertEqual(len(run["attempts"]), 84)

    def test_authorized_import_requires_complete_school_coverage(self):
        schools = load_json("data/schools.json")
        rows = [
            {
                "school_id": school["id"],
                "rating": school["rating"],
                "rating_status": "verified",
                "rating_source": "GreatSchools",
                "rating_source_url": f"https://www.greatschools.org/school/{index}/",
                "rating_source_school_id": f"gs-{index}",
                "rating_as_of": "2026",
                "rating_checked_at": "2026-08-29T12:00:00Z",
                "rating_method": "authorized_bulk_feed",
            }
            for index, school in enumerate(schools, start=1)
        ]
        source = _source_config(ROOT)
        self.assertEqual(len(validate_delivery(rows, schools, source)), 84)
        with self.assertRaises(ImportError):
            validate_delivery(rows[:-1], schools, source)

    def test_known_ambiguous_names_are_explicitly_corrected(self):
        crosswalk = load_json("data/boundary-crosswalk.json")
        mappings = {
            (file_entry["path"], mapping["feature_name"]): mapping
            for file_entry in crosswalk
            for mapping in file_entry["mappings"]
        }
        self.assertEqual(
            mappings[("princegeorge_hs_boundaries.geojson", "NORTHWESTERN HIGH")]["school_id"],
            "prince_georges_county_md:northwestern_high_school",
        )
        self.assertEqual(
            mappings[("princegeorge_hs_boundaries.geojson", "DR HENRY A WISE, JR. HIGH")]["school_id"],
            "prince_georges_county_md:dr_henry_a_wise_jr_high_school",
        )

    def test_centreville_is_an_explained_unmatched_feature(self):
        crosswalk = load_json("data/boundary-crosswalk.json")
        centreville = next(
            mapping
            for file_entry in crosswalk
            if file_entry["path"] == "fairfax_hs_boundaries.geojson"
            for mapping in file_entry["mappings"]
            if mapping["feature_name"] == "Centreville"
        )
        self.assertEqual(centreville["status"], "unmatched")
        self.assertIsNone(centreville["school_id"])
        self.assertTrue(centreville["reason"])

    def test_alexandria_is_not_mislabeled_as_attendance_boundary(self):
        manifest = load_json("data/boundary-manifest.json")
        alexandria = next(item for item in manifest if item["path"] == "Alexandria.geojson")
        self.assertEqual(alexandria["boundary_type"], "municipal_boundary")

    def test_falls_church_city_boundary_is_linked_to_meridian_as_municipal_context(self):
        manifest = load_json("data/boundary-manifest.json")
        falls_church = next(
            item for item in manifest if item["path"] == "falls_church_city_boundary.geojson"
        )
        self.assertEqual(falls_church["boundary_type"], "municipal_boundary")
        self.assertEqual(falls_church["name_field"], "NAME")
        self.assertEqual(falls_church["school_year"], "unknown")

        crosswalk = load_json("data/boundary-crosswalk.json")
        file_entry = next(
            item for item in crosswalk if item["path"] == "falls_church_city_boundary.geojson"
        )
        self.assertEqual(
            file_entry["mappings"],
            [
                {
                    "feature_name": "Falls Church",
                    "status": "matched",
                    "school_id": "falls_church_city_va:meridian_high_school",
                }
            ],
        )

    def test_montgomery_manifest_uses_current_source_year(self):
        manifest = load_json("data/boundary-manifest.json")
        montgomery = next(
            item for item in manifest if item["path"] == "montgomery_hs_boundaries.geojson"
        )
        self.assertEqual(montgomery["name_field"], "S_NAME")
        self.assertEqual(montgomery["school_year"], "2026-2027")


if __name__ == "__main__":
    unittest.main()
