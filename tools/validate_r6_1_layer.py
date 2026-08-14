#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate the R6.1-2 Yocto bootstrap layer contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "meta-aos-vehicle-platform"
SM_CONFIG = LAYER / "recipes-aos/aos-servicemanager/files/sm.cfg"
RUNTIME = (
    LAYER
    / "recipes-aos/aos-servicemanager/files/systemd-slot-component/runtime.cpp"
)
PATCH = (
    LAYER
    / "recipes-aos/aos-servicemanager/files/0001-add-production-systemd-slot-component-runtime.patch"
)
UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider.service"
)
TMPFILES = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider.conf"
)
POLICY = LAYER / "recipes-security/refpolicy/files/vehicle_data_provider.te"
POLICY_APPEND = LAYER / "recipes-security/refpolicy/refpolicy-aos_git.bbappend"
COMPONENT_ROOT = "/var/aos/workdirs/sm/runtimes/systemd-slot-component"
COMPONENT_TYPE = "vehicle-data-provider"


class LayerError(ValueError):
    """Raised when the bootstrap layer violates its accepted boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LayerError(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise LayerError(f"cannot read {path.relative_to(ROOT)}: {error}") from error


def validate_layer() -> None:
    layer_conf = read(LAYER / "conf/layer.conf")
    require(
        'LAYERSERIES_COMPAT_aos-vehicle-platform = "scarthgap"' in layer_conf,
        "layer is not locked to scarthgap",
    )
    require(
        'BBFILE_PRIORITY_aos-vehicle-platform = "20"' in layer_conf,
        "layer priority changed",
    )

    try:
        config = json.loads(read(SM_CONFIG))
    except json.JSONDecodeError as error:
        raise LayerError(f"Service Manager configuration is invalid: {error}") from error
    runtimes = config.get("runtimes")
    require(isinstance(runtimes, list), "Service Manager runtimes are missing")
    provider = [item for item in runtimes if item.get("plugin") == "systemd-slot-component"]
    require(len(provider) == 1, "exactly one provider component runtime is required")
    provider = provider[0]
    require(provider.get("type") == COMPONENT_TYPE, "provider type changed")
    require(provider.get("isComponent") is True, "provider is not a component")
    runtime_config = provider.get("config")
    require(isinstance(runtime_config, dict), "provider runtime config is missing")
    require(runtime_config.get("workingDir") == COMPONENT_ROOT, "component root changed")
    require(runtime_config.get("layoutVersion") == 1, "layout version changed")
    require(
        runtime_config.get("unit") == "aos-vehicle-data-provider.service",
        "provider unit changed",
    )
    rendered_config = json.dumps(config)
    require("qualificationMode" not in rendered_config, "qualification probe leaked into image")
    require("bootx64.efi" not in rendered_config, "ARM64 image contains the x86 bootloader path")
    require("bootaa64.efi" in rendered_config, "ARM64 bootloader path is missing")

    patch = read(PATCH)
    require("SystemdSlotComponentRuntime" in patch, "runtime factory patch is missing")
    require("qualification" not in patch.lower(), "qualification patch is selected")
    require("src/cm/" not in patch, "factory patch changes Communication Manager tests")

    runtime = read(RUNTIME)
    require("EnsureEmptyStore" in runtime, "empty-store bootstrap is missing")
    require(
        "atomic component lifecycle is deferred to R6.1-3" in runtime,
        "lifecycle gate is missing",
    )
    require("eNotSupported" in runtime, "bootstrap runtime does not fail closed")

    unit = read(UNIT)
    require("DynamicUser=yes" in unit, "provider unit lacks DynamicUser")
    require("ConditionFileIsExecutable=" in unit, "provider executable condition is missing")
    require("ProtectSystem=strict" in unit, "provider unit does not protect rootfs")
    require("CapabilityBoundingSet=\n" in unit, "provider capabilities are not empty")
    install_section = unit.split("[Install]", 1)[1]
    require("WantedBy=" not in install_section, "provider unit must not be enabled")

    tmpfiles = read(TMPFILES)
    require(COMPONENT_ROOT in tmpfiles, "persistent component root is missing")
    require(f"{COMPONENT_ROOT}/active" not in tmpfiles, "bootstrap creates an active slot")
    require(
        f"{COMPONENT_ROOT}/credentials 0700" in tmpfiles,
        "credential boundary is not private",
    )

    policy = read(POLICY)
    require("vehicle_data_provider_t" in policy, "provider SELinux domain is missing")
    require("vehicle_data_provider_store_t" in policy, "provider store type is missing")
    require("manage_dirs_pattern(aos_t" in policy, "Service Manager cannot own the store")
    require("permissive" not in policy, "provider SELinux policy is permissive")

    policy_append = read(POLICY_APPEND)
    require(
        "do_compile:prepend()" in policy_append,
        "provider policy is not installed by a shell compile task",
    )
    require(
        "do_patch:append()" not in policy_append,
        "provider policy shell commands are appended to the Python patch task",
    )

    all_text = "\n".join(read(path) for path in LAYER.rglob("*") if path.is_file())
    for forbidden in (
        "BEGIN PRIVATE KEY",
        "BEGIN CERTIFICATE",
        "qualificationMode",
        "/Users/",
        "alex_agizim@epam.com",
    ):
        require(forbidden not in all_text, f"layer contains forbidden data: {forbidden}")


def main() -> int:
    try:
        validate_layer()
    except LayerError as error:
        print(f"R6.1 Yocto layer validation failed: {error}", file=sys.stderr)
        return 1
    print("R6.1 Yocto bootstrap layer validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
