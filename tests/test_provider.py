# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "providers/carla-viss-kuksa/src"
sys.path.insert(0, str(SOURCE))

from carla_viss_kuksa_provider.bridge import (  # noqa: E402
    BridgeState,
    SIGNALS,
    parse_snapshot,
    parse_subscribe_response,
    subscription_request,
)


def event(values: dict[str, str], subscription_id: str = "7") -> str:
    timestamp = "2026-08-14T10:20:30.123Z"
    return json.dumps(
        {
            "action": "subscription",
            "subscriptionId": subscription_id,
            "data": [
                {"path": path, "dp": {"value": value, "ts": timestamp}}
                for path, value in values.items()
            ],
            "ts": timestamp,
        }
    )


VALID_VALUES = {
    "Vehicle.Speed": "42.5",
    "Vehicle.Acceleration.Longitudinal": "1.25",
    "Vehicle.Acceleration.Lateral": "-0.5",
    "Vehicle.Acceleration.Vertical": "0.0",
    "Vehicle.Chassis.Accelerator.PedalPosition": "23",
    "Vehicle.Chassis.Brake.PedalPosition": "0",
    "Vehicle.Chassis.Axle.Row1.SteeringAngle": "-4.75",
}


class FakeSink:
    def __init__(self) -> None:
        self.publications = []

    def publish(self, values) -> None:
        self.publications.append(dict(values))


class ProviderTests(unittest.TestCase):
    def test_initial_disconnect_clears_retained_values_once(self) -> None:
        sink = FakeSink()
        bridge = BridgeState(sink, 0.25, lambda: 10.0)
        self.assertTrue(bridge.mark_unavailable())
        self.assertFalse(bridge.mark_unavailable())
        self.assertEqual(len(sink.publications), 1)
        self.assertTrue(all(value is None for value in sink.publications[0].values()))

    def test_subscription_requests_only_contract_paths(self) -> None:
        message = json.loads(subscription_request("provider-1", 50))
        self.assertEqual(message["action"], "subscribe")
        self.assertEqual(message["path"], "Vehicle")
        self.assertEqual(
            message["filter"][0]["parameter"],
            [signal.relative_path for signal in SIGNALS],
        )

    def test_subscribe_response_requires_matching_request(self) -> None:
        response = json.dumps(
            {
                "action": "subscribe",
                "requestId": "provider-1",
                "subscriptionId": "9",
            }
        )
        self.assertEqual(parse_subscribe_response(response, "provider-1"), "9")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            parse_subscribe_response(response, "another-request")

    def test_valid_frame_is_typed_and_timestamped(self) -> None:
        snapshot = parse_snapshot(event(VALID_VALUES), "7")
        self.assertEqual(snapshot.invalid_paths, ())
        self.assertEqual(snapshot.values["Vehicle.Speed"].value, 42.5)
        self.assertEqual(
            snapshot.values["Vehicle.Chassis.Accelerator.PedalPosition"].value,
            23,
        )
        self.assertEqual(
            snapshot.values["Vehicle.Speed"].timestamp.utcoffset().total_seconds(),
            0,
        )

    def test_missing_and_invalid_values_become_unavailable(self) -> None:
        values = dict(VALID_VALUES)
        values.pop("Vehicle.Chassis.Brake.PedalPosition")
        values["Vehicle.Chassis.Accelerator.PedalPosition"] = "101"
        snapshot = parse_snapshot(event(values), "7")
        self.assertIsNone(snapshot.values["Vehicle.Chassis.Brake.PedalPosition"])
        self.assertIsNone(
            snapshot.values["Vehicle.Chassis.Accelerator.PedalPosition"]
        )
        self.assertEqual(
            snapshot.invalid_paths,
            ("Vehicle.Chassis.Accelerator.PedalPosition",),
        )

    def test_duplicate_paths_are_rejected(self) -> None:
        message = json.loads(event(VALID_VALUES))
        message["data"].append(message["data"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_snapshot(json.dumps(message), "7")

    def test_stale_state_is_published_once(self) -> None:
        now = [10.0]
        sink = FakeSink()
        bridge = BridgeState(sink, 0.25, lambda: now[0])
        bridge.handle_message(event(VALID_VALUES), "7")
        now[0] = 10.24
        self.assertFalse(bridge.tick())
        now[0] = 10.25
        self.assertTrue(bridge.tick())
        self.assertFalse(bridge.tick())
        self.assertEqual(len(sink.publications), 2)
        self.assertTrue(
            all(value is None for value in sink.publications[-1].values())
        )


if __name__ == "__main__":
    unittest.main()
