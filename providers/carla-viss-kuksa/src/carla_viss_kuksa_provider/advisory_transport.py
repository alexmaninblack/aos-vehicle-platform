# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Fixed two-endpoint advisory transport on the existing selected VISS session.

The only worker observes current KUKSA actuator targets. It never opens VISS,
publishes status, changes credentials, or queues telemetry/history. All VISS
and status side effects stay on the provider's existing main loop.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
import uuid

from .advisory import AdvisoryPolicy, Caller, ENDPOINTS, ENDPOINT_BY_STATUS, MAX_REQUEST_BYTES

LOG = logging.getLogger("carla-viss-kuksa-provider")
READINESS_PATHS = tuple(path.removesuffix("Request") + "Readiness" for path in ENDPOINTS)
AVAILABILITY_PATHS = tuple(path.removesuffix("Request") + "Availability" for path in ENDPOINTS)


def producer_ready(raw: str | None, now: dt.datetime) -> bool:
    """Strict current observation, never a package/version inference."""
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > 256:
        return False
    try:
        value = json.loads(raw)
        if (not isinstance(value, dict) or set(value) != {"schemaVersion", "ready", "observedAt"}
                or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
                or type(value["ready"]) is not bool or not isinstance(value["observedAt"], str)
                or not value["observedAt"].endswith("Z")
                or json.dumps(value, separators=(",", ":"), sort_keys=True) != raw):
            return False
        observed = dt.datetime.fromisoformat(value["observedAt"].removesuffix("Z") + "+00:00")
        return value["ready"] and 0 <= (now - observed).total_seconds() <= 15
    except (ValueError, TypeError, KeyError, OverflowError):
        return False


