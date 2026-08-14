# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Verify the exact provider imports in the target CPython environment."""

from __future__ import annotations

import importlib.metadata
import platform

import google.protobuf
import grpc
import kuksa_client.grpc
import websockets

import carla_viss_kuksa_provider.runtime


EXPECTED = {
    "grpcio": "1.75.0",
    "kuksa_client": "0.5.0",
    "protobuf": "5.29.5",
    "typing_extensions": "4.15.0",
    "websockets": "15.0.1",
}


if platform.machine() != "aarch64":
    raise SystemExit(f"Expected aarch64, found {platform.machine()}")
for distribution, expected_version in EXPECTED.items():
    actual_version = importlib.metadata.version(distribution)
    if actual_version != expected_version:
        raise SystemExit(
            f"Expected {distribution} {expected_version}, found {actual_version}"
        )
print("AOS-2 ARM64 provider runtime verification passed.")
