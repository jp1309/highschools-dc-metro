"""Regression tests for the elementary-school ratings pipeline."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_manual_ratings import (  # noqa: E402
    EXPECTED_HEADERS,
    EXPECTED_RECORDS,
    ImportFailure,
    RUN_ID,
    SOURCE_FILENAME,
    SOURCE_SHA256,
    materialize,
    parse_grades,
    parse_provider_url,
    read_sheet_rows,
    sha256_file,
    workbook_records,
)
from scripts.validate_data import validate_project  # noqa: E402


def load_json(relative_path: str):
    with (ROOT / relative_path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


class ElementaryRatingsPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = ROOT / "outputs" / RUN_ID / SOURCE_FILENAME

    def test_workbook_contract_and_all_552_rows(self):
        rows = read_sheet_rows(self.snapshot, "Elementary Schools")
        self.assertEqual(rows[5], EXPECTED_HEADERS)
        self.assertEqual(sorted(number for number in rows if number >= 6), list(range(6, 558)))

        schools = workbook_records(self.snapshot)
        self.assertEqual(len(schools), EXPECTED_RECORDS)
        self.assertEqual([school["source_row_number"] for school in schools], list(range(6, 558)))
        self.assertEqual(len({school["id"] for school in schools}), EXPECTED_RECORDS)
        self.assertEqual(len({school["rating_source_url"] for school in schools}), EXPECTED_RECORDS)
        self.assertEqual(len({school["rating_source_school_id"] for school in schools}), EXPECTED_RECORDS)
        self.assertTrue(all(school["contains_elementary"] for school in schools))
        self.assertTrue(all(school["school_type"] in {"public", "charter"} for school in schools))
        self.assertTrue(all(isinstance(school["rating"], int) for school in schools))
        self.assertTrue(all(1 <= school["rating"] <= 10 for school in schools))

        self.assertEqual(
            Counter(school["school_type"] for school in schools),
            {"public": 492, "charter": 60},
        )
        self.assertEqual(
            Counter(school["jurisdiction"] for school in schools),
            {
                "Arlington, VA": 25,
                "Fairfax County, VA": 134,
                "Falls Church City, VA": 2,
                "Alexandria City, VA": 14,
                "Montgomery County, MD": 126,
                "Prince George's County, MD": 121,
                "Washington, DC": 130,
            },
        )

        mt_daniel = next(school for school in schools if school["name"] == "Mt. Daniel School")
        self.assertEqual(mt_daniel["id"], "falls_church_city_va:mt_daniel_school")
        self.assertEqual(mt_daniel["source_jurisdiction"], "Fairfax County, VA")
        self.assertEqual(mt_daniel["jurisdiction"], "Falls Church City, VA")
        self.assertEqual(mt_daniel["attendance_model"], "municipal_context")
        self.assertIn("physical jurisdiction", mt_daniel["jurisdiction_resolution_note"])

        normalized_names = {
            school["name"]: school for school in schools if school["name_normalization_note"]
        }
        self.assertEqual(
            set(normalized_names),
            {
                "Bailey's Elementary School for the Arts and Sciences",
                "Bailey's Upper Elementary School for the Arts and Sciences",
                "The Children's Guild DC PCS",
            },
        )
        self.assertTrue(all("&#39;" in school["source_name"] for school in normalized_names.values()))
        self.assertTrue(all("&#39;" not in school["name"] for school in normalized_names.values()))

    def test_integrated_data_validation_passes(self):
        result = validate_project(ROOT)
        self.assertTrue(result.ok, "\n".join(result.errors))
        self.assertEqual(result.summary["schools"], EXPECTED_RECORDS)
        self.assertEqual(result.summary["rating_evidence"], EXPECTED_RECORDS)

    def test_materialized_scores_match_workbook_records(self):
        expected = workbook_records(self.snapshot)
        actual = load_json("data/schools.json")
        expected_scores = {
            school["id"]: (school["rating"], school["rating_source_url"])
            for school in expected
        }
        actual_scores = {
            school["id"]: (school["rating"], school["rating_source_url"])
            for school in actual
        }
        self.assertEqual(actual_scores, expected_scores)

    def test_rating_evidence_matches_every_school(self):
        schools = {school["id"]: school for school in load_json("data/schools.json")}
        evidence = load_json("data/rating-evidence.json")
        run = next(item for item in evidence["runs"] if item["run_id"] == RUN_ID)
        self.assertEqual(run["coverage"], EXPECTED_RECORDS)
        self.assertEqual(run["source_workbook"]["sha256"], SOURCE_SHA256)
        self.assertEqual(run["source_workbook"]["data_range"], "A6:I557")
        self.assertEqual(run["source_workbook"]["source_role"], "sole_rating_source")
        attempts = {attempt["school_id"]: attempt for attempt in run["attempts"]}
        self.assertEqual(set(attempts), set(schools))
        for school_id, school in schools.items():
            self.assertEqual(attempts[school_id]["rating"], school["rating"])
            self.assertEqual(attempts[school_id]["rating_source_url"], school["rating_source_url"])
            self.assertEqual(attempts[school_id]["outcome"], "materialized_from_user_workbook")

        mt_daniel = attempts["falls_church_city_va:mt_daniel_school"]
        self.assertEqual(mt_daniel["source_jurisdiction"], "Fairfax County, VA")
        self.assertEqual(mt_daniel["jurisdiction"], "Falls Church City, VA")
        self.assertIn("physical jurisdiction", mt_daniel["jurisdiction_resolution_note"])

    def test_workbook_snapshot_has_reviewed_sha256(self):
        self.assertTrue(self.snapshot.is_file())
        self.assertEqual(sha256_file(self.snapshot), SOURCE_SHA256)

    def test_altered_workbook_is_rejected_before_materialization(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory)
            altered = target / SOURCE_FILENAME
            altered.write_bytes(self.snapshot.read_bytes() + b"altered")
            with self.assertRaisesRegex(ImportFailure, "SHA-256 mismatch"):
                materialize(altered, target / "project")
            self.assertFalse((target / "project" / "data" / "schools.json").exists())

    def test_materialization_is_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory)
            data_dir = target / "data"
            data_dir.mkdir(parents=True)
            for filename in ("boundary-manifest.json", "boundary-crosswalk.json"):
                source = ROOT / "data" / filename
                if source.is_file():
                    shutil.copyfile(source, data_dir / filename)
            materialize(self.snapshot, target)
            for relative_path in (
                "data/schools.json",
                "data/rating-evidence.json",
                f"outputs/{RUN_ID}/import-summary.json",
            ):
                self.assertEqual((target / relative_path).read_bytes(), (ROOT / relative_path).read_bytes())

    def test_grade_parser_has_explicit_pk_and_kindergarten_scale(self):
        self.assertEqual(parse_grades("PK, K-5"), (-1, 5, True))
        self.assertEqual(parse_grades("3-5"), (3, 5, True))
        self.assertEqual(parse_grades("K-12"), (0, 12, True))
        self.assertEqual(parse_grades("6-8"), (6, 8, False))

    def test_provider_url_contract(self):
        provider_id, numeric_id = parse_provider_url(
            "https://www.greatschools.org/virginia/arlington/7904-Arlington-Science-Focus-School/",
            "Arlington, VA",
            "Arlington",
        )
        self.assertEqual(provider_id, "va-7904")
        self.assertEqual(numeric_id, "7904")
        with self.assertRaises(ImportFailure):
            parse_provider_url(
                "https://example.com/virginia/arlington/7904-Arlington-Science-Focus-School/",
                "Arlington, VA",
                "Arlington",
            )


if __name__ == "__main__":
    unittest.main()
