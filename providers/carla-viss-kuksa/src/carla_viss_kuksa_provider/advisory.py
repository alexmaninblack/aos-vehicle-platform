# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Bounded defense-in-depth policy for the two typed v3 QM advisories."""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol


MAX_REQUEST_BYTES = 2048
MAX_STATUS_BYTES = 1024
MAX_ACCEPTANCE_AGE = dt.timedelta(milliseconds=2000)
MAX_LEASE = dt.timedelta(milliseconds=30000)
MIN_REFRESH_INTERVAL = 10.0
MIN_STATE_CHANGE_INTERVAL = 1.0
REPLAY_RETENTION = 300.0
REPLAY_CAPACITY_PER_ENDPOINT = 512
UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
DECISION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MODEL_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True)
class Endpoint:
    endpoint_id: str
    owner_service: str
    service_version: str
    request_path: str
    status_path: str
    recommendations: frozenset[str]
    set_reason: str


ENDPOINTS = {
    "Vehicle.OEM.BrakeHealth.Advisory.Request": Endpoint(
        "BRAKE_HEALTH_ADVISORY",
        "BRAKE_HEALTH",
        "3.0.0",
        "Vehicle.OEM.BrakeHealth.Advisory.Request",
        "Vehicle.OEM.BrakeHealth.Advisory.GatewayStatus",
        frozenset({"INSPECTION_RECOMMENDED"}),
        "PREDICTED_BRAKE_DEGRADATION",
    ),
    "Vehicle.OEM.TireHealth.Advisory.Request": Endpoint(
        "TIRE_HEALTH_ADVISORY",
        "TIRE_HEALTH",
        "1.0.0",
        "Vehicle.OEM.TireHealth.Advisory.Request",
        "Vehicle.OEM.TireHealth.Advisory.GatewayStatus",
        frozenset(
            {"TIRE_INSPECTION_RECOMMENDED", "TIRE_REPLACEMENT_RECOMMENDED"}
        ),
        "PREDICTED_TIRE_WEAR",
    ),
}
ENDPOINT_BY_STATUS = {endpoint.status_path: endpoint for endpoint in ENDPOINTS.values()}


@dataclass(frozen=True)
class Caller:
    service_id: str
    service_version: str
    authority: str = "SERVICE_WRITE"


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str
    forwarded: bool = False
    application_success: bool = False


class VissWriter(Protocol):
    def set_value(self, path: str, canonical_value: str) -> None:
        """Issue one narrow VISS Set. Transport success is not application success."""


class StatusPublisher(Protocol):
    def publish_status(self, path: str, canonical_value: str) -> None:
        """Publish authoritative Gateway status into the read-only KUKSA leaf."""


