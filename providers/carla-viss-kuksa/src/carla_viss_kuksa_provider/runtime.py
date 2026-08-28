# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Runtime wiring for verified VISS input and authenticated KUKSA output."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import re
import signal
import socket
import ssl
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Mapping

from .bridge import (
    BridgeState,
    SIGNALS,
    SignalSpec,
    SignalValue,
    parse_subscribe_response,
    subscription_request,
)
from .manifest import load_manifest

try:
    from . import vdp_release_profile as ACTIVE_RELEASE_PROFILE
except ImportError:
    ACTIVE_RELEASE_PROFILE = None


LOG = logging.getLogger("carla-viss-kuksa-provider")
COMPONENT_SCHEMA_VERSION = 2
COMPONENT_NAME = "carla-viss-kuksa"
TELEMETRY_PROFILE = "0.1.1"
RUNTIME_INTERFACE = 1
KUKSA_HOST = "127.0.0.1"
KUKSA_PORT = 55555
KUKSA_CA = Path("/etc/kuksa-val/CA.pem")
KUKSA_TLS_SERVER_NAME = "127.0.0.1"
EXTERNAL_CONFIGURATION_ENV = "AOS_VEHICLE_DATA_PROVIDER_CONFIGURATION"
VISS_CA_ENV = "AOS_VEHICLE_DATA_PROVIDER_VISS_CA"
CREDENTIAL_DIRECTORY_ENV = "CREDENTIALS_DIRECTORY"
EXPECTED_RUNTIME = {
    "grpcio": "1.75.0",
    "kuksa_client": "0.5.0",
    "protobuf": "5.29.6",
    "typing_extensions": "4.15.0",
    "websockets": "15.0.1",
}


@dataclass(frozen=True)
class PayloadConfiguration:
    subscription_period_ms: int
    freshness_timeout_ms: int
    reconnect_initial_ms: int
    reconnect_max_ms: int
    semantic_version: str | None = None
    signals: tuple[SignalSpec, ...] = SIGNALS
    advisory_enabled: bool = False


@dataclass(frozen=True)
class VissConfiguration:
    uri: str
    ca: Path
    tls_server_name: str
    client_certificate: Path | None = None
    client_key: Path | None = None
    source_identity: tuple[str, str, str, int] | None = None


@dataclass(frozen=True)
class KuksaConfiguration:
    host: str
    port: int
    ca: Path
    tls_server_name: str
    token: Path


@dataclass(frozen=True)
class Configuration:
    payload: PayloadConfiguration
    viss: VissConfiguration
    kuksa: KuksaConfiguration


