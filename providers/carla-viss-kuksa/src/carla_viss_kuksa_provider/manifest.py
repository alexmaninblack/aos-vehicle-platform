# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed validation for an immutable build-selected VDP manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import ModuleType


COMPONENT_TYPE = "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider"
VDP_CONTRACT = {
    "contractId": "aosedge-demo-vdp-compatibility",
    "contractVersion": "1.0.1",
    "sha256": "8e58e18e9d99a13409af6813e573cbe1c690e439ad746224426801f6b080c871",
}
VISS_CONTRACT = {
    "contractId": "aosedge-demo-viss-trust-telemetry-profile",
    "contractVersion": "1.1.0",
    "sha256": "4a1a2bd804c3a49f707b5e640632bd8a0357901f59e4615c340622b043d4c12c",
}
HARDWARE_PROFILE = {
    "profileVersion": "1.0.0",
    "sha256": "ac0ba26464219482dcb41e56ebbc1538489e13bd6c84725dbc124e59514cb7e5",
}
ADVISORY_CONTRACT = {
    "contractId": "aosedge-demo-typed-qm-advisory",
    "contractVersion": "1.0.2",
    "sha256": "f7ae78148fb3b3265c8b773117126665afb1edd97a73f59db5a1f3af7c223487",
}
ADVISORY_ENDPOINTS = {
    "BRAKE_HEALTH_ADVISORY": {
        "id": "BRAKE_HEALTH_ADVISORY",
        "ownerService": "BRAKE_HEALTH",
        "requestPath": "Vehicle.OEM.BrakeHealth.Advisory.Request",
        "statusPath": "Vehicle.OEM.BrakeHealth.Advisory.GatewayStatus",
    },
    "TIRE_HEALTH_ADVISORY": {
        "id": "TIRE_HEALTH_ADVISORY",
        "ownerService": "TIRE_HEALTH",
        "requestPath": "Vehicle.OEM.TireHealth.Advisory.Request",
        "statusPath": "Vehicle.OEM.TireHealth.Advisory.GatewayStatus",
    },
}


class ManifestError(ValueError):
    """Raised when signed profile identity is incomplete or inconsistent."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(path: Path, profile: ModuleType) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ManifestError("CAPABILITY_MANIFEST_MALFORMED")
    raw = path.read_bytes()
    if sha256_bytes(raw) != profile.MANIFEST_SHA256:
        raise ManifestError("CONTRACT_DIGEST_MISMATCH")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ManifestError("CAPABILITY_MANIFEST_MALFORMED") from error
    validate_manifest(manifest, profile)
    return manifest


def validate_manifest(manifest: object, profile: ModuleType) -> None:
    if not isinstance(manifest, dict):
        raise ManifestError("CAPABILITY_MANIFEST_MALFORMED")
    required_keys = {
        "$comment",
        "advisoryEndpoints",
        "capabilities",
        "componentId",
        "componentType",
        "contracts",
        "readPaths",
        "runtimeInterface",
        "schemaVersion",
        "semanticVersion",
    }
    if set(manifest) != required_keys:
        raise ManifestError("CAPABILITY_MANIFEST_MALFORMED")
    if manifest["schemaVersion"] != 1 or manifest["runtimeInterface"] != 1:
        raise ManifestError("COMPONENT_VERSION_UNSUPPORTED")
    if manifest["componentId"] != "vehicle-data-platform":
        raise ManifestError("CONTRACT_ID_MISMATCH")
    if manifest["componentType"] != COMPONENT_TYPE:
        raise ManifestError("COMPONENT_VERSION_UNSUPPORTED")
    if manifest["semanticVersion"] != profile.VERSION:
        raise ManifestError("COMPONENT_VERSION_UNSUPPORTED")
    expected_paths = [signal.path for signal in profile.SIGNALS]
    if manifest["readPaths"] != expected_paths:
        raise ManifestError("REQUIRED_PATH_MISSING")
    if manifest["capabilities"] != list(profile.CAPABILITIES):
        raise ManifestError("REQUIRED_CAPABILITY_MISSING")
    expected_endpoints = [
        ADVISORY_ENDPOINTS[endpoint_id]
        for endpoint_id in profile.ADVISORY_ENDPOINT_IDS
    ]
    if manifest["advisoryEndpoints"] != expected_endpoints:
        raise ManifestError("ADVISORY_UNAVAILABLE")
    contracts = manifest["contracts"]
    expected_contracts = {
        "vdpCompatibility": VDP_CONTRACT,
        "vehicleHardware": HARDWARE_PROFILE,
        "vissTrustTelemetry": VISS_CONTRACT,
    }
    if profile.ADVISORY_ENDPOINT_IDS:
        expected_contracts["typedQmAdvisory"] = ADVISORY_CONTRACT
    if contracts != expected_contracts:
        raise ManifestError("CONTRACT_DIGEST_MISMATCH")
