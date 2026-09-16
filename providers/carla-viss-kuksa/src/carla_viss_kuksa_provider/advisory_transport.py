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


class CurrentTargets:
    """Two bounded current values; no history or unbounded cross-thread queue."""

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
                if path in ENDPOINTS and isinstance(raw, str)
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

    def detach(self) -> None:
        self.websocket = None
        self.pending.clear()

    def set_value(self, path: str, canonical_value: str) -> None:
        if path not in ENDPOINTS or self.websocket is None:
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
        if not ready:
            self._report("transport", "KUKSA_TARGETS_UNAVAILABLE")
            return
        self._report("transport", "KUKSA_TARGETS_READY")
        for path, raw in values.items():
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
