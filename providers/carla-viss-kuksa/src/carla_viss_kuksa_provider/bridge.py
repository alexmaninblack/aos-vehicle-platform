# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Dependency-free VISS parsing, validation, and stale-state handling."""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol


@dataclass(frozen=True)
class SignalValue:
    value: float | int
    timestamp: dt.datetime


@dataclass(frozen=True)
class SignalSpec:
    path: str
    convert: Callable[[str], float | int]

    @property
    def relative_path(self) -> str:
        return self.path.removeprefix("Vehicle.")


@dataclass(frozen=True)
class Snapshot:
    values: Mapping[str, SignalValue | None]
    invalid_paths: tuple[str, ...]
    complete: bool = False
    source_timestamp: dt.datetime | None = None


class TelemetrySink(Protocol):
    def publish(self, values: Mapping[str, SignalValue | None]) -> None:
        """Atomically publish current values or explicit unavailability."""


def finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("value must be finite")
    return value


def nonnegative_float(raw: str) -> float:
    value = finite_float(raw)
    if value < 0:
        raise ValueError("speed must be non-negative")
    return value


def uint8_percent(raw: str) -> int:
    if not raw or any(character not in "0123456789" for character in raw):
        raise ValueError("percentage must be an unsigned decimal integer")
    value = int(raw, 10)
    if not 0 <= value <= 100:
        raise ValueError("percentage must be between 0 and 100")
    return value


SIGNALS = (
    SignalSpec("Vehicle.Speed", nonnegative_float),
    SignalSpec("Vehicle.Acceleration.Longitudinal", finite_float),
    SignalSpec("Vehicle.Acceleration.Lateral", finite_float),
    SignalSpec("Vehicle.Acceleration.Vertical", finite_float),
    SignalSpec("Vehicle.Chassis.Accelerator.PedalPosition", uint8_percent),
    SignalSpec("Vehicle.Chassis.Brake.PedalPosition", uint8_percent),
    SignalSpec("Vehicle.Chassis.Axle.Row1.SteeringAngle", finite_float),
)
SIGNAL_BY_PATH = {signal.path: signal for signal in SIGNALS}


