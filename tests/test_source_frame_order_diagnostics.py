# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Distinguish ordering failures without logging source values or relaxing gates."""
import json
import unittest
from test_provider import BridgeState, FakeSink, VALID_VALUES, event


class FrameOrderDiagnostics(unittest.TestCase):
    def test_changed_equal_timestamp_is_distinct_from_time_regression(self):
        for regression, reason in ((False, "SAME_TIMESTAMP_CHANGED"), (True, "TIME_REGRESSION")):
            with self.subTest(reason=reason):
                sink = FakeSink()
                bridge = BridgeState(sink, 5, lambda: 0, require_complete_frames=True)
                bridge.handle_message(event(VALID_VALUES), "7")
                changed = json.loads(event({**VALID_VALUES, "Vehicle.Speed": "43"}))
                if regression:
                    for point in changed["data"]:
                        point["dp"]["ts"] = "2026-08-14T10:20:30.122Z"
                with self.assertRaisesRegex(ValueError, "VISS source frame is not monotonic: " + reason):
                    bridge.handle_message(json.dumps(changed), "7")
                self.assertEqual(len(sink.publications), 2)
                self.assertTrue(all(value is None for value in sink.publications[-1].values()))

    def test_identical_repeat_never_renews_freshness(self):
        now = [0]
        sink = FakeSink()
        bridge = BridgeState(sink, 5, lambda: now[0], require_complete_frames=True)
        bridge.handle_message(event(VALID_VALUES), "7")
        now[0] = 6
        self.assertTrue(bridge.handle_message(event(VALID_VALUES), "7").repeated)
        self.assertEqual(len(sink.publications), 1)
        self.assertTrue(bridge.tick())
        self.assertTrue(all(value is None for value in sink.publications[-1].values()))
