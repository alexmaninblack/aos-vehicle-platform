# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Transport-independent, bounded image admission and delivery.

An authenticated OEM adapter must supply selection and transport authority.
This module validates data, not identities. It opens no files/devices/listeners,
decodes no pixels, starts no worker and has no vehicle-control or Cloud API.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import re
import threading
import time
from typing import Callable
from uuid import UUID

PROFILE = "front-rgb-jpeg-720p-v1"
CLOCK = "CARLA_WORLD_SNAPSHOT_FRAME_MATCH"
MAX_JPEG_BYTES = 4 * 1024 * 1024
MAX_RETAINED_FRAMES = 2
MIN_PAIR_NS = 80_000_000
MAX_PAIR_NS = 120_000_000
MAX_SENSOR_OFFSET_NS = 75_000_000
MAX_LOCAL_AGE_NS = 1_000_000_000
MAX_INTEGER = 2**63 - 1
METADATA_FIELDS = frozenset((
    "schemaVersion", "profile", "sourceId", "sourceEpoch", "cameraId", "frame",
    "simulationTimeNs", "sensorSimulationTimeNs", "clock", "calibrationId",
    "encoding", "width", "height", "payloadBytes", "sha256",
))


class CameraError(ValueError):
    """Only fixed non-secret reason codes leave the component."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CameraError(code)


def integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_INTEGER


def uuid(value: object) -> bool:
    try:
        return type(value) is str and str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def digest(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class SourceBinding:
    """Volatile trusted OEM selection, not a credential or service-supplied claim."""
    source_id: str
    source_epoch: str
    calibration_id: str
    camera_id: str = "front"

    def __post_init__(self) -> None:
        require(uuid(self.source_id) and uuid(self.source_epoch), "BINDING_ID_INVALID")
        require(digest(self.calibration_id), "CALIBRATION_ID_INVALID")
        require(self.camera_id == "front", "CAMERA_PROFILE_INVALID")


@dataclass(frozen=True)
class FrameInfo:
    source_id: str
    source_epoch: str
    camera_id: str
    calibration_id: str
    frame: int
    simulation_time_ns: int
    sensor_simulation_time_ns: int
    sha256: str
    profile: str = PROFILE
    clock: str = CLOCK
    encoding: str = "JPEG"
    width: int = 1280
    height: int = 720


@dataclass(frozen=True)
class Frame:
    info: FrameInfo
    jpeg: bytes
    received_ns: int


def jpeg_header(payload: bytes) -> None:
    """Check bounded JPEG SOF dimensions before any downstream pixel decode.

    This is not a full compressed-image validity check. The isolated consumer
    still must bound and handle decoder failures independently.
    """
    require(payload[:2] == b"\xff\xd8" and payload[-2:] == b"\xff\xd9", "JPEG_HEADER_INVALID")
    offset = 2
    while offset + 4 <= len(payload):
        require(payload[offset] == 255, "JPEG_MARKER_INVALID")
        marker = payload[offset + 1]
        offset += 2
        while marker == 255:
            require(offset < len(payload), "JPEG_HEADER_INVALID")
            marker = payload[offset]
            offset += 1
        require(marker not in (0, 0xD8, 0xD9, 0xDA) and offset + 2 <= len(payload), "JPEG_SOF_MISSING")
        size = int.from_bytes(payload[offset:offset + 2], "big")
        require(size >= 2 and offset + size <= len(payload), "JPEG_SEGMENT_INVALID")
        if marker in (0xC0, 0xC1, 0xC2):
            require(size >= 8 and payload[offset + 2] == 8, "JPEG_SOF_INVALID")
            height = int.from_bytes(payload[offset + 3:offset + 5], "big")
            width = int.from_bytes(payload[offset + 5:offset + 7], "big")
            require((width, height, payload[offset + 7]) == (1280, 720, 3), "JPEG_DIMENSIONS_INVALID")
            return
        offset += size
    raise CameraError("JPEG_SOF_MISSING")


def validate(metadata: dict, payload: bytes, binding: SourceBinding) -> FrameInfo:
    require(type(metadata) is dict and metadata.keys() == METADATA_FIELDS, "METADATA_FIELDS_INVALID")
    require(type(metadata["schemaVersion"]) is int and metadata["schemaVersion"] == 1, "METADATA_SCHEMA_INVALID")
    require((metadata["profile"], metadata["cameraId"], metadata["encoding"], metadata["clock"]) ==
            (PROFILE, "front", "JPEG", CLOCK), "CAMERA_PROFILE_INVALID")
    require((metadata["sourceId"], metadata["sourceEpoch"], metadata["calibrationId"], metadata["cameraId"]) ==
            (binding.source_id, binding.source_epoch, binding.calibration_id, binding.camera_id), "SOURCE_BINDING_MISMATCH")
    require(all(integer(metadata[k]) for k in ("frame", "simulationTimeNs", "sensorSimulationTimeNs", "payloadBytes", "width", "height")), "FRAME_NUMBER_INVALID")
    require((metadata["width"], metadata["height"]) == (1280, 720), "FRAME_DIMENSIONS_INVALID")
    require(abs(metadata["sensorSimulationTimeNs"] - metadata["simulationTimeNs"]) <= MAX_SENSOR_OFFSET_NS, "FRAME_CLOCK_MISMATCH")
    require(type(payload) is bytes and 0 < len(payload) <= MAX_JPEG_BYTES and metadata["payloadBytes"] == len(payload), "FRAME_SIZE_INVALID")
    require(digest(metadata["sha256"]) and hashlib.sha256(payload).hexdigest() == metadata["sha256"], "FRAME_DIGEST_INVALID")
    jpeg_header(payload)
    return FrameInfo(binding.source_id, binding.source_epoch, binding.camera_id, binding.calibration_id,
                     metadata["frame"], metadata["simulationTimeNs"], metadata["sensorSimulationTimeNs"], metadata["sha256"])


class CameraAccess:
    """One selected camera and one Perception delivery cursor, memory only.

    The producer never waits for inference. Rejected input does not refresh
    delivery age. Disconnect clears pixels but retains the current epoch's
    high-water marks, so reconnect cannot replay an old frame. A process restart
    requires a freshly authenticated upstream session/epoch before live use.
    """
    def __init__(self, clock: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock = clock
        self._clock_high = -1
        self._lock = threading.RLock()
        self._binding: SourceBinding | None = None
        self._connected = False
        self._frames: deque[Frame] = deque(maxlen=MAX_RETAINED_FRAMES)
        self._high_frame = self._high_time = self._delivered = -1
        self._counts = dict(admitted=0, rejected=0, supersededPairs=0, selections=0, disconnects=0)
        self._last_rejection: str | None = None

    def _now(self) -> int:
        now = self._clock()
        require(integer(now) and now >= self._clock_high, "RECEIVER_CLOCK_INVALID")
        self._clock_high = now
        return now

    def select(self, binding: SourceBinding) -> None:
        require(type(binding) is SourceBinding, "TRUSTED_BINDING_REQUIRED")
        with self._lock:
            if binding != self._binding:
                self._frames.clear()
                self._high_frame = self._high_time = self._delivered = -1
                self._binding = binding
                self._counts["selections"] += 1
            self._connected = True

    def disconnect(self) -> None:
        with self._lock:
            self._connected = False
            self._frames.clear()
            self._counts["disconnects"] += 1

    def _pair(self) -> bool:
        return len(self._frames) == 2 and MIN_PAIR_NS <= (
            self._frames[1].info.simulation_time_ns - self._frames[0].info.simulation_time_ns
        ) <= MAX_PAIR_NS

    def admit(self, metadata: dict, payload: bytes) -> None:
        with self._lock:
            try:
                require(self._connected and self._binding is not None, "SOURCE_UNAVAILABLE")
                info = validate(metadata, payload, self._binding)
                require(info.frame > self._high_frame and info.simulation_time_ns > self._high_time, "FRAME_REPLAY_OR_REGRESSION")
                now = self._now()
                if self._pair() and self._frames[-1].info.frame > self._delivered:
                    self._counts["supersededPairs"] += 1
                self._frames.append(Frame(info, payload, now))
                self._high_frame, self._high_time = info.frame, info.simulation_time_ns
                self._counts["admitted"] += 1
            except CameraError as error:
                self._counts["rejected"] += 1
                self._last_rejection = str(error)
                raise

    def _state(self, now: int) -> tuple[str, str]:
        if not self._connected:
            return "UNAVAILABLE", "SOURCE_UNAVAILABLE"
        if not self._frames:
            return "WARMING", "WAITING_FRAME"
        # Both members must be within the local retention age; never refresh
        # an old member merely because a newer image arrived.
        if now - self._frames[0].received_ns > MAX_LOCAL_AGE_NS:
            return "STALE", "LOCAL_DELIVERY_STALE"
        if not self._pair():
            return "WARMING", "WAITING_PAIR" if len(self._frames) == 1 else "PAIR_INTERVAL_INVALID"
        return "AVAILABLE", "WORLD_FRAME_PAIR_AVAILABLE"

    def take_pair(self) -> tuple[Frame, Frame] | None:
        with self._lock:
            if self._state(self._now())[0] != "AVAILABLE" or self._frames[-1].info.frame <= self._delivered:
                return None
            self._delivered = self._frames[-1].info.frame
            return self._frames[0], self._frames[1]

    def status(self) -> dict:
        with self._lock:
            state, reason = self._state(self._now())
            return dict(deliveryState=state, reason=reason, retainedFrames=len(self._frames),
                        retainedJpegBytes=sum(len(f.jpeg) for f in self._frames),
                        counters=dict(self._counts), lastRejection=self._last_rejection,
                        captureFreshness="NOT_QUALIFIED", motionAuthority=False)