class AdvisoryPolicy:
    """Validate, bound and correlate v3 advisory traffic using current state only."""

    def __init__(self, viss: VissWriter, kuksa: StatusPublisher) -> None:
        self._viss = viss
        self._kuksa = kuksa
        self._replay: dict[str, OrderedDict[tuple[str, str, int], tuple[str, float]]] = {
            endpoint.endpoint_id: OrderedDict() for endpoint in ENDPOINTS.values()
        }
        self._latest_sequence: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._last_forward: dict[str, tuple[float, tuple[str, str | None]]] = {}
        self._pending: OrderedDict[tuple[str, str, int], Endpoint] = OrderedDict()

    def handle_request(
        self,
        caller: Caller,
        path: str,
        raw_value: str,
        now_utc: dt.datetime,
        monotonic_now: float,
    ) -> Decision:
        endpoint = ENDPOINTS.get(path)
        if endpoint is None:
            return Decision(False, "UNAUTHORIZED_PATH")
        if (
            caller.authority != "SERVICE_WRITE"
            or caller.service_id != endpoint.owner_service
            or caller.service_version != endpoint.service_version
        ):
            return Decision(False, "UNAUTHORIZED_SOURCE")
        try:
            request = _canonical_object(raw_value, MAX_REQUEST_BYTES)
            _validate_request(request, endpoint, caller, now_utc)
        except AdvisoryError as error:
            return Decision(False, error.reason)

        identity = _identity(request)
        canonical = canonical_json(request)
        replay = self._replay[endpoint.endpoint_id]
        self._expire_replay(replay, monotonic_now)
        previous = replay.get(identity)
        if previous is not None:
            if previous[0] == canonical:
                return Decision(True, "IDEMPOTENT_NO_NEW_EFFECT")
            return Decision(False, "REPLAY_DETECTED")

        sequence_key = (endpoint.endpoint_id, request["producerEpoch"])
        latest_sequence = self._latest_sequence.get(sequence_key)
        if latest_sequence is not None and request["sequence"] <= latest_sequence:
            return Decision(False, "SEQUENCE_ROLLBACK")

        requested_state = (request["operation"], request.get("recommendation"))
        last_forward = self._last_forward.get(endpoint.endpoint_id)
        if last_forward is not None:
            elapsed = monotonic_now - last_forward[0]
            minimum = (
                MIN_REFRESH_INTERVAL
                if requested_state == last_forward[1]
                else MIN_STATE_CHANGE_INTERVAL
            )
            if elapsed < minimum:
                return Decision(False, "RATE_LIMITED")

        replay[identity] = (canonical, monotonic_now)
        replay.move_to_end(identity)
        while len(replay) > REPLAY_CAPACITY_PER_ENDPOINT:
            replay.popitem(last=False)
        self._latest_sequence[sequence_key] = request["sequence"]
        self._latest_sequence.move_to_end(sequence_key)
        while len(self._latest_sequence) > 2 * REPLAY_CAPACITY_PER_ENDPOINT:
            self._latest_sequence.popitem(last=False)
        self._last_forward[endpoint.endpoint_id] = (monotonic_now, requested_state)
        self._pending[identity] = endpoint
        self._pending.move_to_end(identity)
        while len(self._pending) > 2 * REPLAY_CAPACITY_PER_ENDPOINT:
            self._pending.popitem(last=False)
        try:
            self._viss.set_value(endpoint.request_path, canonical)
        except Exception:
            return Decision(False, "INTERNAL_ERROR")
        return Decision(True, "FORWARDED_TO_GATEWAY", forwarded=True)

    def handle_gateway_status(self, path: str, raw_value: str) -> Decision:
        endpoint = ENDPOINT_BY_STATUS.get(path)
        if endpoint is None:
            return Decision(False, "UNAUTHORIZED_PATH")
        try:
            status = _canonical_object(raw_value, MAX_STATUS_BYTES)
            _validate_status(status)
        except AdvisoryError as error:
            return Decision(False, error.reason)
        identity = _identity(status)
        if self._pending.get(identity) != endpoint:
            return Decision(False, "REPLAY_DETECTED")
        canonical = canonical_json(status)
        self._kuksa.publish_status(endpoint.status_path, canonical)
        if status["state"] in {"APPLIED", "CLEARED", "REJECTED", "EXPIRED", "FAILED"}:
            self._pending.pop(identity, None)
        return Decision(
            True,
            "GATEWAY_STATUS_PUBLISHED",
            application_success=status["state"] in {"APPLIED", "CLEARED"},
        )

    def _expire_replay(
        self,
        replay: OrderedDict[tuple[str, str, int], tuple[str, float]],
        monotonic_now: float,
    ) -> None:
        while replay:
            first_identity = next(iter(replay))
            if monotonic_now - replay[first_identity][1] < REPLAY_RETENTION:
                break
            replay.popitem(last=False)


class AdvisoryError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _canonical_object(raw_value: str, maximum_bytes: int) -> dict[str, object]:
    if not isinstance(raw_value, str) or len(raw_value.encode("utf-8")) > maximum_bytes:
        raise AdvisoryError("INVALID_SCHEMA")
    try:
        value = json.loads(raw_value)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise AdvisoryError("INVALID_SCHEMA") from error
    if not isinstance(value, dict) or raw_value != canonical_json(value):
        raise AdvisoryError("INVALID_SCHEMA")
    return value


