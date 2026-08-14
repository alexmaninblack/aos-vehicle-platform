# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
from carla_viss_kuksa_provider import runtime  # noqa: E402


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

    def close(self) -> None:
        pass


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

    def test_component_configuration_is_strict_and_versioned(self) -> None:
        configuration = runtime.load_payload_configuration(
            ROOT / "providers/carla-viss-kuksa/config/component.json"
        )
        self.assertEqual(configuration.subscription_period_ms, 50)
        self.assertEqual(configuration.freshness_timeout_ms, 250)

        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            path = Path(directory) / "provider.json"
            payload = json.loads(
                (
                    ROOT / "providers/carla-viss-kuksa/config/component.json"
                ).read_text(encoding="utf-8")
            )
            payload["vehicleSpecificEndpoint"] = "forbidden"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                runtime.load_payload_configuration(path)

    def test_vehicle_configuration_and_credentials_stay_outside_payload(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            vehicle_configuration = root / "vehicle.json"
            vehicle_configuration.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "viss": {
                            "uri": "wss://10.0.0.1:6443",
                            "tlsServerName": "127.0.0.1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            viss_ca = root / "viss-ca.pem"
            viss_ca.write_text("test trust anchor", encoding="utf-8")
            kuksa_ca = root / "kuksa-ca.pem"
            kuksa_ca.write_text("test trust anchor", encoding="utf-8")
            credentials = root / "credentials"
            credentials.mkdir()
            (credentials / "kuksa-token").write_text("test token", encoding="utf-8")
            environment = {
                runtime.EXTERNAL_CONFIGURATION_ENV: str(vehicle_configuration),
                runtime.VISS_CA_ENV: str(viss_ca),
                runtime.CREDENTIAL_DIRECTORY_ENV: str(credentials),
            }

            with mock.patch.object(runtime, "KUKSA_CA", kuksa_ca):
                configuration = runtime.load_configuration(
                    ROOT / "providers/carla-viss-kuksa/config/component.json",
                    environment,
                )

            self.assertEqual(configuration.viss.uri, "wss://10.0.0.1:6443")
            self.assertEqual(configuration.kuksa.host, "127.0.0.1")
            self.assertEqual(configuration.kuksa.port, 55555)
            self.assertEqual(
                configuration.kuksa.token, credentials / "kuksa-token"
            )

    def test_vehicle_configuration_rejects_cleartext_transport(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            configuration_path = root / "vehicle.json"
            configuration_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "viss": {
                            "uri": "ws://10.0.0.1:6443",
                            "tlsServerName": "127.0.0.1",
                        },
                    }
                ),
                encoding="utf-8",
            )
            viss_ca = root / "viss-ca.pem"
            viss_ca.write_text("test trust anchor", encoding="utf-8")
            environment = {
                runtime.EXTERNAL_CONFIGURATION_ENV: str(configuration_path),
                runtime.VISS_CA_ENV: str(viss_ca),
            }
            with self.assertRaisesRegex(ValueError, "wss://"):
                runtime._load_viss_configuration(environment)

    def test_mark_unavailable_publishes_every_contract_signal(self) -> None:
        sink = FakeSink()
        with mock.patch.object(runtime, "KuksaSink", return_value=sink), mock.patch.object(
            runtime,
            "_load_kuksa_configuration",
            return_value=mock.sentinel.kuksa_configuration,
        ):
            runtime.mark_unavailable(
                ROOT / "providers/carla-viss-kuksa/config/component.json", {}
            )

        self.assertEqual(len(sink.publications), 1)
        self.assertEqual(
            set(sink.publications[0]), {signal.path for signal in SIGNALS}
        )
        self.assertTrue(
            all(value is None for value in sink.publications[0].values())
        )

    def test_readiness_is_an_explicit_systemd_notification(self) -> None:
        notifier = mock.MagicMock()
        notifier.__enter__.return_value = notifier
        with mock.patch.object(runtime.socket, "socket", return_value=notifier):
            runtime.notify_ready({"NOTIFY_SOCKET": "/run/systemd/notify"})

        notifier.connect.assert_called_once_with("/run/systemd/notify")
        notification = notifier.sendall.call_args.args[0]
        self.assertIn(b"READY=1", notification)
        self.assertIn(b"KUKSA authenticated", notification)

    def test_sighup_requests_unavailability_in_the_main_process(self) -> None:
        handlers = {}

        def save_handler(signal_number, handler) -> None:
            handlers[signal_number] = handler

        with mock.patch.object(
            runtime, "load_configuration", return_value=mock.sentinel.configuration
        ), mock.patch.object(
            runtime.signal, "signal", side_effect=save_handler
        ), mock.patch.object(runtime, "run", return_value=0) as run:
            self.assertEqual(runtime.main(["--config", "/tmp/provider.json"]), 0)

        handlers[runtime.signal.SIGHUP](runtime.signal.SIGHUP, None)
        unavailable_requested = run.call_args.args[2]
        self.assertTrue(unavailable_requested.is_set())
        self.assertFalse(run.call_args.args[1].is_set())


if __name__ == "__main__":
    unittest.main()