class KuksaSink:
    def __init__(
        self,
        configuration: KuksaConfiguration,
        signals: tuple[SignalSpec, ...] = SIGNALS,
    ) -> None:
        self._configuration = configuration
        self._signals = signals
        self._client = None

    def publish(self, values: Mapping[str, SignalValue | None]) -> None:
        from kuksa_client.grpc import DataEntry, Datapoint, EntryUpdate, Field

        client = self._connect()
        updates = []
        for signal_spec in self._signals:
            item = values[signal_spec.path]
            datapoint = (
                Datapoint(item.value, item.timestamp)
                if item is not None
                else Datapoint(None)
            )
            updates.append(
                EntryUpdate(
                    DataEntry(signal_spec.path, value=datapoint), (Field.VALUE,)
                )
            )
        try:
            client.set(updates, try_v2=False, timeout=2.0)
        except Exception:
            self.close()
            raise

    def _connect(self):
        if self._client is not None:
            return self._client
        from kuksa_client.grpc import VSSClient

        token = self._configuration.token.read_text(encoding="utf-8").strip()
        if not token or "\n" in token:
            raise RuntimeError("KUKSA credential must contain exactly one token")
        client = VSSClient(
            self._configuration.host,
            self._configuration.port,
            token=token,
            root_certificates=self._configuration.ca,
            tls_server_name=self._configuration.tls_server_name,
        )
        client.connect()
        self._client = client
        LOG.info("Connected to the verified KUKSA Databroker")
        return client

    def close(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client = None


def run(
    configuration: Configuration,
    stop: threading.Event,
    unavailable_requested: threading.Event,
) -> int:
    from websockets.sync.client import connect

    sink = KuksaSink(configuration.kuksa, configuration.payload.signals)
    bridge = BridgeState(
        sink,
        configuration.payload.freshness_timeout_ms / 1000.0,
        time.monotonic,
        configuration.payload.signals,
        require_complete_frames=configuration.payload.semantic_version is not None,
    )
    tls_context = ssl.create_default_context(cafile=str(configuration.viss.ca))
    tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
    if configuration.viss.client_certificate is not None:
        assert configuration.viss.client_key is not None
        tls_context.load_cert_chain(
            configuration.viss.client_certificate,
            configuration.viss.client_key,
        )
    request_id = "carla-kuksa-provider-1"
    request = subscription_request(
        request_id,
        configuration.payload.subscription_period_ms,
        configuration.payload.signals,
    )
    reconnect_delay = configuration.payload.reconnect_initial_ms / 1000.0
    maximum_delay = configuration.payload.reconnect_max_ms / 1000.0

    def apply_unavailable_request() -> None:
        if unavailable_requested.is_set():
            bridge.mark_unavailable()
            unavailable_requested.clear()
            LOG.info("Explicit unavailability request completed")

    try:
        # KUKSA authentication and fail-safe unavailability are the readiness
        # boundary. CARLA may remain absent without failing component health.
        bridge.mark_unavailable()
        unavailable_requested.clear()
        notify_ready()
        LOG.info("Provider is ready; CARLA availability is not required")
        while not stop.is_set():
            apply_unavailable_request()
            try:
                with connect(
                    configuration.viss.uri,
                    ssl=tls_context,
                    server_hostname=configuration.viss.tls_server_name,
                    subprotocols=["VISSv3"],
                    proxy=None,
                    open_timeout=5,
                    close_timeout=2,
                    ping_interval=20,
                    ping_timeout=10,
                    max_size=262_144,
                ) as websocket:
                    if websocket.subprotocol != "VISSv3":
                        raise RuntimeError("VISS server did not negotiate VISSv3")
                    websocket.send(request)
                    subscription_id = parse_subscribe_response(
                        websocket.recv(timeout=5), request_id
                    )
                    LOG.info("Connected to the verified CARLA VISS endpoint")
                    reconnect_delay = (
                        configuration.payload.reconnect_initial_ms / 1000.0
                    )
                    while not stop.is_set():
                        apply_unavailable_request()
                        try:
                            message = websocket.recv(timeout=0.1)
                        except TimeoutError:
                            if bridge.tick():
                                LOG.warning(
                                    "CARLA telemetry became stale; KUKSA values are unavailable"
                                )
                            continue
                        snapshot = bridge.handle_message(message, subscription_id)
                        if snapshot.invalid_paths:
                            LOG.warning(
                                "Invalid CARLA values were marked unavailable: %s",
                                ", ".join(snapshot.invalid_paths),
                            )
            except Exception as error:
                try:
                    if bridge.mark_unavailable():
                        LOG.warning(
                            "CARLA connection was lost; KUKSA values are unavailable"
                        )
                except Exception as stale_error:
                    LOG.error("Could not mark KUKSA values unavailable: %s", stale_error)
                sink.close()
                if stop.is_set():
                    break
                LOG.warning(
                    "Telemetry bridge will reconnect in %.1f seconds: %s",
                    reconnect_delay,
                    error,
                )
                deadline = time.monotonic() + reconnect_delay
                while not stop.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    unavailable_requested.wait(min(remaining, 0.1))
                    apply_unavailable_request()
                reconnect_delay = min(reconnect_delay * 2, maximum_delay)
    finally:
        try:
            bridge.mark_unavailable()
        except Exception as error:
            LOG.error("Could not clear KUKSA values during shutdown: %s", error)
        sink.close()
    return 0


def load_payload_configuration(
    path: Path,
    release_profile: ModuleType | None = None,
) -> PayloadConfiguration:
    raw = _read_object(path, "component configuration")
    if raw.get("schemaVersion") == 3:
        return _load_release_payload_configuration(
            path,
            raw,
            ACTIVE_RELEASE_PROFILE if release_profile is None else release_profile,
        )
    _require_keys(
        raw,
        {
            "schemaVersion",
            "provider",
            "vehicleTelemetryProfile",
            "runtimeInterface",
            "timing",
        },
        {"$comment"},
        "component configuration",
    )
    if raw["schemaVersion"] != COMPONENT_SCHEMA_VERSION:
        raise ValueError("component configuration schemaVersion must be 2")
    if raw["provider"] != COMPONENT_NAME:
        raise ValueError("component provider identity is incompatible")
    if raw["vehicleTelemetryProfile"] != TELEMETRY_PROFILE:
        raise ValueError("vehicle telemetry profile is incompatible")
    if raw["runtimeInterface"] != RUNTIME_INTERFACE:
        raise ValueError("provider runtime interface is incompatible")
    timing = raw["timing"]
    if not isinstance(timing, dict):
        raise ValueError("component timing configuration must be an object")
    _require_keys(
        timing,
        {
            "subscriptionPeriodMs",
            "freshnessTimeoutMs",
            "reconnectInitialMs",
            "reconnectMaxMs",
        },
        set(),
        "component timing configuration",
    )
    configuration = PayloadConfiguration(
        subscription_period_ms=_integer(
            timing, "subscriptionPeriodMs", 50, 60_000
        ),
        freshness_timeout_ms=_integer(timing, "freshnessTimeoutMs", 100, 60_000),
        reconnect_initial_ms=_integer(timing, "reconnectInitialMs", 100, 60_000),
        reconnect_max_ms=_integer(timing, "reconnectMaxMs", 100, 300_000),
    )
    if configuration.reconnect_initial_ms > configuration.reconnect_max_ms:
        raise ValueError("initial reconnect delay must not exceed maximum delay")
    return configuration


def _load_release_payload_configuration(
    path: Path,
    raw: dict[str, object],
    release_profile: ModuleType | None,
) -> PayloadConfiguration:
    if release_profile is None:
        raise ValueError("component release profile is unavailable")
    _require_keys(
        raw,
        {
            "schemaVersion",
            "provider",
            "semanticVersion",
            "capabilityManifest",
            "capabilityManifestSha256",
            "runtimeInterface",
            "timing",
        },
        {"$comment"},
        "component release configuration",
    )
    if raw["provider"] != COMPONENT_NAME or raw["runtimeInterface"] != RUNTIME_INTERFACE:
        raise ValueError("component release identity is incompatible")
    if raw["semanticVersion"] != release_profile.VERSION:
        raise ValueError("component release version is incompatible")
    if raw["capabilityManifest"] != "capability-manifest.json":
        raise ValueError("component capability manifest path is incompatible")
    if raw["capabilityManifestSha256"] != release_profile.MANIFEST_SHA256:
        raise ValueError("component capability manifest digest is incompatible")
    load_manifest(path.parent / "capability-manifest.json", release_profile)
    timing = raw["timing"]
    if not isinstance(timing, dict):
        raise ValueError("component timing configuration must be an object")
    _require_keys(
        timing,
        {
            "subscriptionPeriodMs",
            "freshnessTimeoutMs",
            "reconnectInitialMs",
            "reconnectMaxMs",
        },
        set(),
        "component timing configuration",
    )
    configuration = PayloadConfiguration(
        subscription_period_ms=_integer(timing, "subscriptionPeriodMs", 50, 60_000),
        freshness_timeout_ms=_integer(timing, "freshnessTimeoutMs", 100, 60_000),
        reconnect_initial_ms=_integer(timing, "reconnectInitialMs", 100, 60_000),
        reconnect_max_ms=_integer(timing, "reconnectMaxMs", 100, 300_000),
        semantic_version=release_profile.VERSION,
        signals=release_profile.SIGNALS,
        advisory_enabled=bool(release_profile.ADVISORY_ENDPOINT_IDS),
    )
    if configuration.reconnect_initial_ms > configuration.reconnect_max_ms:
        raise ValueError("initial reconnect delay must not exceed maximum delay")
    return configuration


def load_configuration(
    path: Path, environment: Mapping[str, str] | None = None
) -> Configuration:
    raw = _read_object(path, "provider configuration")
    if raw.get("schemaVersion") == 1:
        return _load_legacy_configuration(raw)
    environment = os.environ if environment is None else environment
    payload = load_payload_configuration(path)
    return Configuration(
        payload=payload,
        viss=_load_viss_configuration(
            environment,
            require_mutual_tls=payload.semantic_version is not None,
        ),
        kuksa=_load_kuksa_configuration(environment),
    )


def mark_unavailable(
    path: Path, environment: Mapping[str, str] | None = None
) -> None:
    environment = os.environ if environment is None else environment
    payload = load_payload_configuration(path)
    sink = KuksaSink(_load_kuksa_configuration(environment), payload.signals)
    try:
        sink.publish({signal_spec.path: None for signal_spec in payload.signals})
    finally:
        sink.close()


def offline_self_test(path: Path) -> None:
    load_payload_configuration(path)
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("provider requires CPython 3.12")
    if platform.machine() != "aarch64":
        raise RuntimeError("provider requires AArch64")
    for distribution, expected_version in EXPECTED_RUNTIME.items():
        actual_version = importlib.metadata.version(distribution)
        if actual_version != expected_version:
            raise RuntimeError(
                f"provider requires {distribution} {expected_version}, found {actual_version}"
            )
    # Import the complete runtime surface without opening a socket.
    import google.protobuf  # noqa: F401
    import grpc  # noqa: F401
    import kuksa_client.grpc  # noqa: F401
    import websockets  # noqa: F401


def notify_ready(environment: Mapping[str, str] | None = None) -> None:
    environment = os.environ if environment is None else environment
    address = environment.get("NOTIFY_SOCKET")
    if not address:
        # Offline self-tests may omit NOTIFY_SOCKET. The production component
        # unit uses Type=notify and always supplies it.
        return
    if address.startswith("@"):
        address = "\0" + address[1:]
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notifier:
        notifier.connect(address)
        notifier.sendall(b"READY=1\nSTATUS=KUKSA authenticated; values unavailable\n")


def _load_viss_configuration(
    environment: Mapping[str, str],
    require_mutual_tls: bool = False,
) -> VissConfiguration:
    configuration_path = _absolute_environment_path(
        environment, EXTERNAL_CONFIGURATION_ENV
    )
    raw = _read_object(configuration_path, "vehicle integration configuration")
    expected_schema = 2 if require_mutual_tls else 1
    required_keys = {"schemaVersion", "viss"}
    if require_mutual_tls:
        required_keys.add("selectedSource")
    _require_keys(raw, required_keys, {"$comment"}, "vehicle integration configuration")
    if raw["schemaVersion"] != expected_schema:
        raise ValueError(
            f"vehicle integration configuration schemaVersion must be {expected_schema}"
        )
    viss = raw["viss"]
    if not isinstance(viss, dict):
        raise ValueError("vehicle integration VISS configuration must be an object")
    _require_keys(
        viss,
        {"uri", "tlsServerName"},
        set(),
        "vehicle integration VISS configuration",
    )
    uri = _string(viss, "uri")
    if not uri.startswith("wss://"):
        raise ValueError("VISS URI must use wss://")
    ca = _absolute_environment_path(environment, VISS_CA_ENV)
    _require_regular_file(ca, "VISS trust anchor")
    client_certificate = None
    client_key = None
    source_identity = None
    if require_mutual_tls:
        selected_source = raw["selectedSource"]
        if not isinstance(selected_source, dict):
            raise ValueError("selected source configuration must be an object")
        _require_keys(
            selected_source,
            {
                "unitId",
                "nodeId",
                "clientCertificateSha256",
                "assignmentGeneration",
                "role",
            },
            set(),
            "selected source configuration",
        )
        role = _string(selected_source, "role")
        fingerprint = _string(selected_source, "clientCertificateSha256")
        generation = _integer(selected_source, "assignmentGeneration", 1, 2**63 - 1)
        if role != "SELECTED_PLATFORM_UNIT" or re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            raise ValueError("selected source identity is incompatible")
        credential_directory = _absolute_environment_path(
            environment, CREDENTIAL_DIRECTORY_ENV
        )
        client_certificate = credential_directory / "viss-client-cert.pem"
        client_key = credential_directory / "viss-client-key.pem"
        _require_regular_file(client_certificate, "VISS client certificate")
        _require_regular_file(client_key, "VISS client key")
        if _certificate_sha256(client_certificate) != fingerprint:
            raise ValueError("selected source certificate fingerprint is incompatible")
        source_identity = (
            _string(selected_source, "unitId"),
            _string(selected_source, "nodeId"),
            fingerprint,
            generation,
        )
    return VissConfiguration(
        uri=uri,
        ca=ca,
        tls_server_name=_string(viss, "tlsServerName"),
        client_certificate=client_certificate,
        client_key=client_key,
        source_identity=source_identity,
    )


def _load_kuksa_configuration(environment: Mapping[str, str]) -> KuksaConfiguration:
    credential_directory = _absolute_environment_path(
        environment, CREDENTIAL_DIRECTORY_ENV
    )
    if not credential_directory.is_dir() or credential_directory.is_symlink():
        raise ValueError("systemd credential directory is unavailable")
    token = credential_directory / "kuksa-token"
    _require_regular_file(token, "KUKSA credential")
    _require_regular_file(KUKSA_CA, "KUKSA trust anchor")
    return KuksaConfiguration(
        host=KUKSA_HOST,
        port=KUKSA_PORT,
        ca=KUKSA_CA,
        tls_server_name=KUKSA_TLS_SERVER_NAME,
        token=token,
    )


def _load_legacy_configuration(raw: dict[str, object]) -> Configuration:
    viss = raw.get("viss")
    kuksa = raw.get("kuksa")
    timing = raw.get("timing")
    if not all(isinstance(item, dict) for item in (viss, kuksa, timing)):
        raise ValueError("legacy configuration must contain viss, kuksa, and timing")
    assert isinstance(viss, dict)
    assert isinstance(kuksa, dict)
    assert isinstance(timing, dict)
    viss_configuration = VissConfiguration(
        uri=_string(viss, "uri"),
        ca=Path(_string(viss, "caFile")),
        tls_server_name=_string(viss, "tlsServerName"),
    )
    kuksa_configuration = KuksaConfiguration(
        host=_string(kuksa, "host"),
        port=_integer(kuksa, "port", 1, 65_535),
        ca=Path(_string(kuksa, "caFile")),
        tls_server_name=_string(kuksa, "tlsServerName"),
        token=Path(_string(kuksa, "tokenFile")),
    )
    payload = PayloadConfiguration(
        subscription_period_ms=_integer(timing, "subscriptionPeriodMs", 50, 60_000),
        freshness_timeout_ms=_integer(timing, "freshnessTimeoutMs", 100, 60_000),
        reconnect_initial_ms=_integer(timing, "reconnectInitialMs", 100, 60_000),
        reconnect_max_ms=_integer(timing, "reconnectMaxMs", 100, 300_000),
    )
    if not viss_configuration.uri.startswith("wss://"):
        raise ValueError("VISS URI must use wss://")
    if payload.reconnect_initial_ms > payload.reconnect_max_ms:
        raise ValueError("initial reconnect delay must not exceed maximum delay")
    for file_path in (
        viss_configuration.ca,
        kuksa_configuration.ca,
        kuksa_configuration.token,
    ):
        _require_regular_file(file_path, "legacy provider dependency")
    return Configuration(payload, viss_configuration, kuksa_configuration)


def _read_object(path: Path, label: str) -> dict[str, object]:
    _require_regular_file(path, label)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")
    return raw


def _require_regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is unavailable")


def _certificate_sha256(path: Path) -> str:
    try:
        der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
    except (UnicodeError, ValueError) as error:
        raise ValueError("VISS client certificate is malformed") from error
    return hashlib.sha256(der).hexdigest()


def _absolute_environment_path(
    environment: Mapping[str, str], variable: str
) -> Path:
    value = environment.get(variable, "")
    path = Path(value)
    if not value or not path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{variable} does not contain a safe absolute path")
    return path


def _require_keys(
    container: dict[str, object],
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    keys = set(container)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise ValueError(f"{label} has missing or unexpected fields")


def _string(container: dict[str, object], key: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _integer(
    container: dict[str, object], key: str, minimum: int, maximum: int
) -> int:
    value = container.get(key)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--self-test", action="store_true")
    operation.add_argument("--mark-unavailable", action="store_true")
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args(arguments)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        if options.self_test:
            offline_self_test(options.config)
            LOG.info("Provider offline self-test passed")
            return 0
        if options.mark_unavailable:
            mark_unavailable(options.config)
            LOG.info("Provider values are unavailable")
            return 0

        configuration = load_configuration(options.config)
        stop = threading.Event()
        unavailable_requested = threading.Event()

        def request_stop(_signal_number, _frame) -> None:
            stop.set()

        def request_unavailable(_signal_number, _frame) -> None:
            unavailable_requested.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGHUP, request_unavailable)
        return run(configuration, stop, unavailable_requested)
    except Exception as error:
        LOG.error("Provider failed: %s", error)
        return 1
