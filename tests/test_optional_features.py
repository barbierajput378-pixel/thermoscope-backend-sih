import os
import unittest

from pipeline.alerts.alert_engine import should_alert, should_alert_for_risk
from pipeline.ml.features import location_id_for
from pipeline.risk.risk_scoring import score_risk


class OptionalFeatureLogicTests(unittest.TestCase):
    def test_location_id_is_stable_rounded_cell(self):
        self.assertEqual(location_id_for(20.12341, 85.12341), location_id_for(20.12349, 85.12349))

    def test_risk_score_increases_for_hot_dry_windy_history(self):
        low = score_risk(0, 0, 50, 0, 0)
        high = score_risk(5, 100, 0, 50, 10)
        self.assertEqual(low, 0)
        self.assertEqual(high, 100)

    def test_alert_thresholds(self):
        old_confidence = os.environ.get("ALERT_CONFIDENCE_THRESHOLD")
        os.environ["ALERT_CONFIDENCE_THRESHOLD"] = "0.75"
        self.assertTrue(should_alert("industrial_fire", 0.75, "high"))
        self.assertFalse(should_alert("industrial_fire", 0.74, "high"))
        self.assertFalse(should_alert("wildfire", 1, "high"))
        self.assertTrue(should_alert("wildfire", 0, "low", frp_spike=True))
        self.assertTrue(should_alert_for_risk(80))
        self.assertFalse(should_alert_for_risk(79.9))
        if old_confidence is None:
            del os.environ["ALERT_CONFIDENCE_THRESHOLD"]
        else:
            os.environ["ALERT_CONFIDENCE_THRESHOLD"] = old_confidence
