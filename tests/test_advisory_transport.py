# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "providers/carla-viss-kuksa/src"))
from carla_viss_kuksa_provider.advisory import canonical_json
from carla_viss_kuksa_provider.advisory_transport import AdvisoryTransport, CurrentTargets, READINESS_PATHS, AVAILABILITY_PATHS, producer_ready
from carla_viss_kuksa_provider import runtime
from carla_viss_kuksa_provider.bridge import subscription_request
from carla_viss_kuksa_provider.releases import v3

NOW = dt.datetime.now(dt.timezone.utc)
B = "Vehicle.OEM.BrakeHealth.Advisory.Request"
T = "Vehicle.OEM.TireHealth.Advisory.Request"
BS = B.replace("Request", "GatewayStatus")
TS = T.replace("Request", "GatewayStatus")


def request(tire=False, sequence=1, seconds=0):
    issued = NOW + dt.timedelta(seconds=seconds)
    return canonical_json({
        "schemaVersion": 1, "requestId": "123e4567-e89b-42d3-a456-426614174000",
        "producerEpoch": "123e4567-e89b-42d3-a456-426614174001",
        "sequence": sequence, "operation": "SET", "decisionId": "assessment-1",
        "serviceVersion": "29.0.0" if tire else "47.0.0", "modelVersion": "model-1",
        "reasonCode": "PREDICTED_TIRE_WEAR" if tire else "PREDICTED_BRAKE_DEGRADATION",
        "recommendation": "TIRE_INSPECTION_RECOMMENDED" if tire else "INSPECTION_RECOMMENDED",
        "issuedAt": issued.isoformat().replace("+00:00", "Z"),
        "expiresAt": (issued + dt.timedelta(seconds=30)).isoformat().replace("+00:00", "Z"),
    })


