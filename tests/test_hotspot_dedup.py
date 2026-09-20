import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from main import build_seen_before_index, has_seen_before


class HotspotDedupTests(unittest.TestCase):
    def test_index_fetches_coordinates_once(self):
        supabase = Mock()
        supabase.table.return_value.select.return_value.execute.return_value.data = [
            {"lat": 20.0, "lon": 85.0}
        ]

        index = build_seen_before_index(supabase)

        supabase.table.assert_called_once_with("hotspots")
        supabase.table.return_value.select.assert_called_once_with("lat,lon")
        self.assertTrue(has_seen_before(index, 20.005, 85.005))

    def test_boundary_points_keep_tolerance_semantics(self):
        supabase = Mock()
        supabase.table.return_value.select.return_value.execute.return_value.data = [
            {"lat": 20.0049, "lon": 85.0049}
        ]

        index = build_seen_before_index(supabase)

        self.assertTrue(has_seen_before(index, 20.0051, 85.0051))
        self.assertFalse(has_seen_before(index, 20.0151, 85.0151))


if __name__ == "__main__":
    unittest.main()
