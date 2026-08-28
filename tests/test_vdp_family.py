# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "providers/carla-viss-kuksa/src"
FOTA = ROOT / "packaging/fota"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(FOTA))

from carla_viss_kuksa_provider import runtime  # noqa: E402
from carla_viss_kuksa_provider.advisory import (  # noqa: E402
    AdvisoryPolicy,
    Caller,
    canonical_json,
)
from carla_viss_kuksa_provider.bridge import (  # noqa: E402
    BridgeState,
    Snapshot,
    parse_snapshot,
)
from carla_viss_kuksa_provider.manifest import (  # noqa: E402
    ManifestError,
    load_manifest,
)
from carla_viss_kuksa_provider.readiness import (  # noqa: E402
    ReadinessTracker,
    SourceIdentity,
)
from carla_viss_kuksa_provider.releases import v1, v2, v3  # noqa: E402
import vdp_family  # noqa: E402


NOW = dt.datetime(2026, 8, 28, 12, 0, 0, tzinfo=dt.timezone.utc)
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
PRODUCER_EPOCH = "123e4567-e89b-42d3-a456-426614174001"


def viss_event(signals, timestamp: str = "2026-08-28T12:00:00.000Z") -> str:
    values = {}
    for signal in signals:
        if signal.path.endswith("PedalPosition"):
            values[signal.path] = "25"
        else:
            values[signal.path] = "1.25"
    return json.dumps(
        {
            "action": "subscription",
            "subscriptionId": "7",
            "data": [
                {"path": path, "dp": {"value": value, "ts": timestamp}}
                for path, value in values.items()
            ],
        }
    )


def request(
    *,
    service_version: str = "3.0.0",
    sequence: int = 1,
    operation: str = "SET",
    recommendation: str | None = "INSPECTION_RECOMMENDED",
    reason: str = "PREDICTED_BRAKE_DEGRADATION",
    request_id: str = REQUEST_ID,
    issued_at: dt.datetime = NOW,
    expires_at: dt.datetime | None = None,
) -> str:
    if expires_at is None:
        expires_at = issued_at + dt.timedelta(seconds=20)
    value = {
        "schemaVersion": 1,
        "requestId": request_id,
        "producerEpoch": PRODUCER_EPOCH,
        "sequence": sequence,
        "operation": operation,
        "reasonCode": reason,
        "decisionId": f"decision-{sequence}",
        "serviceVersion": service_version,
        "modelVersion": "model-1",
        "issuedAt": issued_at.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        "expiresAt": expires_at.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
    }
    if recommendation is not None:
        value["recommendation"] = recommendation
    return canonical_json(value)


def status(state: str = "APPLIED", request_id: str = REQUEST_ID) -> str:
    return canonical_json(
        {
            "schemaVersion": 1,
            "requestId": request_id,
            "producerEpoch": PRODUCER_EPOCH,
            "sequence": 1,
            "state": state,
            "reason": "NONE",
            "gatewayObservedAt": "2026-08-28T12:00:00.100Z",
            "activeRecommendation": "INSPECTION_RECOMMENDED",
            "activeReasonCode": "PREDICTED_BRAKE_DEGRADATION",
            "activeUntil": "2026-08-28T12:00:20.000Z",
        }
    )


class FakeSink:
    def __init__(self) -> None:
        self.publications = []

    def publish(self, values) -> None:
        self.publications.append(dict(values))


class FakeViss:
    def __init__(self) -> None:
        self.sets = []

    def set_value(self, path: str, canonical_value: str) -> None:
        self.sets.append((path, canonical_value))


class FakeKuksa:
    def __init__(self) -> None:
        self.statuses = []

    def publish_status(self, path: str, canonical_value: str) -> None:
        self.statuses.append((path, canonical_value))