def status(tire=False, state="APPLIED"):
    req = json.loads(request(tire))
    return canonical_json({
        "schemaVersion": 1, **{key: req[key] for key in ("requestId", "producerEpoch", "sequence")},
        "state": state, "reason": "NONE", "gatewayObservedAt": NOW.isoformat().replace("+00:00", "Z"),
        "activeRecommendation": req["recommendation"] if state == "APPLIED" else "NONE",
        "activeReasonCode": req["reasonCode"] if state == "APPLIED" else "NONE",
        "activeUntil": req["expiresAt"] if state == "APPLIED" else None,
    })


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.client = mock.Mock()
        self.client.read_advisory_targets.return_value = {B: request(), T: request(True)}
        self.targets = CurrentTargets(self.client)
        self.targets.poll()
        self.publisher = mock.Mock()
        self.now = 10.0
        self.transport = AdvisoryTransport(self.targets, self.publisher, monotonic=lambda: self.now)
        self.socket = mock.Mock()
        self.transport.attach(self.socket)

    def event(self, path, raw):
        return json.dumps({"action": "subscription", "subscriptionId": "7", "data": [
            {"path": path, "dp": {"value": raw, "ts": NOW.isoformat().replace("+00:00", "Z")}},
        ]})

    def test_exact_two_targets_preserve_release_and_set_is_not_application(self):
        self.transport.tick(NOW)
        sent = [json.loads(call.args[0]) for call in self.socket.send.call_args_list]
        self.assertEqual({B, T, *AVAILABILITY_PATHS}, {item["path"] for item in sent})
        self.assertEqual({"29.0.0", "47.0.0"}, {json.loads(item["value"])["serviceVersion"] for item in sent if item["path"] in (B, T)})
        self.assertEqual(4, len(self.transport.pending))
        for item in sent:
            self.assertTrue(self.transport.consume(json.dumps({"action": "set", "requestId": item["requestId"]}), "7"))
        self.publisher.publish_status.assert_not_called()
        self.transport.tick(NOW)
        self.assertEqual(4, self.socket.send.call_count)

    def test_same_identity_on_both_endpoints_and_applied_then_expired(self):
        self.transport.tick(NOW)
        for path, tire in ((BS, False), (TS, True)):
            self.assertTrue(self.transport.consume(self.event(path, status(tire)), "7"))
        self.assertEqual(2, self.publisher.publish_status.call_count)
        self.transport.consume(self.event(BS, status(state="EXPIRED")), "7")
        self.publisher.publish_status.assert_called_with(BS, status(state="EXPIRED"))
        self.transport.consume(self.event(TS, status(True)), "7")
        self.assertEqual(3, self.publisher.publish_status.call_count)

    def test_cross_endpoint_status_not_published(self):
        self.transport.tick(NOW)
        self.transport.consume(self.event(BS, status(True)), "7")
        self.publisher.publish_status.assert_not_called()

    def test_wrong_subscription_never_supplies_status(self):
        self.transport.tick(NOW)
        self.transport.consume(self.event(BS, status()), "other")
        self.publisher.publish_status.assert_not_called()

    def test_timeout_rejection_unknown_response_never_fabricates_gateway_status(self):
        self.transport.tick(NOW)
        request_id = next(iter(self.transport.pending))
        self.transport.consume(json.dumps({"action": "set", "requestId": request_id, "error": {"message": "untrusted"}}), "7")
        self.transport.consume('{"action":"set","requestId":[]}', "7")
        self.now += 3.0
        self.transport.tick(NOW)
        self.assertEqual({}, self.transport.pending)
        self.publisher.publish_status.assert_not_called()

    def test_disconnect_preserves_replay_but_sends_nothing_until_attached(self):
        self.transport.detach()
        self.transport.tick(NOW)
        self.socket.send.assert_not_called()
        self.transport.attach(self.socket)
        self.transport.tick(NOW)
        self.transport.detach()
        self.transport.attach(self.socket)
        self.transport.tick(NOW)
        self.assertEqual(6, self.socket.send.call_count)

    def test_current_mailbox_bounds_paths_size_type_and_clears_on_error(self):
        self.client.read_advisory_targets.return_value = {B: "x" * 2049, T: 42, "Vehicle.Speed": "30"}
        self.targets.poll()
        self.assertEqual((True, {}), self.targets.snapshot())
        self.client.read_advisory_targets.side_effect = RuntimeError("do not print credentials")
        self.targets.poll()
        self.assertEqual((False, {}), self.targets.snapshot())

    def test_subscription_only_extends_exact_statuses(self):
        raw = self.transport.subscription(subscription_request("p", 50, v3.SIGNALS))
        paths = json.loads(raw)["filter"][0]["parameter"]
        self.assertEqual([BS.removeprefix("Vehicle."), TS.removeprefix("Vehicle.")], paths[-2:])
        self.assertEqual(len(v3.SIGNALS) + 2, len(paths))
        self.assertNotIn(B.removeprefix("Vehicle."), paths)

    def test_mixed_event_keeps_telemetry_visible_without_inventing_status(self):
        event = json.loads(self.event(BS, ""))
        event["data"].append({"path": "Vehicle.Speed", "dp": {"value": "10", "ts": NOW.isoformat()}})
        self.assertFalse(self.transport.consume(json.dumps(event), "7"))
        self.publisher.publish_status.assert_not_called()

    def test_stale_target_is_rejected_and_not_retried_each_frame(self):
        self.transport.tick(NOW + dt.timedelta(seconds=3))
        self.transport.tick(NOW + dt.timedelta(seconds=4))
        self.assertEqual(set(AVAILABILITY_PATHS), {json.loads(call.args[0])["path"] for call in self.socket.send.call_args_list})
        self.assertEqual("STALE_REQUEST", self.transport.last_result[B])

    def test_readiness_is_bounded_fresh_and_never_an_advisory_request(self):
        value = dict(schemaVersion=1, ready=True, observedAt=NOW.isoformat().replace("+00:00", "Z"))
        raw = canonical_json(value)
        self.assertTrue(producer_ready(raw, NOW))
        self.assertFalse(producer_ready(raw, NOW - dt.timedelta(milliseconds=1)))
        self.assertFalse(producer_ready(raw, NOW + dt.timedelta(seconds=16)))
        for bad in (None, "{}", raw + " ", canonical_json(dict(value, ready=1)),
                    canonical_json(dict(value, schemaVersion=True)), canonical_json(dict(value, extra=True))):
            self.assertFalse(producer_ready(bad, NOW))
        self.client.read_advisory_targets.return_value = {READINESS_PATHS[0]: raw}
        self.targets.poll()
        self.transport.tick(NOW)
        sent = [json.loads(call.args[0]) for call in self.socket.send.call_args_list]
        self.assertEqual(list(AVAILABILITY_PATHS), [item["path"] for item in sent])
        self.assertEqual([True, False], [json.loads(item["value"])["ready"] for item in sent])
        self.publisher.publish_status.assert_not_called()
        self.client.read_advisory_targets.side_effect = RuntimeError("unavailable")
        self.targets.poll(); self.now += 5; self.transport.tick(NOW + dt.timedelta(seconds=5))
        latest = [json.loads(call.args[0]) for call in self.socket.send.call_args_list][-2:]
        self.assertEqual([False, False], [json.loads(item["value"])["ready"] for item in latest])

    def test_worker_closes_and_stops(self):
        self.targets.start()
        self.targets.close()
        self.assertFalse(self.targets.thread.is_alive())
        self.client.close.assert_called_once()

    def test_runtime_uses_one_viss_socket_and_processes_status_beside_telemetry(self):
        stop = threading.Event()
        source = mock.Mock()
        source.snapshot.return_value = (True, {B: request()})
        sink = mock.Mock()
        ws = mock.MagicMock()
        ws.__enter__.return_value = ws
        ws.subprotocol = "VISSv3"
        messages = [json.dumps({"action": "subscribe", "requestId": "carla-kuksa-provider-1", "subscriptionId": "7"}), self.event(BS, status())]
        def receive(**_):
            value = messages.pop(0)
            if not messages:
                stop.set()
            return value
        ws.recv.side_effect = receive
        connect = mock.Mock(return_value=ws)
        configuration = runtime.Configuration(
            runtime.PayloadConfiguration(50, 5000, 100, 200, signals=v3.SIGNALS, advisory_enabled=True),
            runtime.VissConfiguration("wss://unit", Path("/ca"), "unit", Path("/cert"), Path("/key")),
            runtime.KuksaConfiguration("127.0.0.1", 55555, Path("/ca"), "127.0.0.1", Path("/token")),
        )
        with mock.patch.object(runtime, "KuksaSink", return_value=sink), mock.patch.object(runtime.ssl, "create_default_context"), mock.patch("carla_viss_kuksa_provider.advisory_transport.CurrentTargets", return_value=source):
            runtime.run(configuration, stop, threading.Event(), connect_factory=connect)
        connect.assert_called_once()
        source.start.assert_called_once()
        source.close.assert_called_once()
        sink.publish_status.assert_called_once_with(BS, status())


if __name__ == "__main__":
    unittest.main()
