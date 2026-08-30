"""Regression tests for official middle-school boundary snapshots."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.validate_boundaries import validate_boundaries  # noqa: E402


class MiddleBoundaryTests(unittest.TestCase):
    def test_boundaries_and_crosswalk_are_complete(self):
        result = validate_boundaries(ROOT)
        self.assertTrue(result.ok, "\n".join(result.errors))
        self.assertEqual(result.summary["layers"], 7)
        self.assertEqual(result.summary["features"], 130)
        self.assertEqual(result.summary["matched_features"], 123)
        self.assertEqual(result.summary["unmatched_features"], 7)


if __name__ == "__main__":
    unittest.main()