def subscription_request(
    request_id: str,
    period_ms: int,
    signals: tuple[SignalSpec, ...] = SIGNALS,
) -> str:
    if not request_id:
        raise ValueError("request ID must not be empty")
    if not 50 <= period_ms <= 60_000:
        raise ValueError("subscription period must be between 50 and 60000 ms")
    request = {
        "action": "subscribe",
        "path": "Vehicle",
        "filter": [
            {
                "variant": "paths",
                "parameter": [signal.relative_path for signal in signals],
            },
            {"variant": "timebased", "parameter": {"period": str(period_ms)}},
        ],
        "requestId": request_id,
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def parse_subscribe_response(raw_message: str, request_id: str) -> str:
    message = _message_object(raw_message)
    if message.get("action") != "subscribe" or message.get("requestId") != request_id:
        raise ValueError("unexpected VISS subscribe response")
    if "error" in message:
        raise ValueError("VISS subscription was rejected")
    subscription_id = message.get("subscriptionId")
    if not isinstance(subscription_id, str) or not subscription_id:
        raise ValueError("VISS subscribe response has no subscription ID")
    return subscription_id


def parse_snapshot(
    raw_message: str,
    subscription_id: str,
    signals: tuple[SignalSpec, ...] = SIGNALS,
) -> Snapshot:
    message = _message_object(raw_message)
    if message.get("action") != "subscription":
        raise ValueError("message is not a VISS subscription event")
    if message.get("subscriptionId") != subscription_id:
        raise ValueError("VISS subscription ID does not match")
    if "error" in message:
        raise ValueError("VISS subscription event contains an error")

    data = message.get("data")
    if isinstance(data, dict):
        points = [data]
    elif isinstance(data, list):
        points = data
    else:
        raise ValueError("VISS subscription event has invalid data")

    signal_by_path = {signal.path: signal for signal in signals}
    selected: dict[str, SignalValue | None] = {
        signal.path: None for signal in signals
    }
    invalid: list[str] = []
    seen: set[str] = set()
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("VISS data point must be an object")
        path = point.get("path")
        if path not in signal_by_path:
            continue
        if path in seen:
            raise ValueError(f"duplicate VISS data point: {path}")
        seen.add(path)
        try:
            selected[path] = _parse_data_point(signal_by_path[path], point)
        except (TypeError, ValueError):
            invalid.append(path)
            selected[path] = None
    timestamps = {
        item.timestamp for item in selected.values() if item is not None
    }
    complete = not invalid and len(seen) == len(signals) and len(timestamps) == 1
    source_timestamp = next(iter(timestamps)) if complete else None
    return Snapshot(selected, tuple(sorted(invalid)), complete, source_timestamp)


def _message_object(raw_message: str) -> dict[str, object]:
    try:
        message = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("message is not valid VISS JSON") from error
    if not isinstance(message, dict):
        raise ValueError("VISS message must be an object")
    return message


def _parse_data_point(signal: SignalSpec, point: Mapping[str, object]) -> SignalValue:
    datapoint = point.get("dp")
    if not isinstance(datapoint, dict):
        raise ValueError("VISS data point has no dp object")
    raw_value = datapoint.get("value")
    raw_timestamp = datapoint.get("ts")
    if not isinstance(raw_value, str) or not isinstance(raw_timestamp, str):
        raise ValueError("VISS value and timestamp must be strings")
    timestamp = _parse_timestamp(raw_timestamp)
    return SignalValue(signal.convert(raw_value), timestamp)


def _parse_timestamp(raw_timestamp: str) -> dt.datetime:
    if not raw_timestamp.endswith("Z"):
        raise ValueError("VISS timestamp must be UTC with a trailing Z")
    try:
        timestamp = dt.datetime.fromisoformat(raw_timestamp[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("VISS timestamp is invalid") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() != dt.timedelta(0):
        raise ValueError("VISS timestamp must be UTC")
    return timestamp


class BridgeState:
    """Publish validated frames and clear retained KUKSA values when stale."""

    def __init__(
        self,
        sink: TelemetrySink,
        freshness_timeout_seconds: float,
        monotonic: Callable[[], float],
        signals: tuple[SignalSpec, ...] = SIGNALS,
        require_complete_frames: bool = False,
    ) -> None:
        if freshness_timeout_seconds <= 0:
            raise ValueError("freshness timeout must be positive")
        self._sink = sink
        self._freshness_timeout = freshness_timeout_seconds
        self._monotonic = monotonic
        self._signals = signals
        self._require_complete_frames = require_complete_frames
        self._last_publish_at: float | None = None
        self._last_source_timestamp: dt.datetime | None = None
        # Clear any value retained by KUKSA before the first healthy CARLA
        # frame. This also makes a provider restart fail safe when CARLA is
        # already unavailable.
        self._unavailable = False

    def handle_message(self, raw_message: str, subscription_id: str) -> Snapshot:
        snapshot = parse_snapshot(raw_message, subscription_id, self._signals)
        if self._require_complete_frames:
            if not snapshot.complete or snapshot.source_timestamp is None:
                self.mark_unavailable()
                return snapshot
            if (
                self._last_source_timestamp is not None
                and snapshot.source_timestamp <= self._last_source_timestamp
            ):
                self.mark_unavailable()
                raise ValueError("VISS source frame is not monotonic")
        self._sink.publish(snapshot.values)
        self._last_publish_at = self._monotonic()
        self._last_source_timestamp = snapshot.source_timestamp
        self._unavailable = False
        return snapshot

    def tick(self) -> bool:
        if self._unavailable or self._last_publish_at is None:
            return False
        if self._monotonic() - self._last_publish_at < self._freshness_timeout:
            return False
        self.mark_unavailable()
        return True

    def mark_unavailable(self) -> bool:
        if self._unavailable:
            return False
        self._sink.publish({signal.path: None for signal in self._signals})
        self._unavailable = True
        return True