class VdpReleaseProfileTests(unittest.TestCase):
    def test_profiles_are_exact_strict_supersets(self) -> None:
        paths1 = tuple(signal.path for signal in v1.SIGNALS)
        paths2 = tuple(signal.path for signal in v2.SIGNALS)
        paths3 = tuple(signal.path for signal in v3.SIGNALS)
        self.assertEqual(len(paths1), 7)
        self.assertEqual(paths2[: len(paths1)], paths1)
        self.assertEqual(len(paths2) - len(paths1), 8)
        self.assertEqual(paths3[: len(paths2)], paths2)
        self.assertEqual(len(paths3) - len(paths2), 8)
        self.assertEqual(v1.ADVISORY_ENDPOINT_IDS, ())
        self.assertEqual(v2.ADVISORY_ENDPOINT_IDS, ())
        self.assertEqual(
            v3.ADVISORY_ENDPOINT_IDS,
            ("BRAKE_HEALTH_ADVISORY", "TIRE_HEALTH_ADVISORY"),
        )
        self.assertTrue(
            all("AngularSpeed" not in path for path in paths1)
        )
        self.assertTrue(all("ChaosWheel" not in path for path in paths2))

    def test_manifests_match_build_selected_profiles_and_digests(self) -> None:
        for profile in (v1, v2, v3):
            path = (
                ROOT
                / "providers/carla-viss-kuksa/releases"
                / profile.VERSION
                / "capability-manifest.json"
            )
            loaded = load_manifest(path, profile)
            self.assertEqual(loaded["semanticVersion"], profile.VERSION)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                profile.MANIFEST_SHA256,
            )

    def test_wrong_version_and_manifest_mutation_fail_closed(self) -> None:
        release = ROOT / "providers/carla-viss-kuksa/releases/1.0.0"
        with self.assertRaisesRegex(ValueError, "version"):
            runtime.load_payload_configuration(release / "provider.json", v2)
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            config = json.loads((release / "provider.json").read_text())
            manifest = json.loads(
                (release / "capability-manifest.json").read_text()
            )
            manifest["readPaths"].append(
                "Vehicle.Chassis.Axle.Row1.Wheel.Left.Speed"
            )
            (root / "provider.json").write_text(json.dumps(config))
            (root / "capability-manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ManifestError, "DIGEST"):
                runtime.load_payload_configuration(root / "provider.json", v1)

    def test_all_release_payload_configurations_are_accepted(self) -> None:
        for profile in (v1, v2, v3):
            release = (
                ROOT / "providers/carla-viss-kuksa/releases" / profile.VERSION
            )
            configuration = runtime.load_payload_configuration(
                release / "provider.json", profile
            )
            self.assertEqual(configuration.semantic_version, profile.VERSION)
            self.assertEqual(configuration.signals, profile.SIGNALS)
            self.assertEqual(
                configuration.advisory_enabled, profile.VERSION == "3.0.0"
            )


class VdpSignalQualityTests(unittest.TestCase):
    def test_complete_frame_recovers_and_preserves_source_time(self) -> None:
        sink = FakeSink()
        bridge = BridgeState(
            sink,
            0.25,
            lambda: 10.0,
            v2.SIGNALS,
            require_complete_frames=True,
        )
        snapshot = bridge.handle_message(viss_event(v2.SIGNALS), "7")
        self.assertTrue(snapshot.complete)
        self.assertEqual(
            snapshot.source_timestamp,
            dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(len(sink.publications), 1)
        self.assertEqual(set(sink.publications[0]), {item.path for item in v2.SIGNALS})

    def test_missing_invalid_and_non_monotonic_frames_fail_unavailable(self) -> None:
        sink = FakeSink()
        bridge = BridgeState(
            sink,
            0.25,
            lambda: 10.0,
            v1.SIGNALS,
            require_complete_frames=True,
        )
        message = json.loads(viss_event(v1.SIGNALS))
        message["data"].pop()
        incomplete = bridge.handle_message(json.dumps(message), "7")
        self.assertFalse(incomplete.complete)
        self.assertTrue(all(value is None for value in sink.publications[-1].values()))
        bridge.handle_message(viss_event(v1.SIGNALS), "7")
        with self.assertRaisesRegex(ValueError, "monotonic"):
            bridge.handle_message(viss_event(v1.SIGNALS), "7")
        self.assertTrue(all(value is None for value in sink.publications[-1].values()))

    def test_profile_specific_parse_never_substitutes_zero(self) -> None:
        message = json.loads(viss_event(v2.SIGNALS))
        message["data"][7]["dp"]["value"] = "-1"
        snapshot = parse_snapshot(json.dumps(message), "7", v2.SIGNALS)
        angular_path = v2.SIGNALS[7].path
        self.assertIsNone(snapshot.values[angular_path])
        self.assertIn(angular_path, snapshot.invalid_paths)


class VdpReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = SourceIdentity("unit-a", "node-a", "a" * 64, 7)
        self.tracker = ReadinessTracker(self.expected)
        self.tracker.manifest_validated()

    def test_wrong_source_and_dependency_loss_are_redacted_and_fail_closed(self) -> None:
        wrong_sources = (
            SourceIdentity("unit-b", "node-a", "a" * 64, 7),
            SourceIdentity("unit-a", "node-b", "a" * 64, 7),
            SourceIdentity("unit-a", "node-a", "b" * 64, 7),
            SourceIdentity("unit-a", "node-a", "a" * 64, 8),
        )
        for wrong in wrong_sources:
            self.tracker.dependencies(
                provider_credential_ready=True,
                kuksa_ready=True,
                viss_mtls_ready=True,
                source=wrong,
            )
            self.assertEqual(
                self.tracker.view.reason, "SOURCE_IDENTITY_MISMATCH"
            )
            self.assertNotIn(wrong.unit_id, self.tracker.view.reason)
        self.tracker.dependencies(
            provider_credential_ready=False,
            kuksa_ready=True,
            viss_mtls_ready=True,
            source=self.expected,
        )
        self.assertEqual(
            self.tracker.view.reason, "PROVIDER_CREDENTIAL_UNAVAILABLE"
        )
        self.tracker.dependencies(
            provider_credential_ready=True,
            kuksa_ready=True,
            viss_mtls_ready=False,
            source=self.expected,
        )
        self.assertEqual(self.tracker.view.reason, "VISS_MTLS_UNAVAILABLE")
        self.tracker.dependencies(
            provider_credential_ready=True,
            kuksa_ready=False,
            viss_mtls_ready=True,
            source=self.expected,
        )
        self.assertEqual(self.tracker.view.reason, "KUKSA_UNAVAILABLE")

    def test_manifest_mismatch_and_recovery_are_fail_closed(self) -> None:
        self.tracker.manifest_invalid("CONTRACT_ID_MISMATCH")
        self.assertEqual(self.tracker.view.reason, "CONTRACT_ID_MISMATCH")
        self.tracker.manifest_validated()
        self.assertEqual(self.tracker.view.reason, "TELEMETRY_DISCONNECTED")

    def test_recovery_requires_one_complete_fresh_snapshot(self) -> None:
        self.tracker.dependencies(
            provider_credential_ready=True,
            kuksa_ready=True,
            viss_mtls_ready=True,
            source=self.expected,
        )
        incomplete = Snapshot({}, (), False, None)
        self.assertFalse(self.tracker.observe(incomplete))
        complete = parse_snapshot(viss_event(v1.SIGNALS), "7", v1.SIGNALS)
        self.assertTrue(self.tracker.observe(complete))
        self.assertEqual(self.tracker.view.data_readiness, "READY")
        self.tracker.disconnected()
        self.assertEqual(self.tracker.view.reason, "TELEMETRY_DISCONNECTED")
        self.assertFalse(self.tracker.observe(complete))
        self.assertEqual(self.tracker.view.reason, "TELEMETRY_STALE")

    def test_selected_unit_mtls_material_is_external_and_fingerprint_bound(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            credentials = root / "credentials"
            credentials.mkdir()
            certificate = credentials / "viss-client-cert.pem"
            certificate.write_text(
                "-----BEGIN CERTIFICATE-----\n"
                "dGVzdCBzZWxlY3RlZC11bml0IGNlcnRpZmljYXRl\n"
                "-----END CERTIFICATE-----\n"
            )
            (credentials / "viss-client-key.pem").write_text("test key")
            ca = root / "viss-ca.pem"
            ca.write_text("test CA")
            fingerprint = hashlib.sha256(
                b"test selected-unit certificate"
            ).hexdigest()
            integration = root / "vehicle.json"
            integration.write_text(
                json.dumps(
                    {
                        "schemaVersion": 2,
                        "viss": {
                            "uri": "wss://10.0.0.1:6443",
                            "tlsServerName": "127.0.0.1",
                        },
                        "selectedSource": {
                            "unitId": "unit-a",
                            "nodeId": "node-a",
                            "clientCertificateSha256": fingerprint,
                            "assignmentGeneration": 7,
                            "role": "SELECTED_PLATFORM_UNIT",
                        },
                    }
                )
            )
            environment = {
                runtime.EXTERNAL_CONFIGURATION_ENV: str(integration),
                runtime.VISS_CA_ENV: str(ca),
                runtime.CREDENTIAL_DIRECTORY_ENV: str(credentials),
            }
            configuration = runtime._load_viss_configuration(
                environment, require_mutual_tls=True
            )
            self.assertEqual(configuration.client_certificate, certificate)
            self.assertEqual(configuration.source_identity[2], fingerprint)
            payload_text = "".join(
                path.read_text()
                for path in (
                    ROOT / "providers/carla-viss-kuksa/releases"
                ).glob("*/*.json")
            )
            self.assertNotIn("unit-a", payload_text)
            integration_data = json.loads(integration.read_text())
            integration_data["selectedSource"]["clientCertificateSha256"] = "b" * 64
            integration.write_text(json.dumps(integration_data))
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                runtime._load_viss_configuration(
                    environment, require_mutual_tls=True
                )


class VdpAdvisoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.viss = FakeViss()
        self.kuksa = FakeKuksa()
        self.policy = AdvisoryPolicy(self.viss, self.kuksa)
        self.brake = Caller("BRAKE_HEALTH", "3.0.0")
        self.brake_path = "Vehicle.OEM.BrakeHealth.Advisory.Request"
        self.brake_status = "Vehicle.OEM.BrakeHealth.Advisory.GatewayStatus"

    def test_brake_and_tire_requests_forward_only_to_the_exact_gateway_paths(self) -> None:
        brake = self.policy.handle_request(
            self.brake, self.brake_path, request(), NOW, 10.0
        )
        self.assertTrue(brake.accepted)
        self.assertTrue(brake.forwarded)
        self.assertFalse(brake.application_success)
        tire_request = request(
            service_version="1.0.0",
            request_id="123e4567-e89b-42d3-a456-426614174002",
            recommendation="TIRE_INSPECTION_RECOMMENDED",
            reason="PREDICTED_TIRE_WEAR",
        )
        tire = self.policy.handle_request(
            Caller("TIRE_HEALTH", "1.0.0"),
            "Vehicle.OEM.TireHealth.Advisory.Request",
            tire_request,
            NOW,
            10.0,
        )
        self.assertTrue(tire.accepted)
        self.assertEqual(
            [item[0] for item in self.viss.sets],
            [
                self.brake_path,
                "Vehicle.OEM.TireHealth.Advisory.Request",
            ],
        )

    def test_unknown_caller_path_provider_authority_and_motion_write_are_denied(self) -> None:
        cases = (
            (
                Caller("TIRE_HEALTH", "1.0.0"),
                self.brake_path,
                "UNAUTHORIZED_SOURCE",
            ),
            (
                Caller("BRAKE_HEALTH", "3.0.0", "PROVIDER"),
                self.brake_path,
                "UNAUTHORIZED_SOURCE",
            ),
            (
                self.brake,
                "Vehicle.Chassis.Brake.PedalPosition",
                "UNAUTHORIZED_PATH",
            ),
        )
        for caller, path, reason in cases:
            with self.subTest(reason=reason, path=path):
                decision = self.policy.handle_request(
                    caller, path, request(), NOW, 10.0
                )
                self.assertFalse(decision.accepted)
                self.assertEqual(decision.reason, reason)
        self.assertEqual(self.viss.sets, [])

    def test_schema_value_canonical_freshness_and_lease_are_enforced(self) -> None:
        noncanonical = json.dumps(json.loads(request()), indent=2)
        stale = request(issued_at=NOW - dt.timedelta(seconds=3))
        long_lease = request(expires_at=NOW + dt.timedelta(seconds=31))
        wrong_value = request(recommendation="TIRE_INSPECTION_RECOMMENDED")
        for raw, reason in (
            (noncanonical, "INVALID_SCHEMA"),
            ("x" * 2049, "INVALID_SCHEMA"),
            (stale, "STALE_REQUEST"),
            (long_lease, "STALE_REQUEST"),
            (wrong_value, "INVALID_VALUE"),
        ):
            with self.subTest(reason=reason):
                decision = self.policy.handle_request(
                    self.brake, self.brake_path, raw, NOW, 10.0
                )
                self.assertEqual(decision.reason, reason)

    def test_explicit_clear_is_schema_bound_and_rate_limited(self) -> None:
        self.assertTrue(
            self.policy.handle_request(
                self.brake, self.brake_path, request(), NOW, 10.0
            ).accepted
        )
        clear_now = NOW + dt.timedelta(seconds=2)
        clear = request(
            sequence=2,
            operation="CLEAR",
            recommendation=None,
            reason="CONDITION_CLEARED",
            request_id="123e4567-e89b-42d3-a456-426614174005",
            issued_at=clear_now,
        )
        accepted = self.policy.handle_request(
            self.brake, self.brake_path, clear, clear_now, 12.0
        )
        self.assertTrue(accepted.accepted)
        invalid = json.loads(clear)
        invalid["recommendation"] = "INSPECTION_RECOMMENDED"
        invalid["sequence"] = 3
        invalid["requestId"] = "123e4567-e89b-42d3-a456-426614174006"
        denied = self.policy.handle_request(
            self.brake,
            self.brake_path,
            canonical_json(invalid),
            clear_now,
            14.0,
        )
        self.assertEqual(denied.reason, "INVALID_SCHEMA")

    def test_replay_sequence_and_rate_bounds_are_deterministic(self) -> None:
        first = request()
        self.assertTrue(
            self.policy.handle_request(
                self.brake, self.brake_path, first, NOW, 10.0
            ).accepted
        )
        duplicate = self.policy.handle_request(
            self.brake, self.brake_path, first, NOW, 10.1
        )
        self.assertEqual(duplicate.reason, "IDEMPOTENT_NO_NEW_EFFECT")
        conflicting_value = json.loads(first)
        conflicting_value["decisionId"] = "other"
        conflicting = self.policy.handle_request(
            self.brake,
            self.brake_path,
            canonical_json(conflicting_value),
            NOW,
            10.2,
        )
        self.assertEqual(conflicting.reason, "REPLAY_DETECTED")
        too_fast = self.policy.handle_request(
            self.brake,
            self.brake_path,
            request(
                sequence=2,
                request_id="123e4567-e89b-42d3-a456-426614174003",
            ),
            NOW,
            11.0,
        )
        self.assertEqual(too_fast.reason, "RATE_LIMITED")
        accepted = self.policy.handle_request(
            self.brake,
            self.brake_path,
            request(
                sequence=2,
                request_id="123e4567-e89b-42d3-a456-426614174003",
            ),
            NOW,
            20.0,
        )
        self.assertTrue(accepted.accepted)
        rollback = self.policy.handle_request(
            self.brake,
            self.brake_path,
            request(
                request_id="123e4567-e89b-42d3-a456-426614174004",
            ),
            NOW,
            30.0,
        )
        self.assertEqual(rollback.reason, "SEQUENCE_ROLLBACK")

    def test_only_correlated_gateway_status_can_claim_application_success(self) -> None:
        self.policy.handle_request(
            self.brake, self.brake_path, request(), NOW, 10.0
        )
        unknown = self.policy.handle_gateway_status(
            self.brake_status,
            status(request_id="123e4567-e89b-42d3-a456-426614174099"),
        )
        self.assertFalse(unknown.accepted)
        self.assertEqual(self.kuksa.statuses, [])
        received = self.policy.handle_gateway_status(
            self.brake_status, status("RECEIVED")
        )
        self.assertTrue(received.accepted)
        self.assertFalse(received.application_success)
        applied = self.policy.handle_gateway_status(self.brake_status, status())
        self.assertTrue(applied.accepted)
        self.assertTrue(applied.application_success)
        self.assertTrue(
            all(item[0] == self.brake_status for item in self.kuksa.statuses)
        )

    def test_replay_and_pending_state_are_bounded(self) -> None:
        for index in range(1030):
            current = NOW + dt.timedelta(seconds=10 * index)
            value = json.loads(
                request(
                    request_id=f"123e4567-e89b-42d3-a456-{index:012x}",
                    issued_at=current,
                )
            )
            value["producerEpoch"] = f"123e4567-e89b-42d3-a456-{index:012x}"
            decision = self.policy.handle_request(
                self.brake,
                self.brake_path,
                canonical_json(value),
                current,
                float(10 * index),
            )
            self.assertTrue(decision.accepted)
        self.assertLessEqual(len(self.policy._pending), 1024)
        self.assertLessEqual(len(self.policy._latest_sequence), 1024)
        self.assertLessEqual(
            len(self.policy._replay["BRAKE_HEALTH_ADVISORY"]), 512
        )


class VdpSourcePrebuildTests(unittest.TestCase):
    def test_unknown_release_and_invalid_revision_are_forbidden_inputs(self) -> None:
        with self.assertRaisesRegex(vdp_family.PrebuildError, "unsupported"):
            vdp_family.compose("4.0.0", "1" * 40)
        with self.assertRaisesRegex(vdp_family.PrebuildError, "full Git"):
            vdp_family.compose("1.0.0", "main")

    def test_each_source_prebuild_is_deterministic_and_release_minimal(self) -> None:
        revision = "1" * 40
        digests = set()
        for version in vdp_family.VERSIONS:
            with self.subTest(version=version):
                first, metadata = vdp_family.compose(version, revision)
                second, _ = vdp_family.compose(version, revision)
                self.assertEqual(first, second)
                self.assertTrue(metadata["notDeployable"])
                digests.add(hashlib.sha256(first).hexdigest())
                with tarfile.open(fileobj=io.BytesIO(first), mode="r:") as archive:
                    names = set(archive.getnames())
                    for member in archive:
                        if member.isfile() and member.name.endswith(".py"):
                            source = archive.extractfile(member)
                            self.assertIsNotNone(source)
                            compile(source.read(), member.name, "exec")
                advisory = "python/carla_viss_kuksa_provider/advisory.py"
                self.assertEqual(advisory in names, version == "3.0.0")
                release_modules = {
                    name
                    for name in names
                    if name.startswith(
                        "python/carla_viss_kuksa_provider/releases/v"
                    )
                }
                self.assertEqual(len(release_modules), 1)
        self.assertEqual(len(digests), 3)

    def test_source_prebuild_directory_round_trip_and_tamper_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            output = Path(directory) / "vdp-2.0.0"
            vdp_family.prepare(output, "2.0.0", "2" * 40)
            vdp_family.validate_directory(output, "2.0.0")
            summary = json.loads((output / "prebuild.json").read_text())
            summary["sourcePrebuildSha256"] = "0" * 64
            (output / "prebuild.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(vdp_family.PrebuildError, "digest"):
                vdp_family.validate_directory(output, "2.0.0")

    def test_prebuild_runtime_imports_only_its_build_selected_profile(self) -> None:
        archive_bytes, _ = vdp_family.compose("2.0.0", "3" * 40)
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
                archive.extractall(root)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    (
                        "import sys; from pathlib import Path; "
                        "from carla_viss_kuksa_provider import runtime; "
                        "config = runtime.load_payload_configuration(Path(sys.argv[1])); "
                        "print(config.semantic_version); print(len(config.signals))"
                    ),
                    str(root / "config/provider.json"),
                ],
                check=True,
                capture_output=True,
                text=True,
                env={
                    "PYTHONPATH": str(root / "python"),
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            self.assertEqual(result.stdout.splitlines(), ["2.0.0", "15"])

    def test_historical_provider_path_remains_pinned_and_distinct(self) -> None:
        builder = (FOTA / "build-provider-component").read_text()
        configuration = json.loads((FOTA / "config.yaml").read_text())
        self.assertIn(
            'RELEASE_SOURCE_REVISION = "e972d2bd7f14e27646bb5d7c10c7186ecdecfa9f"',
            builder,
        )
        self.assertIn("accepted_tree(source_prefix)", builder)
        self.assertEqual(configuration["items"][0]["version"], "0.2.0")
        self.assertEqual(
            configuration["items"][0]["images"][0]["path"],
            "provider-0.2.0-arm64.tar",
        )

    def test_no_dynamic_provider_auth_store_quota_or_secret_input_is_added(self) -> None:
        owned = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for root in (
                ROOT / "providers/carla-viss-kuksa",
                ROOT / "packaging/fota",
            )
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        self.assertNotIn("GetPermissions", owned)
        self.assertNotIn("AOS" + "_SECRET", owned)
        self.assertNotIn("application.db", owned)
        self.assertNotIn("telemetry.log", owned)


if __name__ == "__main__":
    unittest.main()
