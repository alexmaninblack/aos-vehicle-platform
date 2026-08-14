# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Runtime wiring for verified VISS input and authenticated KUKSA output."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .bridge import (
    BridgeState,
    SIGNALS,
    SignalValue,
    parse_subscribe_response,
    subscription_request,
)


LOG = logging.getLogger("carla-viss-kuksa-provider")


@dataclass(frozen=True)
class Configuration:
    viss_uri: str
    viss_ca: Path
    viss_tls_server_name: str
    kuksa_host: str
    kuksa_port: int
    kuksa_ca: Path
    kuksa_tls_server_name: str
    kuksa_token: Path
    subscription_period_ms: int
    freshness_timeout_ms: int
    reconnect_initial_ms: int
    reconnect_max_ms: int


class KuksaSink:
    def __init__(self, configuration: Configuration) -> None:
        self._configuration = configuration
        self._client = None

    def publish(self, values: Mapping[str, SignalValue | None]) -> None:
        from kuksa_client.grpc import DataEntry, Datapoint, EntryUpdate, Field

        client = self._connect()
        updates = []
        for signal in SIGNALS:
            item = values[signal.path]
            datapoint = (
                Datapoint(item.value, item.timestamp)
                if item is not None
                else Datapoint(None)
            )
            updates.append(
                EntryUpdate(DataEntry(signal.path, value=datapoint), (Field.VALUE,))
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

        token = self._configuration.kuksa_token.read_text(encoding="utf-8").strip()
        if not token or "\n" in token:
            raise RuntimeError("KUKSA credential must contain exactly one token")
        client = VSSClient(
            self._configuration.kuksa_host,
            self._configuration.kuksa_port,
            token=token,
            root_certificates=self._configuration.kuksa_ca,
            tls_server_name=self._configuration.kuksa_tls_server_name,
        )
        client.connect()
        self._client = client
        LOG.info("Connected to the verified KUKSA Databroker")
        return client

    def close(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client = None


def run(configuration: Configuration, stop: threading.Event) -> int:
    from websockets.sync.client import connect

    sink = KuksaSink(configuration)
    bridge = BridgeState(
        sink,
        configuration.freshness_timeout_ms / 1000.0,
        time.monotonic,
    )
    tls_context = ssl.create_default_context(cafile=str(configuration.viss_ca))
    tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
    request_id = "carla-kuksa-provider-1"
    request = subscription_request(request_id, configuration.subscription_period_ms)
    reconnect_delay = configuration.reconnect_initial_ms / 1000.0
    maximum_delay = configuration.reconnect_max_ms / 1000.0

    try:
        while not stop.is_set():
            try:
                with connect(
                    configuration.viss_uri,
                    ssl=tls_context,
                    server_hostname=configuration.viss_tls_server_name,
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
                    reconnect_delay = configuration.reconnect_initial_ms / 1000.0
                    while not stop.is_set():
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
                stop.wait(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, maximum_delay)
    finally:
        try:
            bridge.mark_unavailable()
        except Exception as error:
            LOG.error("Could not clear KUKSA values during shutdown: %s", error)
        sink.close()
    return 0


def load_configuration(path: Path) -> Configuration:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise ValueError("configuration schemaVersion must be 1")
    viss = raw.get("viss")
    kuksa = raw.get("kuksa")
    timing = raw.get("timing")
    if not all(isinstance(item, dict) for item in (viss, kuksa, timing)):
        raise ValueError("configuration must contain viss, kuksa, and timing objects")
    configuration = Configuration(
        viss_uri=_string(viss, "uri"),
        viss_ca=Path(_string(viss, "caFile")),
        viss_tls_server_name=_string(viss, "tlsServerName"),
        kuksa_host=_string(kuksa, "host"),
        kuksa_port=_integer(kuksa, "port", 1, 65_535),
        kuksa_ca=Path(_string(kuksa, "caFile")),
        kuksa_tls_server_name=_string(kuksa, "tlsServerName"),
        kuksa_token=Path(_string(kuksa, "tokenFile")),
        subscription_period_ms=_integer(
            timing, "subscriptionPeriodMs", 50, 60_000
        ),
        freshness_timeout_ms=_integer(timing, "freshnessTimeoutMs", 100, 60_000),
        reconnect_initial_ms=_integer(timing, "reconnectInitialMs", 100, 60_000),
        reconnect_max_ms=_integer(timing, "reconnectMaxMs", 100, 300_000),
    )
    if not configuration.viss_uri.startswith("wss://"):
        raise ValueError("VISS URI must use wss://")
    if configuration.reconnect_initial_ms > configuration.reconnect_max_ms:
        raise ValueError("initial reconnect delay must not exceed maximum delay")
    for file_path in (
        configuration.viss_ca,
        configuration.kuksa_ca,
        configuration.kuksa_token,
    ):
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError(f"required regular file is unavailable: {file_path}")
    return configuration


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
    parser.add_argument("--config", required=True, type=Path)
    options = parser.parse_args(arguments)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    stop = threading.Event()

    def request_stop(_signal_number, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        configuration = load_configuration(options.config)
        return run(configuration, stop)
    except Exception as error:
        LOG.error("Provider failed: %s", error)
        return 1