class CurrentTargets:
    """Two requests and two readiness values; no history/unbounded queue."""

    def __init__(self, client) -> None:
        self.client = client
        self.lock = threading.Lock()
        self.values: dict[str, str] = {}
        self.ready = False
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def poll(self) -> None:
        try:
            values = self.client.read_advisory_targets()
            bounded = {
                path: raw for path, raw in values.items()
                if (path in ENDPOINTS or path in READINESS_PATHS) and isinstance(raw, str)
                and 0 < len(raw.encode("utf-8")) <= MAX_REQUEST_BYTES
            }
        except Exception:
            with self.lock:
                self.values = {}
                self.ready = False
            return
        with self.lock:
            self.values = bounded
            self.ready = True

    def snapshot(self) -> tuple[bool, dict[str, str]]:
        with self.lock:
            return self.ready, dict(self.values)

    def start(self) -> None:
        def observe() -> None:
            try:
                while not self.stop.is_set():
                    self.poll()
                    self.stop.wait(0.25)
            finally:
                self.client.close()

        self.thread = threading.Thread(target=observe, name="qm-target-observer", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread is not None:
            # Every read has a two-second RPC deadline; no indefinite shutdown.
            self.thread.join(timeout=3.0)
            if self.thread.is_alive():
                raise RuntimeError("advisory target observer did not stop")


class AdvisoryTransport:
    """Multiplex bounded Set replies and status events with ordinary telemetry."""

    def __init__(self, targets: CurrentTargets, publisher, *, monotonic=time.monotonic) -> None:
        self.targets = targets
        self.monotonic = monotonic
        self.policy = AdvisoryPolicy(self, publisher)
        self.websocket = None
        self.pending: dict[str, tuple[str, float]] = {}
        self.seen_targets: dict[str, str] = {}
        self.seen_statuses: dict[str, str] = {}
        self.last_result: dict[str, str] = {}
        self.next_availability = 0.0

    @staticmethod
    def subscription(raw: str) -> str:
        request = json.loads(raw)
        paths = request["filter"][0]["parameter"]
        paths.extend(path.removeprefix("Vehicle.") for path in ENDPOINT_BY_STATUS)
        return json.dumps(request, separators=(",", ":"), sort_keys=True)

    def attach(self, websocket) -> None:
        self.websocket = websocket
        self.pending.clear()
        self.seen_statuses.clear()
        self.next_availability = 0.0

    def detach(self) -> None:
        self.websocket = None
        self.pending.clear()

    def set_value(self, path: str, canonical_value: str) -> None:
        if (path not in ENDPOINTS and path not in AVAILABILITY_PATHS) or self.websocket is None:
            raise RuntimeError("advisory VISS route unavailable")
        if any(item[0] == path for item in self.pending.values()):
            raise RuntimeError("advisory VISS response pending")
        request_id = "vdp-advisory-" + str(uuid.uuid4())
        self.pending[request_id] = (path, self.monotonic() + 2.0)
        self.websocket.send(json.dumps({
            "action": "set", "path": path, "value": canonical_value,
            "requestId": request_id,
        }, separators=(",", ":"), sort_keys=True))

    def tick(self, now_utc: dt.datetime) -> None:
        now = self.monotonic()
        for request_id, (path, deadline) in list(self.pending.items()):
            if now >= deadline:
                del self.pending[request_id]
                self._report(path, "VISS_RESPONSE_TIMEOUT")
        if self.websocket is None:
            return
        ready, values = self.targets.snapshot()
        if now >= self.next_availability:
            for source, path in zip(READINESS_PATHS, AVAILABILITY_PATHS):
                if any(item[0] == path for item in self.pending.values()):
                    continue
                self.set_value(path, json.dumps({
                    "schemaVersion": 1, "ready": ready and producer_ready(values.get(source), now_utc),
                    "observedAt": now_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                }, separators=(",", ":"), sort_keys=True))
            self.next_availability = now + 5.0
        if not ready:
            self._report("transport", "KUKSA_TARGETS_UNAVAILABLE")
            return
        self._report("transport", "KUKSA_TARGETS_READY")
        for path, raw in values.items():
            if path not in ENDPOINTS:
                continue
            if self.seen_targets.get(path) == raw:
                continue
            if any(item[0] == path for item in self.pending.values()):
                continue
            self.seen_targets[path] = raw
            endpoint = ENDPOINTS[path]
            result = self.policy.handle_request(
                Caller(endpoint.owner_service, endpoint.functional_profile),
                path, raw, now_utc, now,
            )
            self._report(path, result.reason)

    def consume(self, raw_message: str, subscription_id: str) -> bool:
        """Consume Set/status-only messages, leaving mixed telemetry visible."""
        message = json.loads(raw_message)
        if message.get("action") == "set":
            request_id = message.get("requestId")
            pending = self.pending.pop(request_id, None) if isinstance(request_id, str) else None
            if pending is not None:
                self._report(pending[0], "VISS_SET_REJECTED" if "error" in message else "VISS_SET_ACCEPTED")
            # A Set response is never a telemetry snapshot or application proof.
            return True
        if message.get("action") != "subscription" or message.get("subscriptionId") != subscription_id:
            return False
        points = message.get("data", [])
        if isinstance(points, dict):
            points = [points]
        if not isinstance(points, list):
            return False
        seen: set[str] = set()
        for point in points:
            if not isinstance(point, dict):
                continue
            path = point.get("path")
            if not isinstance(path, str) or path not in ENDPOINT_BY_STATUS or path in seen:
                continue
            seen.add(path)
            datapoint = point.get("dp")
            value = datapoint.get("value") if isinstance(datapoint, dict) else None
            if not isinstance(value, str) or self.seen_statuses.get(path) == value:
                continue
            result = self.policy.handle_gateway_status(path, value)
            if result.accepted:
                self.seen_statuses[path] = value
            self._report(path, result.reason)
        # A status-only change must not mark all 23 absent telemetry fields
        # unavailable. Mixed full snapshots still reach the telemetry parser.
        return bool(points) and all(
            isinstance(point, dict) and isinstance(point.get("path"), str)
            and point["path"] in ENDPOINT_BY_STATUS for point in points
        )

    def _report(self, path: str, reason: str) -> None:
        # Fixed endpoint/reason only; never dump requests, credentials or peers.
        if self.last_result.get(path) == reason:
            return
        self.last_result[path] = reason
        LOG.info("QM_ADVISORY endpoint=%s result=%s", path, reason)