def _validate_request(
    request: dict[str, object],
    endpoint: Endpoint,
    caller: Caller,
    now_utc: dt.datetime,
) -> None:
    base_fields = {
        "schemaVersion",
        "requestId",
        "producerEpoch",
        "sequence",
        "operation",
        "reasonCode",
        "decisionId",
        "serviceVersion",
        "modelVersion",
        "issuedAt",
        "expiresAt",
    }
    operation = request.get("operation")
    expected_fields = base_fields | ({"recommendation"} if operation == "SET" else set())
    if set(request) != expected_fields or request.get("schemaVersion") != 1:
        raise AdvisoryError("INVALID_SCHEMA")
    if not _valid_uuid(request.get("requestId")) or not _valid_uuid(request.get("producerEpoch")):
        raise AdvisoryError("INVALID_VALUE")
    sequence = request.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise AdvisoryError("INVALID_VALUE")
    if request.get("serviceVersion") != caller.service_version:
        raise AdvisoryError("UNAUTHORIZED_SOURCE")
    if not isinstance(request.get("decisionId"), str) or DECISION_ID.fullmatch(request["decisionId"]) is None:
        raise AdvisoryError("INVALID_VALUE")
    if not isinstance(request.get("modelVersion"), str) or MODEL_VERSION.fullmatch(request["modelVersion"]) is None:
        raise AdvisoryError("INVALID_VALUE")
    if operation == "SET":
        if request.get("recommendation") not in endpoint.recommendations:
            raise AdvisoryError("INVALID_VALUE")
        if request.get("reasonCode") != endpoint.set_reason:
            raise AdvisoryError("INVALID_VALUE")
    elif operation == "CLEAR":
        if request.get("reasonCode") != "CONDITION_CLEARED":
            raise AdvisoryError("INVALID_VALUE")
    else:
        raise AdvisoryError("INVALID_VALUE")
    issued_at = _timestamp(request.get("issuedAt"))
    expires_at = _timestamp(request.get("expiresAt"))
    if now_utc.tzinfo is None or now_utc.utcoffset() != dt.timedelta(0):
        raise AdvisoryError("INVALID_VALUE")
    if issued_at > now_utc or now_utc - issued_at > MAX_ACCEPTANCE_AGE:
        raise AdvisoryError("STALE_REQUEST")
    if expires_at <= now_utc or expires_at <= issued_at or expires_at - issued_at > MAX_LEASE:
        raise AdvisoryError("STALE_REQUEST")


def _validate_status(status: dict[str, object]) -> None:
    required = {
        "schemaVersion",
        "requestId",
        "producerEpoch",
        "sequence",
        "state",
        "reason",
        "gatewayObservedAt",
        "activeRecommendation",
        "activeReasonCode",
        "activeUntil",
    }
    if set(status) != required or status.get("schemaVersion") != 1:
        raise AdvisoryError("INVALID_SCHEMA")
    if not _valid_uuid(status.get("requestId")) or not _valid_uuid(status.get("producerEpoch")):
        raise AdvisoryError("INVALID_VALUE")
    sequence = status.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise AdvisoryError("INVALID_VALUE")
    if status.get("state") not in {"RECEIVED", "APPLIED", "CLEARED", "REJECTED", "EXPIRED", "FAILED"}:
        raise AdvisoryError("INVALID_VALUE")
    if status.get("reason") not in {
        "NONE",
        "UNAUTHORIZED_SOURCE",
        "UNAUTHORIZED_PATH",
        "INVALID_SCHEMA",
        "INVALID_VALUE",
        "STALE_REQUEST",
        "REPLAY_DETECTED",
        "SEQUENCE_ROLLBACK",
        "RATE_LIMITED",
        "QM_POLICY_DENIED",
        "INTERNAL_ERROR",
    }:
        raise AdvisoryError("INVALID_VALUE")
    if status.get("activeRecommendation") not in {
        "NONE",
        "INSPECTION_RECOMMENDED",
        "TIRE_INSPECTION_RECOMMENDED",
        "TIRE_REPLACEMENT_RECOMMENDED",
    }:
        raise AdvisoryError("INVALID_VALUE")
    if status.get("activeReasonCode") not in {
        "NONE",
        "PREDICTED_BRAKE_DEGRADATION",
        "PREDICTED_TIRE_WEAR",
    }:
        raise AdvisoryError("INVALID_VALUE")
    _timestamp(status.get("gatewayObservedAt"))
    active_until = status.get("activeUntil")
    if active_until is not None:
        _timestamp(active_until)


def _identity(value: dict[str, object]) -> tuple[str, str, int]:
    return (value["requestId"], value["producerEpoch"], value["sequence"])


def _valid_uuid(value: object) -> bool:
    return isinstance(value, str) and UUID.fullmatch(value) is not None


def _timestamp(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AdvisoryError("INVALID_VALUE")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AdvisoryError("INVALID_VALUE") from error
    if parsed.utcoffset() != dt.timedelta(0):
        raise AdvisoryError("INVALID_VALUE")
    return parsed
