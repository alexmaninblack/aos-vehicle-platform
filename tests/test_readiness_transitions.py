# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Regression for the observed five-second token-renewal readiness tail."""
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers/carla-viss-kuksa/src"))
from carla_viss_kuksa_provider.advisory import canonical_json
from carla_viss_kuksa_provider.advisory_transport import (
    AdvisoryTransport, CurrentTargets, READINESS_PATHS, AVAILABILITY_PATHS,
)

NOW = dt.datetime(2026, 9, 20, 14, 38, 58, tzinfo=dt.timezone.utc)


class ReadinessTransitions(unittest.TestCase):
    def setUp(self):
        self.elapsed = 0.0
        self.client = mock.Mock()
        self.targets = CurrentTargets(self.client)
        self.socket = mock.Mock()
        self.publisher = mock.Mock()
        self.transport = AdvisoryTransport(self.targets, self.publisher, monotonic=lambda: 10 + self.elapsed)
        self.transport.attach(self.socket)
        self.values = {}

    def observe(self, brake, tire, *, age=0):
        observed = NOW + dt.timedelta(seconds=self.elapsed - age)
        self.values = {
            path: canonical_json(dict(schemaVersion=1, ready=value,
                observedAt=observed.isoformat(timespec="milliseconds").replace("+00:00", "Z")))
            for path, value in zip(READINESS_PATHS, (brake, tire))
        }
        self.client.read_advisory_targets.side_effect = None
        self.client.read_advisory_targets.return_value = self.values
        self.targets.poll()

    def tick(self, elapsed):
        self.elapsed = elapsed
        self.transport.tick(NOW + dt.timedelta(seconds=elapsed))

    def sent(self):
        return [json.loads(call.args[0]) for call in self.socket.send.call_args_list]

    def ack(self, *, error=False):
        for request_id in list(self.transport.pending):
            reply = dict(action="set", requestId=request_id)
            if error:
                reply["error"] = {"message": "fixture rejection"}
            self.transport.consume(json.dumps(reply), "subscription")

    def last_values(self):
        return {item["path"]: json.loads(item["value"])["ready"] for item in self.sent()}

    def test_false_first_renewal_recovers_promptly_and_peer_does_not_churn(self):
        self.observe(False, True); self.tick(0); self.ack()
        self.elapsed = .174; self.observe(True, True); self.tick(.174)
        self.assertEqual(3, len(self.sent()))
        self.assertEqual(AVAILABILITY_PATHS[0], self.sent()[-1]["path"])
        self.assertEqual({path: True for path in AVAILABILITY_PATHS}, self.last_values())
        self.publisher.publish_status.assert_not_called()  # not application ACK

    def test_true_first_has_no_false_and_timestamp_changes_do_not_churn(self):
        self.observe(True, True); self.tick(0); self.ack()
        for elapsed in (.1, .2, 1, 4.9):
            self.elapsed = elapsed; self.observe(True, True); self.tick(elapsed)
        self.assertEqual(2, len(self.sent()))
        self.tick(5)
        self.assertEqual(4, len(self.sent()))  # periodic liveness retained
        self.assertTrue(all(json.loads(item["value"])["ready"] for item in self.sent()))

    def test_real_loss_and_recovery_do_not_wait_for_heartbeat(self):
        self.observe(True, True); self.tick(0); self.ack()
        self.client.read_advisory_targets.side_effect = RuntimeError("offline")
        self.targets.poll(); self.tick(.2)
        self.assertEqual({path: False for path in AVAILABILITY_PATHS}, self.last_values())
        self.ack(); self.elapsed = .4; self.observe(True, True); self.tick(.4)
        self.assertEqual({path: True for path in AVAILABILITY_PATHS}, self.last_values())

    def test_stale_future_and_malformed_readiness_fail_closed(self):
        self.observe(True, True); self.tick(0); self.ack()
        self.tick(15.001)
        self.assertEqual({path: False for path in AVAILABILITY_PATHS}, self.last_values())
        for invalid in ("{}", "not-json", canonical_json(dict(schemaVersion=1, ready=True,
                observedAt="2026-09-20T15:00:00.000Z"))):
            self.ack()
            self.client.read_advisory_targets.return_value = {path: invalid for path in READINESS_PATHS}
            self.targets.poll(); self.tick(self.elapsed + 5)
            self.assertEqual({path: False for path in AVAILABILITY_PATHS}, self.last_values())

    def test_pending_write_coalesces_to_latest_not_a_stale_transition_queue(self):
        self.observe(False, True); self.tick(0)
        self.elapsed = .2; self.observe(True, True); self.tick(.2)
        self.assertEqual(2, len(self.sent()))
        self.ack(); self.tick(.21)
        self.assertEqual(3, len(self.sent()))
        self.assertTrue(json.loads(self.sent()[-1]["value"])["ready"])

    def test_rejection_uses_bounded_retry_and_current_value(self):
        self.observe(False, False); self.tick(0); self.ack(error=True)
        self.elapsed = .2; self.observe(True, True); self.tick(.2)
        self.tick(.999); self.assertEqual(2, len(self.sent()))
        self.tick(1)
        self.assertEqual(4, len(self.sent()))
        self.assertEqual({path: True for path in AVAILABILITY_PATHS}, self.last_values())
        self.publisher.publish_status.assert_not_called()

    def test_timeout_and_late_ack_do_not_establish_current_readiness(self):
        self.observe(False, False); self.tick(0)
        old_ids = list(self.transport.pending)
        self.tick(2); self.assertFalse(self.transport.pending)
        for request_id in old_ids:
            self.transport.consume(json.dumps(dict(action="set", requestId=request_id)), "subscription")
        self.elapsed = 2.5; self.observe(True, True); self.tick(2.5)
        self.assertEqual(2, len(self.sent()))
        self.tick(3); self.assertEqual(4, len(self.sent()))
        self.assertEqual({path: True for path in AVAILABILITY_PATHS}, self.last_values())

    def test_reconnect_republishes_without_inheriting_old_ack(self):
        self.observe(True, True); self.tick(0); self.ack()
        self.transport.detach(); self.tick(.2); self.assertEqual(2, len(self.sent()))
        self.observe(False, True); self.transport.attach(self.socket); self.tick(.3)
        self.assertEqual(4, len(self.sent()))
        self.assertFalse(self.last_values()[AVAILABILITY_PATHS[0]])

    def test_send_failure_does_not_leave_phantom_pending(self):
        self.observe(True, True)
        self.socket.send.side_effect = OSError("fixture send failure")
        with self.assertRaises(OSError):
            self.tick(0)
        self.assertFalse(self.transport.pending)
        self.socket.send.side_effect = None
        self.tick(.2)
        self.assertEqual(2, len(self.transport.pending))

    def test_transition_burst_is_bounded(self):
        self.observe(False, False); self.tick(0); self.ack()
        self.elapsed = .01; self.observe(True, True); self.tick(.01)
        self.assertEqual(2, len(self.sent()))
        self.tick(.101); self.assertEqual(4, len(self.sent()))


if __name__ == "__main__":
    unittest.main()
