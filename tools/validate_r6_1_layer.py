#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate the R6.1 atomic component lifecycle Yocto layer contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYER = ROOT / "meta-aos-vehicle-platform"
SM_CONFIG = LAYER / "recipes-aos/aos-servicemanager/files/sm.cfg"
SERVICE_MANAGER_APPEND = (
    LAYER / "recipes-aos/aos-servicemanager/aos-servicemanager_git.bbappend"
)
RUNTIME = (
    LAYER
    / "recipes-aos/aos-servicemanager/files/systemd-slot-component/runtime.cpp"
)
PATCH = (
    LAYER
    / "recipes-aos/aos-servicemanager/files/0001-add-production-systemd-slot-component-runtime.patch"
)
ARCHIVE = (
    LAYER
    / "recipes-aos/aos-servicemanager/files/systemd-slot-component/providerarchive.hpp"
)
UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider.service"
)
SELFTEST_UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider-selftest@.service"
)
PLATFORM_RECIPE = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/"
    "aos-vehicle-data-provider-platform_0.1.0.bb"
)
LAUNCHER = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider-launcher.c"
)
HEALTH_ADAPTER = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider-health"
)
TMPFILES = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/aos-vehicle-data-provider.conf"
)
STORE_PREPARE = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store-prepare"
)
LOOP_HELPER = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-loop.c"
)
STORE_LAYOUT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store-layout"
)
STORE_CHECK = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store-check"
)
STORE_PREPARE_UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store-prepare.service"
)
STORE_ATTACH_UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store-attach.service"
)
STORE_LAYOUT_UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store-layout.service"
)
STORE_MOUNT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-store.mount"
)
STORE_BOOTSTRAP_UNIT = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-bootstrap.service"
)
STORE_MODULES_LOAD = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "aos-vehicle-data-provider-loop.conf"
)
PLATFORM_RECIPE = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/"
    "aos-vehicle-data-provider-platform_0.1.0.bb"
)
SM_DROP_IN = (
    LAYER
    / "recipes-aos/aos-vehicle-data-provider-platform/files/"
    "30-aos-vehicle-data-provider.conf"
)
POLICY = LAYER / "recipes-security/refpolicy/files/vehicle_data_provider.te"
POLICY_FC = LAYER / "recipes-security/refpolicy/files/vehicle_data_provider.fc"
POLICY_APPEND = LAYER / "recipes-security/refpolicy/refpolicy-aos_git.bbappend"
COMPONENT_ROOT = "/var/aos/workdirs/sm/runtimes/systemd-slot-component"
STORE_BACKING = "/var/aos/workdirs/sm/runtimes/.vehicle-data-provider-store.ext4"
STORE_SIZE = 536870912
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

    service_manager_append = read(SERVICE_MANAGER_APPEND)
    require(
        "-DWITH_TEST=ON" in service_manager_append,
        "ARM64 runtime qualifier is not a reproducible build output",
    )
    require(
        'DEPENDS:append = " softhsm"' in service_manager_append,
        "ARM64 test-only SoftHSM dependency is not declared",
    )
    require(
        "-DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST"
        in service_manager_append,
        "cross-compiled test discovery is not deferred to the ARM64 VM",
    )
    require(
        'find "${D}${prefix}/usr" -depth -delete' in service_manager_append,
        "test-only CMake staging data can leak into production packages",
    )

    patch = read(PATCH)
    require("SystemdSlotComponentRuntime" in patch, "runtime factory patch is missing")
    require("qualification" not in patch.lower(), "qualification patch is selected")
    require("src/cm/" not in patch, "factory patch changes Communication Manager tests")
    require(
        "ValidateProviderArchive" in patch,
        "Image Manager does not preflight the provider archive",
    )
    require(
        "cProviderLayerMediaType" in patch,
        "provider-specific OCI media type is not wired into Image Manager",
    )

    archive = read(ARCHIVE)
    for token in (
        "application/vnd.aos.vehicle-data-provider.layer.v1.tar",
        "ValidateChecksum",
        "ValidatePath",
        "provider archive contains a link or special file",
        "provider archive contains a duplicate path",
        "provider archive permissions are unsafe",
        "provider archive path is bootstrap-reserved",
    ):
        require(token in archive, f"provider archive preflight is missing: {token}")

    runtime = read(RUNTIME)
    for field, value in (
        ("healthAdapter", "/usr/libexec/aos-vehicle-data-provider-health"),
        ("maxPayloadBytes", 536870912),
        ("minimumFreeBytes", 134217728),
        ("startTimeoutSeconds", 30),
        ("stopTimeoutSeconds", 15),
    ):
        require(runtime_config.get(field) == value, f"{field} changed")

    for token in (
        "ComponentTransactionPhase::ePrepared",
        "ComponentTransactionPhase::eUnavailable",
        "ComponentTransactionPhase::ePreviousStopped",
        "ComponentTransactionPhase::eSwitched",
        "ComponentTransactionPhase::eCandidateStarted",
        "ValidateAndCopyPayload",
        "OfflineSelfTest",
        "MarkUnavailable",
        "StopProvider",
        "SwitchActive",
        "StartProvider",
        "CheckHealth",
        "Rollback",
        "SaveTransaction",
        "SaveRelease",
        "RemoveStateFile",
    ):
        require(token in runtime, f"atomic lifecycle operation is missing: {token}")
    require("EnsureEmptyStore" not in runtime, "obsolete empty-store runtime remains")
    require(
        "atomic component lifecycle is deferred" not in runtime,
        "obsolete lifecycle deferral remains",
    )
    require("RebootRequired" not in runtime, "component lifecycle requests a Node reboot")

    profile = read(
        LAYER
        / "recipes-aos/aos-servicemanager/files/systemd-slot-component/providerprofile.cpp"
    )
    for operation in ("offline", "unavailable", "active"):
        require(f'RunAdapter("{operation}"' in profile, f"{operation} profile call is missing")
    require("StartUnit(" in profile, "provider start is not delegated to systemd")
    require("StopUnit(" in profile, "provider stop is not delegated to systemd")

    health = read(HEALTH_ADAPTER)
    for operation in ("offline)", "unavailable)", "active)"):
        require(operation in health, f"health adapter operation is missing: {operation}")
    require(
        "aos-vehicle-data-provider-selftest@$slot.service" in health,
        "sandboxed offline provider self-test is missing",
    )
    require(
        'systemctl reload "$unit"' in health,
        "sandboxed fail-safe unavailability call is missing",
    )
    require(
        "/bin/vehicle-data-provider\" --" not in health,
        "health adapter executes provider payload directly",
    )
    require(
        "run_bounded 5 systemctl is-active" in health,
        "active provider health gate is missing or unbounded",
    )
    require("run_bounded" in health, "provider helper calls are not bounded")
    require("timeout " not in health, "unavailable timeout binary leaked into profile")

    unit = read(UNIT)
    require("Type=notify" in unit, "provider readiness is process-only")
    require("NotifyAccess=main" in unit, "provider readiness sender is ambiguous")
    require("User=aos-vdp" in unit, "provider unit lacks the dedicated runtime user")
    require("Group=aos-vdp" in unit, "provider unit lacks the dedicated runtime group")
    require(
        "ExecStart=/usr/libexec/aos-vehicle-data-provider-launcher" in unit,
        "provider launcher does not receive the systemd runtime identity",
    )
    require("NoNewPrivileges=" not in unit, "systemd suppresses the SELinux transition")
    require("ConditionFileIsExecutable=" in unit, "provider executable condition is missing")
    require("ProtectSystem=strict" in unit, "provider unit does not protect rootfs")
    require(
        "CapabilityBoundingSet=\n" in unit,
        "provider launcher retains a Linux capability",
    )
    require(
        "ExecReload=/bin/kill -HUP $MAINPID" in unit,
        "provider unavailability signal hook is missing",
    )
    require(
        "After=network-online.target kuksa-databroker.service" in unit,
        "provider does not retain deterministic KUKSA startup ordering",
    )
    require(
        "Wants=network-online.target kuksa-databroker.service" in unit,
        "provider does not request KUKSA without coupling its lifecycle",
    )
    require(
        "Requires=kuksa-databroker.service" not in unit,
        "provider is incorrectly stopped with the KUKSA dependency",
    )
    for token in (
        "AOS_VEHICLE_DATA_PROVIDER_CONFIGURATION="
        f"{COMPONENT_ROOT}/configuration/provider.json",
        "AOS_VEHICLE_DATA_PROVIDER_VISS_CA="
        f"{COMPONENT_ROOT}/trust/viss-ca.pem",
        "LoadCredential=kuksa-token:"
        f"{COMPONENT_ROOT}/credentials/kuksa-token",
    ):
        require(token in unit, f"provider platform boundary is missing: {token}")
    install_section = unit.split("[Install]", 1)[1]
    require("WantedBy=" not in install_section, "provider unit must not be enabled")

    selftest_unit = read(SELFTEST_UNIT)
    require("Type=oneshot" in selftest_unit, "provider self-test is not one-shot")
    require("User=aos-vdp" in selftest_unit, "provider self-test user changed")
    require("Group=aos-vdp" in selftest_unit, "provider self-test group changed")
    require(
        "ExecStart=/usr/libexec/aos-vehicle-data-provider-launcher --self-test %i"
        in selftest_unit,
        "provider self-test bypasses the audited identity-check launcher",
    )
    require(
        "NoNewPrivileges=" not in selftest_unit,
        "self-test systemd no_new_privs suppresses the SELinux transition",
    )
    require("PrivateNetwork=yes" in selftest_unit, "provider self-test has network access")
    require(
        "CapabilityBoundingSet=\n" in selftest_unit,
        "provider self-test retains a Linux capability",
    )
    require("[Install]" not in selftest_unit, "provider self-test must not be enabled")

    platform_recipe = read(PLATFORM_RECIPE)
    require(
        "inherit systemd useradd" in platform_recipe,
        "provider runtime account is not image-owned",
    )
    require(
        "--system --home /nonexistent --no-create-home --shell /bin/false aos-vdp"
        in platform_recipe,
        "provider runtime account is not fail-closed",
    )

    launcher = read(LAUNCHER)
    require("--self-test" in launcher, "launcher self-test mode is missing")
    require("--mark-unavailable" in launcher, "launcher reload mode is missing")
    require('runtime_user = "aos-vdp"' in launcher, "launcher runtime user changed")
    require("PR_SET_NO_NEW_PRIVS" in launcher, "launcher does not set no_new_privs")
    require("getgroups(1, &supplementary_group)" in launcher,
            "launcher does not verify supplementary groups")
    require("initgroups" not in launcher, "launcher still depends on an NSS group expansion")
    require("setgroups" not in launcher, "launcher still changes supplementary groups")
    require("setresgid" not in launcher, "launcher still changes its runtime group")
    require("setresuid" not in launcher, "launcher still changes its runtime user")
    require("launcher did not receive the dedicated runtime identity" in launcher,
            "launcher does not fail closed on the systemd identity")
    require("PR_GET_NO_NEW_PRIVS" in launcher, "launcher does not verify no_new_privs")
    require("SYS_capget" in launcher, "launcher does not verify cleared capabilities")
    require(
        "runtime capabilities were not cleared" in launcher,
        "launcher capability failure is not fail-closed",
    )
    require(
        launcher.index("getgroups(1, &supplementary_group)")
        < launcher.index("PR_SET_NO_NEW_PRIVS")
        < launcher.index("SYS_capget")
        < launcher.index("execv(executable"),
        "launcher identity-verification order changed",
    )

    tmpfiles = read(TMPFILES)
    require(COMPONENT_ROOT in tmpfiles, "persistent component root is missing")
    require(f"{COMPONENT_ROOT}/active" not in tmpfiles, "bootstrap creates an active slot")
    require(
        f"{COMPONENT_ROOT}/credentials 0700" in tmpfiles,
        "credential boundary is not private",
    )
    require(
        f"{COMPONENT_ROOT}/configuration 0755" in tmpfiles,
        "vehicle integration configuration boundary is missing",
    )
    require(
        f"{COMPONENT_ROOT}/trust 0755" in tmpfiles,
        "vehicle trust boundary is missing",
    )

    store_prepare = read(STORE_PREPARE)
    for token in (
        "set -eu",
        f"store_mount={COMPONENT_ROOT}",
        f"backing_file={STORE_BACKING}",
        f"store_size={STORE_SIZE}",
        "minimum_remaining=536870912",
        "store_label=aos-vdp-store",
        "context=system_u:object_r:aos_var_run_t:s0",
        'dd if=/dev/zero of="$partial_file" bs=1048576 count=512',
        "conv=fsync status=none",
        "-E nodiscard,lazy_itable_init=0,lazy_journal_init=0",
        "e2fsck -p \"$backing_file\"",
        "require_fully_allocated",
        "store identity exists without a recoverable image",
        "partial store identity requires manual reconciliation",
        "mv \"$partial_file\" \"$backing_file\"",
        "store backing file is sparse or incompletely allocated",
        'store_parent_options=$(findmnt -rn -T "$store_parent" -o OPTIONS)',
        "store parent is not writable",
        "store image is already attached before preparation",
    ):
        require(token in store_prepare, f"store preparation contract is missing: {token}")
    require("AOS_" not in store_prepare, "store preparation accepts environment overrides")
    require(
        "fail 'workdirs is not writable'" not in store_prepare,
        "store preparation tests the intentionally read-only sandbox parent",
    )
    require(
        'rm -f -- "$partial_file"' in store_prepare,
        "interrupted partial store recovery is missing",
    )
    require(
        not re.search(r"rm[^\n]*\$backing_file", store_prepare),
        "store preparation can remove the committed backing file",
    )
    require(
        not re.search(r"mkfs[^\n]*\$backing_file", store_prepare),
        "store preparation can reformat the committed backing file",
    )

    loop_helper = read(LOOP_HELPER)
    for token in (
        "#define BACKING_FILE",
        f'    "{STORE_BACKING}"',
        f"#define BACKING_SIZE UINT64_C({STORE_SIZE})",
        "#define MAX_LOOP_DEVICES 256",
        "O_NOFOLLOW",
        "LOOP_CTL_GET_FREE",
        "LOOP_SET_FD",
        "LOOP_SET_STATUS64",
        "LOOP_CLR_FD",
        "st_blocks",
        '#define RUNTIME_DIRECTORY "/run/aos-vehicle-data-provider-store"',
        '#define RUNTIME_LINK "loop"',
        'symlinkat(target, directory, RUNTIME_LINK_PARTIAL)',
        'renameat(directory, RUNTIME_LINK_PARTIAL, directory, RUNTIME_LINK)',
        'unlinkat(runtimeDirectory, RUNTIME_LINK, 0)',
        'strcmp(argv[1], "attach")',
        'strcmp(argv[1], "detach")',
    ):
        require(token in loop_helper, f"fixed loop helper contract is missing: {token}")
    require(
        "argv[2]" not in loop_helper,
        "fixed loop helper accepts a caller-controlled backing path",
    )
    require(
        "system(" not in loop_helper and "exec" not in loop_helper,
        "fixed loop helper delegates privileged behavior to another program",
    )

    store_check = read(STORE_CHECK)
    for token in (
        f"store={COMPONENT_ROOT}",
        f"backing_file={STORE_BACKING}",
        f"store_size={STORE_SIZE}",
        "component store does not use a loop device",
        "runtime_loop=/run/aos-vehicle-data-provider-store/loop",
        "component mount does not use the fixed runtime loop identity",
        "store backing file is sparse or incompletely allocated",
        "store identity has an unexpected number of fields",
        "context=system_u:object_r:vehicle_data_provider_store_t:s0",
        "systemd-tmpfiles --create /usr/lib/aos-vehicle-data-provider/store.conf",
        "backend=loop-ext4",
        "vehicle_data_provider_store_t",
    ):
        require(token in store_check, f"store activation check is missing: {token}")
    require(
        not re.search(r"blkid[^\n]*\$backing_file", store_check),
        "generic filesystem administration reads the Aos backing file",
    )
    require(
        'blkid -p -s UUID -o value "$mount_source"' in store_check,
        "post-mount identity is not checked through the mounted loop device",
    )
    require(
        "losetup" not in store_check,
        "post-mount validation scans the generic-labelled backing file",
    )
    require("AOS_" not in store_check, "store check accepts environment overrides")
    require(
        f"Z {COMPONENT_ROOT}" not in tmpfiles,
        "fixed-context store must not request an unsupported inode relabel",
    )

    prepare_unit = read(STORE_PREPARE_UNIT)
    for token in (
        "DefaultDependencies=no",
        "Requires=var-aos-workdirs.mount aos-vehicle-data-provider-store-layout.service",
        "After=var-aos-workdirs.mount systemd-modules-load.service "
        "aos-vehicle-data-provider-store-layout.service",
        "ConditionPathIsMountPoint=/var/aos/workdirs",
        "ExecStart=/usr/libexec/aos-vehicle-data-provider-store-prepare prepare",
        "ProtectSystem=strict",
        "ReadWritePaths=/var/aos/workdirs/sm/runtimes",
        "CapabilityBoundingSet=\n",
        "AmbientCapabilities=",
    ):
        require(token in prepare_unit, f"store preparation unit is missing: {token}")
    require(
        "PrivateDevices=yes" not in prepare_unit,
        "store preparation cannot validate the real workdirs device through PrivateDevices",
    )
    require(
        "PrivateTmp=yes" not in prepare_unit,
        "store preparation cannot depend on post-local-fs tmpfiles setup",
    )
    require("CAP_SYS_ADMIN" not in prepare_unit, "store image preparation is privileged")

    attach_unit = read(STORE_ATTACH_UNIT)
    for token in (
        "DefaultDependencies=no",
        "Requires=aos-vehicle-data-provider-store-prepare.service",
        "After=aos-vehicle-data-provider-store-prepare.service systemd-modules-load.service",
        "ConditionPathIsMountPoint=/var/aos/workdirs",
        "ExecStart=/usr/libexec/aos-vehicle-data-provider-loop attach",
        "ExecStop=/usr/libexec/aos-vehicle-data-provider-loop detach",
        "RuntimeDirectory=aos-vehicle-data-provider-store",
        "RuntimeDirectoryMode=0750",
        "RuntimeDirectoryPreserve=restart",
        "ProtectSystem=strict",
        "ReadWritePaths=/var/aos/workdirs/sm/runtimes "
        "/run/aos-vehicle-data-provider-store",
        "CapabilityBoundingSet=CAP_SYS_ADMIN",
        "AmbientCapabilities=",
    ):
        require(token in attach_unit, f"store loop attach unit is missing: {token}")
    require(
        "NoNewPrivileges=yes" not in attach_unit,
        "store loop attach blocks its dedicated SELinux domain transition",
    )

    store_layout = read(STORE_LAYOUT)
    for token in (
        "set -eu",
        "workdirs=/var/aos/workdirs",
        "expected_device=/dev/aosvg/workdirs",
        "service_manager_root=/var/aos/workdirs/sm",
        "runtime_root=/var/aos/workdirs/sm/runtimes",
        'ensure_directory "$service_manager_root" 0755',
        'ensure_directory "$runtime_root" 0755',
        "workdirs is not a distinct mount point",
        "workdirs source device is unexpected",
    ):
        require(token in store_layout, f"store parent layout contract is missing: {token}")
    require("AOS_" not in store_layout, "store layout accepts environment overrides")
    require("rm " not in store_layout, "store layout can remove persistent state")

    layout_unit = read(STORE_LAYOUT_UNIT)
    for token in (
        "DefaultDependencies=no",
        "Requires=var-aos-workdirs.mount",
        "After=var-aos-workdirs.mount",
        "Before=aos-vehicle-data-provider-store-prepare.service "
        "aos-vehicle-data-provider-bootstrap.service aos-sm.service",
        "ConditionPathIsMountPoint=/var/aos/workdirs",
        "ExecStart=/usr/libexec/aos-vehicle-data-provider-store-layout",
        "ProtectSystem=strict",
        "ReadWritePaths=/var/aos/workdirs",
        "CapabilityBoundingSet=\n",
        "AmbientCapabilities=\n",
    ):
        require(token in layout_unit, f"store parent layout unit is missing: {token}")
    require("CAP_SYS_ADMIN" not in layout_unit, "store layout unit is privileged")

    store_mount = read(STORE_MOUNT)
    for token in (
        "DefaultDependencies=no",
        "Requires=aos-vehicle-data-provider-store-attach.service",
        "Conflicts=umount.target",
        "Before=aos-vehicle-data-provider-bootstrap.service aos-sm.service umount.target",
        "What=/run/aos-vehicle-data-provider-store/loop",
        f"Where={COMPONENT_ROOT}",
        "Type=ext4",
        "Options=nodev,nosuid,noatime,errors=remount-ro,"
        "context=system_u:object_r:vehicle_data_provider_store_t:s0",
        "TimeoutSec=30s",
    ):
        require(token in store_mount, f"isolated store mount is missing: {token}")
    require("noexec" not in store_mount, "provider store is not executable")
    require("Options=loop," not in store_mount, "mount unit allocates a second loop device")

    bootstrap_unit = read(STORE_BOOTSTRAP_UNIT)
    require(
        f"RequiresMountsFor={COMPONENT_ROOT}" in bootstrap_unit,
        "provider bootstrap does not require the isolated store mount",
    )
    require(
        f"ConditionPathIsMountPoint={COMPONENT_ROOT}" in bootstrap_unit,
        "provider bootstrap does not fail closed without the isolated store",
    )
    require(
        "ExecStart=/usr/libexec/aos-vehicle-data-provider-store-check"
        in bootstrap_unit,
        "provider bootstrap does not validate the isolated store",
    )
    sm_drop_in = read(SM_DROP_IN)
    require(
        "Requires=aos-vehicle-data-provider-bootstrap.service" in sm_drop_in,
        "Service Manager does not fail closed on store bootstrap",
    )
    require(
        read(STORE_MODULES_LOAD).splitlines()[-1] == "loop",
        "steady-state loop module is not selected exactly once",
    )

    platform_recipe = read(PLATFORM_RECIPE)
    for dependency in (
        "coreutils",
        "e2fsprogs-e2fsck",
        "e2fsprogs-mke2fs",
        "kernel-module-loop",
        "util-linux-blkid",
        "util-linux-losetup",
    ):
        require(dependency in platform_recipe, f"store dependency is missing: {dependency}")
    for source in (
        "aos-vehicle-data-provider-store-prepare.service",
        "aos-vehicle-data-provider-store-attach.service",
        "aos-vehicle-data-provider-store-layout.service",
        "aos-vehicle-data-provider-store.mount",
        "aos-vehicle-data-provider-store-layout",
        "aos-vehicle-data-provider-store-prepare",
        "aos-vehicle-data-provider-store-check",
        "aos-vehicle-data-provider-loop.c",
        "aos-vehicle-data-provider-loop.conf",
    ):
        require(f"file://{source}" in platform_recipe, f"store source is missing: {source}")
    require(
        "var-aos-workdirs-sm-runtimes-systemd\\x2dslot\\x2dcomponent.mount"
        in platform_recipe,
        "path-derived component mount unit is not installed",
    )
    require(
        "${libdir}/aos-vehicle-data-provider/store.conf" in platform_recipe,
        "store layout is not isolated from global tmpfiles processing",
    )
    require(
        "${WORKDIR}/aos-vehicle-data-provider-loop.c" in platform_recipe
        and "${B}/aos-vehicle-data-provider-loop" in platform_recipe
        and "${libexecdir}/aos-vehicle-data-provider-loop" in platform_recipe,
        "fixed loop helper is not compiled, installed, and packaged",
    )
    require(
        "${nonarch_libdir}/tmpfiles.d/aos-vehicle-data-provider.conf"
        not in platform_recipe,
        "store layout can run before its isolated mount is active",
    )

    policy = read(POLICY)
    require("vehicle_data_provider_t" in policy, "provider SELinux domain is missing")
    require("vehicle_data_provider_store_t" in policy, "provider store type is missing")
    require("manage_dirs_pattern(aos_t" in policy, "Service Manager cannot own the store")
    require(
        "allow vehicle_data_provider_t aos_var_run_t:dir search;" in policy,
        "provider cannot traverse the fixed-context parent directories",
    )
    require(
        "init_rw_script_stream_sockets(systemd_modules_load_t)" in policy,
        "steady-state module loading cannot use its inherited init script socket",
    )
    for token in (
        "allow vehicle_data_provider_t self:process getcap;",
        "allow vehicle_data_provider_t self:fifo_file rw_fifo_file_perms;",
        "init_rw_script_stream_sockets(vehicle_data_provider_t)",
        "sysnet_dns_name_resolve(vehicle_data_provider_t)",
        "dev_read_urand(vehicle_data_provider_t)",
        "allow vehicle_data_provider_t initrc_runtime_t:dir { getattr search };",
        "allow vehicle_data_provider_t initrc_runtime_t:file { getattr open read };",
    ):
        require(token in policy, f"provider launcher policy is missing: {token}")
    require(
        "allow vehicle_data_provider_t self:capability" not in policy,
        "provider domain retains a Linux capability permission",
    )
    require(
        "systemd_tmpfilesd_managed(vehicle_data_provider_store_t)" not in policy,
        "global tmpfiles retains unnecessary provider-store management access",
    )
    credential_rules = [
        line.strip()
        for line in policy.splitlines()
        if "vehicle_data_provider_t initrc_runtime_t:" in line
    ]
    require(
        credential_rules
        == [
            "allow vehicle_data_provider_t initrc_runtime_t:dir { getattr search };",
            "allow vehicle_data_provider_t initrc_runtime_t:file { getattr open read };",
        ],
        "provider credential access is broader than the reviewed read-only rules",
    )
    broad_parent_rules = [
        line.strip()
        for line in policy.splitlines()
        if "vehicle_data_provider_t aos_var_run_t:" in line
    ]
    require(
        broad_parent_rules
        == ["allow vehicle_data_provider_t aos_var_run_t:dir search;"],
        "provider has broader access to general Aos workdirs than directory search",
    )
    require("permissive" not in policy, "provider SELinux policy is permissive")
    for token in (
        "type vehicle_data_provider_store_prepare_t;",
        "type vehicle_data_provider_store_prepare_exec_t;",
        "init_daemon_domain(vehicle_data_provider_store_prepare_t, "
        "vehicle_data_provider_store_prepare_exec_t)",
        "fstools_exec(vehicle_data_provider_store_prepare_t)",
        "init_rw_script_stream_sockets(vehicle_data_provider_store_prepare_t)",
        "kernel_read_system_state(vehicle_data_provider_store_prepare_t)",
        "allow vehicle_data_provider_store_prepare_t self:fifo_file "
        "rw_fifo_file_perms;",
        "manage_files_pattern(vehicle_data_provider_store_prepare_t, "
        "aos_var_run_t, aos_var_run_t)",
        "type vehicle_data_provider_store_admin_t;",
        "type vehicle_data_provider_store_admin_exec_t;",
        "init_daemon_domain(vehicle_data_provider_store_admin_t, "
        "vehicle_data_provider_store_admin_exec_t)",
        "allow vehicle_data_provider_store_admin_t self:capability sys_admin;",
        "allow vehicle_data_provider_store_admin_t aos_var_run_t:dir search;",
        "allow vehicle_data_provider_store_admin_t aos_var_run_t:file "
        "{ getattr ioctl lock open read write };",
        "allow vehicle_data_provider_store_admin_t "
        "aos_var_run_t:filesystem getattr;",
        "init_rw_script_stream_sockets(vehicle_data_provider_store_admin_t)",
        "dev_rw_loop_control(vehicle_data_provider_store_admin_t)",
        "storage_raw_rw_fixed_disk(vehicle_data_provider_store_admin_t)",
        "type vehicle_data_provider_store_runtime_t;",
        "files_runtime_file(vehicle_data_provider_store_runtime_t)",
        "manage_lnk_files_pattern(vehicle_data_provider_store_admin_t, "
        "vehicle_data_provider_store_runtime_t, vehicle_data_provider_store_runtime_t)",
        "allow mount_t vehicle_data_provider_store_runtime_t:dir search;",
        "allow mount_t vehicle_data_provider_store_runtime_t:lnk_file "
        "read_lnk_file_perms;",
        "allow mount_t vehicle_data_provider_store_t:filesystem relabelfrom;",
        "allow vehicle_data_provider_store_prepare_t "
        "aos_var_run_t:filesystem getattr;",
        "allow vehicle_data_provider_store_prepare_t "
        "loop_control_device_t:chr_file getattr;",
        "allow vehicle_data_provider_store_prepare_t sysfs_t:dir read;",
        "allow vehicle_data_provider_store_prepare_t sysfs_t:file read;",
        "allow vehicle_data_provider_store_prepare_t sysfs_t:lnk_file read;",
    ):
        require(token in policy, f"fixed loop helper policy is missing: {token}")
    require(
        "mount_t aos_var_run_t" not in policy,
        "generic mount domain can access the Aos workdirs backing file",
    )
    require(
        "/usr/libexec/aos-vehicle-data-provider-store-prepare -- "
        "gen_context(system_u:object_r:"
        "vehicle_data_provider_store_prepare_exec_t,s0)"
        in read(POLICY_FC),
        "fixed store preparation script does not enter its dedicated SELinux domain",
    )
    require(
        "/usr/libexec/aos-vehicle-data-provider-loop -- "
        "gen_context(system_u:object_r:vehicle_data_provider_store_admin_exec_t,s0)"
        in read(POLICY_FC),
        "fixed loop helper does not enter its dedicated SELinux domain",
    )
    require(
        "/run/aos-vehicle-data-provider-store(/.*)? "
        "gen_context(system_u:object_r:vehicle_data_provider_store_runtime_t,s0)"
        in read(POLICY_FC),
        "fixed runtime loop identity does not have a dedicated SELinux type",
    )
    require(
        "init_read_runtime_files(vehicle_data_provider_t)" in policy,
        "provider policy is not compatible with the pinned refpolicy runtime interface",
    )
    require(
        "init_dgram_send(vehicle_data_provider_t)" in policy,
        "provider cannot report readiness to systemd",
    )
    require(
        "init_read_runtime(vehicle_data_provider_t)" not in policy,
        "provider policy uses an unavailable refpolicy runtime interface",
    )
    require(
        "class service { start stop status reload };" in policy,
        "provider policy does not declare its systemd service permissions",
    )
    require(
        "aos-vehicle-data-provider-health" not in read(
            POLICY_FC
        ),
        "health controller incorrectly transitions into the payload domain",
    )

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
    print("R6.1 Yocto atomic component lifecycle validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
