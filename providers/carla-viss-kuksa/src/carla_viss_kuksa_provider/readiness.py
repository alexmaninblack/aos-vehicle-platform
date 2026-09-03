# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Current-state-only readiness tracking for the selected VDP source."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from .bridge import Snapshot


@dataclass(frozen=True)
class SourceIdentity:
    unit_id: str
    node_id: str
    client_certificate_sha256: str
    assignment_generation: int
    role: str = "SELECTED_PLATFORM_UNIT"

    def __post_init__(self) -> None:
        if not _canonical_uuid(self.unit_id) or not _canonical_uuid(self.node_id):
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        if (
            len(self.client_certificate_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.client_certificate_sha256)
        ):
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        if (
            not isinstance(self.assignment_generation, int)
            or isinstance(self.assignment_generation, bool)
            or self.assignment_generation < 1
        ):
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        if self.role != "SELECTED_PLATFORM_UNIT":
            raise ValueError("SOURCE_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class ReadinessView:
    process_health: str
    data_readiness: str
    source_state: str
    reason: str


class ReadinessTracker:
    """Track one selected source without retaining telemetry history."""

    def __init__(self, expected_source: SourceIdentity) -> None:
        self._expected_source = expected_source
        self._manifest_valid = False
        self._provider_credential_ready = False
        self._kuksa_ready = False
        self._viss_mtls_ready = False
        self._source_matches = False
        self._last_source_timestamp: dt.datetime | None = None
        self._source_state = "STARTING"
        self._reason = "COMPONENT_ABSENT"

    @property
    def view(self) -> ReadinessView:
        ready = self._reason == "NONE"
        return ReadinessView(
            process_health="HEALTHY",
            data_readiness="READY" if ready else "NOT_READY",
            source_state=self._source_state,
            reason=self._reason,
        )

    def manifest_validated(self) -> None:
        self._manifest_valid = True
        self._source_state = "STARTING"
        self._reason = "TELEMETRY_DISCONNECTED"

    def manifest_invalid(self, reason: str = "CONTRACT_DIGEST_MISMATCH") -> None:
        self._manifest_valid = False
        self._source_state = "CONTRACT_MISMATCH"
        self._reason = reason

    def authenticating(self) -> None:
        if not self._manifest_valid:
            self._source_state = "CONTRACT_MISMATCH"
            self._reason = "CONTRACT_DIGEST_MISMATCH"
            return
        self._viss_mtls_ready = False
        self._source_matches = False
        self._source_state = "AUTHENTICATING"
        self._reason = "TELEMETRY_DISCONNECTED"

    def authentication_failed(self) -> None:
        self._viss_mtls_ready = False
        self._source_matches = False
        self._source_state = "AUTHENTICATION_FAILED"
        self._reason = "VISS_MTLS_UNAVAILABLE"

    def dependencies(
        self,
        *,
        provider_credential_ready: bool,
        kuksa_ready: bool,
        viss_mtls_ready: bool,
        source: SourceIdentity | None,
    ) -> None:
        self._provider_credential_ready = provider_credential_ready
        self._kuksa_ready = kuksa_ready
        self._viss_mtls_ready = viss_mtls_ready
        self._source_matches = source == self._expected_source
        if not self._manifest_valid:
            self._source_state = "CONTRACT_MISMATCH"
            self._reason = "CONTRACT_DIGEST_MISMATCH"
        elif not provider_credential_ready:
            self._source_state = "AUTHENTICATION_FAILED"
            self._reason = "PROVIDER_CREDENTIAL_UNAVAILABLE"
        elif not kuksa_ready:
            self._source_state = "DISCONNECTED"
            self._reason = "KUKSA_UNAVAILABLE"
        elif not viss_mtls_ready:
            self._source_state = "AUTHENTICATION_FAILED"
            self._reason = "VISS_MTLS_UNAVAILABLE"
        elif not self._source_matches:
            self._source_state = "AUTHENTICATION_FAILED"
            self._reason = "SOURCE_IDENTITY_MISMATCH"
        else:
            self._source_state = "DISCONNECTED"
            self._reason = "TELEMETRY_DISCONNECTED"

    def observe(self, snapshot: Snapshot) -> bool:
        if not self._dependencies_ready():
            return False
        timestamp = snapshot.source_timestamp
        if not snapshot.complete or timestamp is None:
            self._source_state = "DISCONNECTED"
            self._reason = "REQUIRED_PATH_MISSING"
            return False
        if self._last_source_timestamp is not None and timestamp <= self._last_source_timestamp:
            self._source_state = "STALE"
            self._reason = "TELEMETRY_STALE"
            return False
        self._last_source_timestamp = timestamp
        self._source_state = "LIVE"
        self._reason = "NONE"
        return True

    def stale(self) -> None:
        self._source_state = "STALE"
        self._reason = "TELEMETRY_STALE"

    def disconnected(self) -> None:
        self._source_state = "DISCONNECTED"
        self._reason = "TELEMETRY_DISCONNECTED"

    def _dependencies_ready(self) -> bool:
        return all(
            (
                self._manifest_valid,
                self._provider_credential_ready,
                self._kuksa_ready,
                self._viss_mtls_ready,
                self._source_matches,
            )
        )


def _canonical_uuid(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False
