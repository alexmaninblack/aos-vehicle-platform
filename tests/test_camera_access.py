# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Offline Camera Access obligations; no guest, network, device or pixel decode."""
from dataclasses import FrozenInstanceError, replace
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "camera-access/src"))
from aos_camera_access import CameraAccess, CameraError, SourceBinding
from aos_camera_access import core


class Clock:
    def __init__(self):
        self.now = 2_000_000_000

    def __call__(self):
        return self.now


def jpeg(width=1280, height=720, extra=b""):
    # Only a synthetic SOF envelope: these tests do not claim a pixel decode.
    return b"\xff\xd8\xff\xc0" + struct.pack("!HBHHB", 8, 8, height, width, 3) + extra + b"\xff\xd9"


class CameraAccessTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.camera = CameraAccess(self.clock)
        self.binding = SourceBinding("00000000-0000-0000-0000-000000000001",
                                     "00000000-0000-0000-0000-000000000002", "a" * 64)

    def metadata(self, frame=10, stamp=1_000_000_000, raw=None, payload=None, binding=None):
        b = binding or self.binding
        p = jpeg() if payload is None else payload
        return dict(schemaVersion=1, profile=core.PROFILE, sourceId=b.source_id, sourceEpoch=b.source_epoch,
                    cameraId=b.camera_id, frame=frame, simulationTimeNs=stamp,
                    sensorSimulationTimeNs=stamp if raw is None else raw, clock=core.CLOCK,
                    calibrationId=b.calibration_id, encoding="JPEG", width=1280, height=720,
                    payloadBytes=len(p), sha256=hashlib.sha256(p).hexdigest())

    def push(self, frame=10, stamp=1_000_000_000, **kwargs):
        p = kwargs.pop("payload", jpeg())
        self.camera.admit(self.metadata(frame, stamp, payload=p, **kwargs), p)

    def pair(self):
        self.camera.select(self.binding)
        self.push()
        self.push(12, 1_100_000_000)

    def test_empty_selection_and_identical_repeat(self):
        self.assertEqual("UNAVAILABLE", self.camera.status()["deliveryState"])
        self.assertIsNone(self.camera.take_pair())
        self.camera.select(self.binding)
        self.assertEqual("WARMING", self.camera.status()["deliveryState"])
        self.push()
        self.camera.select(self.binding)
        self.push(12, 1_100_000_000)
        a, b = self.camera.take_pair()
        self.assertEqual((10, 12), (a.info.frame, b.info.frame))
        self.assertEqual(1, self.camera.status()["counters"]["selections"])
        self.assertIsNone(self.camera.take_pair())

    def test_newest_pair_overwrites_without_a_backlog(self):
        self.pair()
        for n in range(2, 1000):
            self.push(10 + 2*n, 1_000_000_000 + 100_000_000*n)
        pair = self.camera.take_pair()
        self.assertEqual((2006, 2008), tuple(f.info.frame for f in pair))
        state = self.camera.status()
        self.assertEqual(2, state["retainedFrames"])
        self.assertEqual(2*len(jpeg()), state["retainedJpegBytes"])
        self.assertEqual(998, state["counters"]["supersededPairs"])

    def test_delivered_pair_is_not_counted_as_superseded(self):
        self.pair()
        self.camera.take_pair()
        self.push(14, 1_200_000_000)
        self.assertEqual(0, self.camera.status()["counters"]["supersededPairs"])

    def test_raw_timestamp_is_preserved_not_normalized(self):
        self.camera.select(self.binding)
        self.push(raw=1_050_000_000)
        self.push(12, 1_100_000_000)
        a, b = self.camera.take_pair()
        self.assertEqual(100_000_000, b.info.simulation_time_ns-a.info.simulation_time_ns)
        self.assertEqual(50_000_000, b.info.sensor_simulation_time_ns-a.info.sensor_simulation_time_ns)
        self.assertEqual("NOT_QUALIFIED", self.camera.status()["captureFreshness"])

    def test_real_gap_is_not_interpolated(self):
        self.camera.select(self.binding)
        self.push()
        self.push(14, 1_200_000_000)
        self.assertIsNone(self.camera.take_pair())
        self.assertEqual("PAIR_INTERVAL_INVALID", self.camera.status()["reason"])
        self.push(16, 1_300_000_000)
        self.assertEqual((14, 16), tuple(f.info.frame for f in self.camera.take_pair()))

    def test_boundary_pair_intervals(self):
        for interval in (79_999_999, 80_000_000, 120_000_000, 120_000_001):
            with self.subTest(interval=interval):
                self.setUp()
                self.camera.select(self.binding)
                self.push()
                self.push(12, 1_000_000_000+interval)
                self.assertEqual(80_000_000 <= interval <= 120_000_000, self.camera.take_pair() is not None)

    def test_stale_delivery_does_not_refresh_capture_time(self):
        self.pair()
        self.clock.now += core.MAX_LOCAL_AGE_NS + 1
        self.assertIsNone(self.camera.take_pair())
        self.assertEqual("STALE", self.camera.status()["deliveryState"])
        with self.assertRaisesRegex(CameraError, "REPLAY"):
            self.push(12, 1_100_000_000)
        self.assertEqual("STALE", self.camera.status()["deliveryState"])

    def test_old_member_cannot_be_renewed_by_newer_arrival(self):
        self.camera.select(self.binding)
        self.push()
        self.clock.now += core.MAX_LOCAL_AGE_NS + 1
        self.push(12, 1_100_000_000)
        self.assertIsNone(self.camera.take_pair())
        self.push(14, 1_200_000_000)
        self.assertIsNotNone(self.camera.take_pair())

    def test_disconnect_clears_pixels_but_reconnect_rejects_replay(self):
        self.pair()
        self.camera.disconnect()
        self.assertEqual(("UNAVAILABLE", 0), (self.camera.status()["deliveryState"], self.camera.status()["retainedJpegBytes"]))
        with self.assertRaisesRegex(CameraError, "UNAVAILABLE"):
            self.push(14, 1_200_000_000)
        self.camera.select(self.binding)
        with self.assertRaisesRegex(CameraError, "REPLAY"):
            self.push(12, 1_100_000_000)
        self.push(14, 1_200_000_000)
        self.push(16, 1_300_000_000)
        self.assertIsNotNone(self.camera.take_pair())

    def test_source_epoch_or_calibration_change_flushes_old_frames(self):
        for changed in (replace(self.binding, source_id="00000000-0000-0000-0000-000000000003"),
                        replace(self.binding, source_epoch="00000000-0000-0000-0000-000000000003"),
                        replace(self.binding, calibration_id="b"*64)):
            with self.subTest(changed=changed):
                self.setUp()
                self.pair()
                self.camera.select(changed)
                self.assertEqual(0, self.camera.status()["retainedFrames"])
                with self.assertRaisesRegex(CameraError, "BINDING"):
                    self.push()
                self.push(1, 100_000_000, binding=changed)
                self.push(3, 200_000_000, binding=changed)
                self.assertEqual(changed.source_epoch, self.camera.take_pair()[0].info.source_epoch)

    def test_foreign_or_malformed_metadata_cannot_refresh_a_good_frame(self):
        self.camera.select(self.binding)
        self.push()
        changes = (("schemaVersion", True), ("frame", True), ("frame", -1),
                   ("simulationTimeNs", float("nan")), ("sensorSimulationTimeNs", 2_000_000_000),
                   ("cameraId", "rear"), ("profile", "foreign"), ("sourceEpoch", "foreign"),
                   ("clock", "ARRIVAL_TIME"), ("width", 640), ("payloadBytes", 0), ("sha256", "0"*64))
        for key, value in changes:
            with self.subTest(field=key):
                m = self.metadata(12, 1_100_000_000)
                m[key] = value
                with self.assertRaises(CameraError):
                    self.camera.admit(m, jpeg())
                self.assertEqual(1, self.camera.status()["retainedFrames"])
        for m in ({}, dict(self.metadata(), unexpected="field")):
            with self.assertRaisesRegex(CameraError, "FIELDS"):
                self.camera.admit(m, jpeg())

    def test_frame_or_time_replay_regression(self):
        self.pair()
        for frame, stamp in ((12, 1_200_000_000), (11, 1_200_000_000), (14, 1_100_000_000), (14, 1_000_000_000)):
            with self.assertRaisesRegex(CameraError, "REPLAY"):
                self.push(frame, stamp)

    def test_image_bound_and_dimensions_are_checked_before_any_decode(self):
        self.camera.select(self.binding)
        for p in (b"", b"not-jpeg", jpeg(40000, 40000), jpeg(extra=b"x"*core.MAX_JPEG_BYTES), jpeg()[:-1]):
            with self.assertRaises(CameraError):
                self.push(payload=p)
        with self.assertRaisesRegex(CameraError, "SIZE"):
            self.camera.admit(self.metadata(), bytearray(jpeg()))

    def test_delivered_frame_and_selection_are_immutable(self):
        self.pair()
        a, _ = self.camera.take_pair()
        with self.assertRaises(FrozenInstanceError):
            a.info.frame = 100
        with self.assertRaises(FrozenInstanceError):
            a.jpeg = b"replaced"
        self.assertEqual(jpeg(), a.jpeg)

    def test_invalid_binding_and_receiver_clock_fail_closed(self):
        with self.assertRaisesRegex(CameraError, "BINDING"):
            SourceBinding("foreign", self.binding.source_epoch, self.binding.calibration_id)
        with self.assertRaisesRegex(CameraError, "TRUSTED"):
            self.camera.select({})
        self.pair()
        self.clock.now -= 1
        with self.assertRaisesRegex(CameraError, "CLOCK"):
            self.camera.take_pair()

    def test_public_status_has_no_source_identifiers_or_payload(self):
        self.pair()
        status = self.camera.status()
        encoded = json.dumps(status)
        for private in (self.binding.source_id, self.binding.source_epoch, self.binding.calibration_id):
            self.assertNotIn(private, encoded)
        self.assertFalse(status["motionAuthority"])

    def test_machine_profile_matches_implementation(self):
        p = json.loads((ROOT/"contracts/camera-access/profile.json").read_bytes())
        self.assertEqual(core.METADATA_FIELDS, frozenset(p["metadataFields"]))
        for key, expected in (("profile", core.PROFILE), ("clock", core.CLOCK), ("maximumJpegBytes", core.MAX_JPEG_BYTES),
                              ("maximumRetainedFrames", core.MAX_RETAINED_FRAMES), ("minimumPairIntervalNs", core.MIN_PAIR_NS),
                              ("maximumPairIntervalNs", core.MAX_PAIR_NS), ("maximumSensorWorldOffsetNs", core.MAX_SENSOR_OFFSET_NS),
                              ("maximumLocalDeliveryAgeNs", core.MAX_LOCAL_AGE_NS)):
            self.assertEqual(expected, p[key], key)
        self.assertEqual(2*core.MAX_JPEG_BYTES, p["maximumRetainedJpegBytes"])

    def test_core_has_no_external_runtime_or_transport_dependency(self):
        tree = ast.parse((ROOT/"camera-access/src/aos_camera_access/core.py").read_bytes())
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(name.name.split(".")[0] for name in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module.split(".")[0])
        self.assertEqual({"__future__", "collections", "dataclasses", "hashlib", "re", "threading", "time", "typing", "uuid"}, imports)
        forbidden = {"open", "socket", "Popen", "Thread", "start", "system", "connect", "bind", "listen"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                self.assertNotIn(name, forbidden)
        profile = json.loads((ROOT/"contracts/camera-access/profile.json").read_bytes())
        self.assertEqual({False}, set(profile["authority"].values()))
        self.assertEqual("camera-access", profile["component"])

    def test_maximum_valid_payload_retention_is_eight_mib(self):
        self.camera.select(self.binding)
        p = jpeg(extra=b"x"*(core.MAX_JPEG_BYTES-len(jpeg())))
        for n in range(5):
            self.push(10+2*n, 1_000_000_000+100_000_000*n, payload=p)
        self.assertEqual(8*1024*1024, self.camera.status()["retainedJpegBytes"])
        self.assertEqual(2, self.camera.status()["retainedFrames"])


if __name__ == "__main__":
    unittest.main()
