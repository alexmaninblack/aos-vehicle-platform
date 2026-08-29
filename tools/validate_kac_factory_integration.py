#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate the bounded KAC Factory source integration without a target build."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "authorization/aos-kuksa-factory-integration"
RECIPE_DIR = ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-kuksa-factory-integration"
RECIPE = RECIPE_DIR / "aos-kuksa-factory-integration_0.1.0.bb"
FILES = RECIPE_DIR / "files"
PORT_POLICY_PATCH = ROOT / (
    "meta-aos-vehicle-platform/recipes-security/refpolicy/files/"
    "0001-corenetwork-label-aos-kuksa-iam-port.patch"
)
KUKSA_RECIPE_APPEND = ROOT / (
    "meta-aos-vehicle-platform/recipes-connectivity/kuksa-databroker/"
    "kuksa-databroker_%.bbappend"
)
AUTH_FILES = ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-kuksa-auth-compat/files"


class ValidationError(RuntimeError):
    pass


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ValidationError(f"{label}: missing {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise ValidationError(f"{label}: forbidden {needle!r}")


def validate() -> None:
    required = [
        FACTORY / "CMakeLists.txt",
        FACTORY / "include/factory/integration.hpp",
        FACTORY / "src/token_init.cpp",
        FACTORY / "src/runtime_cleanup.cpp",
        FACTORY / "src/tls_prepare.cpp",
        FACTORY / "tests/factory_integration_tests.cpp",
        RECIPE,
        FILES / "aos-kuksa-substrate.target",
        FILES / "aos-kuksa-provision-reset.service",
        FILES / "aos-kuksa-token-init.service",
        FILES / "aos-kuksa-tls-prepare.service",
        FILES / "aos-kuksa-runtime-cleanup.service",
        FILES / "aos-iam-prov.service.d/20-kuksa-token-init.conf",
        FILES / "aos-iam.service.d/20-kuksa-token-init.conf",
        FILES / "kuksa-databroker.service.d/20-kuksa-verifier.conf",
        FILES / "aos-vehicle-data-provider.service.d/20-kuksa-provider.conf",
        PORT_POLICY_PATCH,
        KUKSA_RECIPE_APPEND,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise ValidationError("missing Factory files: " + ", ".join(missing))

    recipe = RECIPE.read_text(encoding="utf-8")
    require(recipe, 'DEPENDS = "openssl softhsm"', "Factory recipe")
    require(
        recipe,
        'RDEPENDS:${PN} = "aos-deprov aos-iamanager aos-kuksa-auth-compat aos-servicemanager aos-vehicle-data-provider-platform coreutils kuksa-databroker softhsm"',
        "Factory recipe",
    )
    for executable in (
        "aos-kuksa-token-init",
        "aos-kuksa-tls-prepare",
        "aos-kuksa-runtime-cleanup",
    ):
        require(recipe, executable, "Factory recipe")
    for forbidden in ("AUTOREV", "do_rootfs", "aos-image-vm", "PACKAGES +="):
        forbid(recipe, forbidden, "Factory recipe")

    reset = (FILES / "aos-kuksa-provision-reset.service").read_text(encoding="utf-8")
    init = (FILES / "aos-kuksa-token-init.service").read_text(encoding="utf-8")
    cleanup = (FILES / "aos-kuksa-runtime-cleanup.service").read_text(encoding="utf-8")
    tls_prepare = (FILES / "aos-kuksa-tls-prepare.service").read_text(encoding="utf-8")
    substrate = (FILES / "aos-kuksa-substrate.target").read_text(encoding="utf-8")
    require(reset, "ConditionPathExists=!/var/aos/.provisionstate", "reset unit")
    require(reset, "ExecStart=/opt/aos/deprovision.sh", "reset unit")
    require(
        reset,
        "ExecStartPost=/usr/bin/install -d -m 0700 -o root -g root /var/aos/iam",
        "reset unit IAM parent",
    )
    if reset.count("ExecStartPost=") != 1:
        raise ValidationError("reset unit must recreate the IAM parent exactly once")
    require(init, "TimeoutStartSec=10s", "token init unit")
    require(init, "RemainAfterExit=yes", "token init unit")
    require(init, "ReadWritePaths=/var/aos/iam /var/lib/softhsm", "token init unit")
    forbid(init, "ReadWritePaths=-/var/aos/iam", "token init unit")
    forbid(init, "ReadWritePaths=/var/aos ", "token init unit")
    require(cleanup, "aos-kuksa-runtime-cleanup", "cleanup unit")
    require(cleanup, "-/var/lib/aos-kuksa-provider", "cleanup unit")
    require(cleanup, "-/var/lib/aos-kuksa-tls", "cleanup unit")
    require(cleanup, "/var/lib/softhsm", "cleanup unit")
    forbid(cleanup, "-/var/lib/softhsm", "cleanup required PKCS11 root")
    require(tls_prepare, "StateDirectory=aos-kuksa-tls", "TLS prepare unit")
    require(tls_prepare, "StateDirectoryMode=0700", "TLS prepare unit")
    require(tls_prepare, "RemainAfterExit=yes", "TLS prepare unit")
    require(tls_prepare, "ConditionPathExists=/var/aos/.provisionstate", "TLS prepare unit")
    require(substrate, "WantedBy=aos.target", "substrate target")
    forbid(substrate, "aos-kuksa-runtime-cleanup.service", "ordinary reboot graph")
    for unit_path in FILES.rglob("*.service"):
        if unit_path.name != "aos-kuksa-runtime-cleanup.service":
            forbid(
                unit_path.read_text(encoding="utf-8"),
                "aos-kuksa-runtime-cleanup.service",
                f"ordinary reboot unit {unit_path.name}",
            )
    for text, label in (
        (reset, "reset"),
        (init, "token init"),
        (tls_prepare, "TLS prepare"),
        (cleanup, "cleanup"),
    ):
        require(text, "RestrictAddressFamilies=AF_UNIX", label)
        require(text, "IPAddressDeny=any", label)
        forbid(text, "IPAddressAllow=", label)

    kuksa = (FILES / "kuksa-databroker.service.d/20-kuksa-verifier.conf").read_text(
        encoding="utf-8"
    )
    require(kuksa, "EnvironmentFile=", "KUKSA drop-in")
    require(kuksa, "Requires=aos-kuksa-tls-prepare.service", "KUKSA drop-in")
    require(kuksa, "LoadCredential=kuksa-server-key:/var/lib/aos-kuksa-tls/server.key", "KUKSA drop-in")
    require(kuksa, "LoadCredential=kuksa-server-cert:/var/lib/aos-kuksa-tls/server.pem", "KUKSA drop-in")
    require(kuksa, "--tls-cert %d/kuksa-server-cert", "KUKSA drop-in")
    require(kuksa, "--tls-private-key %d/kuksa-server-key", "KUKSA drop-in")
    forbid(kuksa, "/etc/kuksa-val/Server", "KUKSA drop-in")
    require(kuksa, "--jwt-public-key=/run/aos-kuksa-verifier/kuksa-jwt-public.pem", "KUKSA drop-in")
    forbid(kuksa, "/etc/kuksa-val/jwt.key.pub", "KUKSA drop-in")

    provider = (
        AUTH_FILES / "aos-kuksa-provider-prepare.service"
    ).read_text(encoding="utf-8")
    require(provider, "StateDirectory=aos-kuksa-provider", "Provider unit")
    require(provider, "StateDirectoryMode=0700", "Provider unit")
    forbid(provider, "systemd-slot-component/credentials", "Provider unit")

    verifier_unit = (AUTH_FILES / "aos-kuksa-verifier-prepare.service").read_text(
        encoding="utf-8"
    )
    auth_unit = (AUTH_FILES / "aos-kuksa-auth-compat.service").read_text(
        encoding="utf-8"
    )
    tmpfiles = (AUTH_FILES / "aos-kuksa-auth-compat.conf").read_text(encoding="utf-8")
    require(
        tmpfiles,
        "d /run/aos-kuksa-auth-compat 0750 aos-kac aos-kuksa-clients -\n"
        "a+ /run/aos-kuksa-auth-compat - - - - u:root:-wx",
        "KAC exact cleanup ACL",
    )
    forbid(tmpfiles, "0770 aos-kac aos-kuksa-clients", "KAC consumer group write")
    for unit_text, label, exact_paths in (
        (
            verifier_unit,
            "Verifier unit",
            "ReadWritePaths=/run/aos-kuksa-verifier /var/lib/softhsm/tokens",
        ),
        (provider, "Provider unit", "ReadWritePaths=/var/lib/softhsm/tokens"),
        (
            auth_unit,
            "KAC daemon unit",
            "ReadWritePaths=/run/aos-kuksa-auth-compat /var/lib/softhsm/tokens",
        ),
    ):
        require(unit_text, exact_paths, label)
        forbid(unit_text, "ReadWritePaths=/var/lib/softhsm\n", label)
        require(unit_text, "NoNewPrivileges=yes", label)
        require(unit_text, "CapabilityBoundingSet=\n", label)
        require(unit_text, "AmbientCapabilities=\n", label)
        for capability in ("CAP_DAC_OVERRIDE", "CAP_DAC_READ_SEARCH", "cap_dac_override"):
            forbid(unit_text, capability, label)
    require(verifier_unit, "SupplementaryGroups=aos-kac", "Verifier exact group")
    forbid(auth_unit, "SupplementaryGroups=aos-kuksa-clients aos-kac", "KAC group boundary")
    forbid(cleanup, "SupplementaryGroups=aos-kuksa-clients", "cleanup consumer group")

    vdp = (FILES / "aos-vehicle-data-provider.service.d/20-kuksa-provider.conf").read_text(
        encoding="utf-8"
    )
    require(vdp, "LoadCredential=\n", "VDP drop-in")
    require(
        vdp,
        "LoadCredential=kuksa-token:/var/lib/aos-kuksa-provider/kuksa-token",
        "VDP drop-in",
    )
    require(
        vdp,
        "LoadCredential=kuksa-ca:/var/lib/aos-kuksa-tls/server.pem",
        "VDP drop-in",
    )
    require(vdp, "ConditionPathExists=/var/lib/aos-kuksa-provider/kuksa-token", "VDP drop-in")
    forbid(vdp, "systemd-slot-component/credentials/kuksa-token", "VDP drop-in")

    provider_runtime = (
        ROOT / "providers/carla-viss-kuksa/src/carla_viss_kuksa_provider/runtime.py"
    ).read_text(encoding="utf-8")
    require(provider_runtime, 'ca = credential_directory / "kuksa-ca"', "VDP runtime")
    forbid(provider_runtime, "/etc/kuksa-val/CA.pem", "VDP runtime")

    kuksa_recipe_append = KUKSA_RECIPE_APPEND.read_text(encoding="utf-8")
    for fixture in ("Server.key", "Server.pem", "Client.key", "Client.pem"):
        require(
            kuksa_recipe_append,
            f"${{D}}${{sysconfdir}}/kuksa-val/{fixture}",
            "KUKSA recipe secret-negative cleanup",
        )

    resources = json.loads(
        (ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/resources.cfg").read_text(
            encoding="utf-8"
        )
    )
    if not isinstance(resources, list) or [item.get("name") for item in resources] != [
        "kuksa",
        "kuksa-auth-client",
    ]:
        raise ValidationError("resources.cfg must contain exact ordered entries")
    client = resources[1]
    if client.get("sharedCount") != 4 or client.get("groups") != ["aos-kuksa-clients"]:
        raise ValidationError("kuksa-auth-client share/group mismatch")
    serialized = json.dumps(client, sort_keys=True)
    for forbidden_value in ("AOS_SECRET", "kuksa-jwt-pin", "token", "permission"):
        if forbidden_value in serialized:
            raise ValidationError(f"resource contains authority: {forbidden_value}")

    image = (ROOT / "meta-aos-vehicle-platform/recipes-core/images/aos-image-vm.bbappend").read_text(
        encoding="utf-8"
    )
    for package in ("aos-kuksa-auth-compat", "aos-kuksa-factory-integration"):
        if len(re.findall(rf"(?<![-\w]){re.escape(package)}(?![-\w])", image)) != 1:
            raise ValidationError(f"image must contain {package} exactly once")

    deprov = (ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-deprov/files/deprovision.sh").read_text(
        encoding="utf-8"
    )
    deprov_append = (
        ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-deprov/aos-deprov.bbappend"
    ).read_text(encoding="utf-8")
    require(
        deprov_append,
        'FILESEXTRAPATHS:prepend := "${THISDIR}/files:"',
        "deprovision bbappend",
    )
    forbid(deprov_append, "SRC_URI:remove", "deprovision bbappend")
    forbid(deprov_append, "do_install", "deprovision bbappend")
    if deprov.count("systemctl start aos-kuksa-runtime-cleanup.service") != 1:
        raise ValidationError("deprovision must centralize the cleanup invocation")
    require(deprov, "run_kuksa_cleanup || return 1", "synchronous fail-closed cleanup")
    require(deprov, "run_kuksa_cleanup || exit 1", "asynchronous fail-closed cleanup")
    if deprov.index("run_kuksa_cleanup || exit 1") > deprov.index(
        "rm /var/aos/.provisionstate"
    ):
        raise ValidationError("async cleanup must precede provision-state removal")
    if deprov.index("run_kuksa_cleanup || return 1") > deprov.index("/opt/aos/clearhsm.sh"):
        raise ValidationError("full cleanup must fail before broad legacy cleanup")

    transformer_path = ROOT / (
        "meta-aos-vehicle-platform/recipes-aos/aos-iamanager/files/"
        "aos-kuksa-iam-configure.py"
    )
    spec = importlib.util.spec_from_file_location("iam_transform", transformer_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = {
        "enablePermissionsHandler": True,
        "certModules": [{"id": "existing", "opaque": [1, 2, 3]}],
        "unchanged": {"value": True},
    }
    transformed = module.transform(original)
    if transformed["certModules"][:-1] != original["certModules"]:
        raise ValidationError("IAM transform changed existing modules")
    if transformed["certModules"][-1] != module.MODULE:
        raise ValidationError("IAM transform did not add exact module")

    policy = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(
            (ROOT / "meta-aos-vehicle-platform/recipes-security/refpolicy/files").glob(
                "aos_kuksa_*"
            )
        )
    )
    for domain in (
        "aos_kuksa_provider_prepare_t",
        "aos_kuksa_token_init_t",
        "aos_kuksa_runtime_cleanup_t",
        "aos_kuksa_tls_prepare_t",
    ):
        require(policy, domain, "SELinux")
    require(policy, "type aos_kuksa_iam_port_t;", "SELinux")
    forbid(policy, "corenet_port(aos_kuksa_iam_port_t)", "SELinux")
    forbid(policy, "portcon tcp", "SELinux")
    port_policy_patch = PORT_POLICY_PATCH.read_text(encoding="utf-8")
    require(
        port_policy_patch,
        "network_port(aos_kuksa_iam, tcp,8090,s0)",
        "SELinux corenetwork patch",
    )
    forbid(port_policy_patch, "unreserved_port", "SELinux corenetwork patch")
    require(policy, "aos_kuksa_provider_store_t", "SELinux")
    require(policy, "aos_kuksa_tls_store_t", "SELinux")
    require(
        policy,
        "read_files_pattern(init_t, aos_kuksa_tls_store_t, aos_kuksa_tls_store_t)",
        "SELinux",
    )
    require(
        policy,
        "read_files_pattern(init_t, aos_var_run_t, aos_kuksa_pin_t)",
        "SELinux systemd PIN credential read",
    )
    require(
        policy,
        "read_files_pattern(initrc_t, aos_kuksa_verifier_runtime_t, aos_kuksa_verifier_runtime_t)",
        "SELinux broker verifier read",
    )
    require(
        policy,
        "read_files_pattern(aos_t, aos_var_run_t, aos_kuksa_pin_t)",
        "SELinux Aos IAM PIN read",
    )
    require(
        policy,
        "manage_files_pattern(aos_t, aos_kuksa_pkcs11_store_t, aos_kuksa_pkcs11_store_t)",
        "SELinux Aos IAM PKCS11 ownership",
    )
    require(
        policy,
        "manage_files_pattern(aos_kuksa_token_init_t, aos_var_run_t, aos_kuksa_pin_t)",
        "SELinux exact PIN parent boundary",
    )
    require(policy, "type aos_var_run_t;", "SELinux IAM parent type")
    require(
        policy,
        'type_transition aos_kuksa_token_init_t aos_var_run_t:file aos_kuksa_pin_t ".kuksa-jwt-pin.tmp";',
        "SELinux exact PIN temporary-file transition",
    )
    require(
        policy,
        "miscfiles_read_localization(aos_kuksa_token_init_t)",
        "SELinux SoftHSM localization read",
    )
    forbid(
        policy,
        "manage_files_pattern(aos_kuksa_token_init_t, aos_kuksa_pin_t, aos_kuksa_pin_t)",
        "SELinux invalid PIN-as-parent boundary",
    )
    require(
        policy,
        "allow aos_kuksa_auth_compat_t aos_kuksa_pkcs11_store_t:file write;",
        "SELinux KAC write-existing boundary",
    )
    require(
        policy,
        "allow aos_kuksa_provider_prepare_t aos_kuksa_pkcs11_store_t:file { lock write };",
        "SELinux Provider write-existing boundary",
    )
    require(
        policy,
        "allow aos_kuksa_verifier_prepare_t aos_kuksa_pkcs11_store_t:file { lock write setattr };",
        "SELinux verifier finalizer file boundary",
    )
    require(
        policy,
        "allow aos_kuksa_verifier_prepare_t aos_kuksa_pkcs11_store_t:dir setattr;",
        "SELinux verifier finalizer directory boundary",
    )
    for domain in ("aos_kuksa_auth_compat_t", "aos_kuksa_provider_prepare_t"):
        for permission in ("create", "add_name", "remove_name", "unlink", "rename", "setattr"):
            forbid(
                policy,
                f"allow {domain} aos_kuksa_pkcs11_store_t:file {permission}",
                "SELinux signer negative boundary",
            )
        forbid(
            policy,
            f"allow {domain} aos_kuksa_pkcs11_store_t:dir write",
            "SELinux signer directory write boundary",
        )
    for domain in (
        "aos_kuksa_token_init_t",
        "aos_kuksa_runtime_cleanup_t",
        "aos_kuksa_tls_prepare_t",
        "aos_kuksa_auth_compat_t",
        "aos_kuksa_verifier_prepare_t",
        "aos_kuksa_provider_prepare_t",
    ):
        require(
            policy,
            f"allow initrc_t {domain}:process2 nnp_transition;",
            "SELinux NoNewPrivileges transition",
        )
        require(
            policy,
            f"init_rw_script_stream_sockets({domain})",
            "SELinux systemd stream boundary",
        )
        require(
            policy,
            f"files_search_var_lib({domain})",
            "SELinux /var/lib traversal boundary",
        )
    for store in (
        "aos_kuksa_provider_store_t",
        "aos_kuksa_tls_store_t",
    ):
        require(
            policy,
            f"list_dirs_pattern(aos_kuksa_runtime_cleanup_t, {store}, {store})",
            "SELinux cleanup directory inspection",
        )
    require(
        policy,
        'type_transition aos_kuksa_provider_prepare_t aos_kuksa_provider_store_t:file aos_kuksa_provider_credential_t ".kuksa-token.tmp";',
        "SELinux exact Provider temporary-file transition",
    )
    forbid(
        policy,
        "type_transition aos_kuksa_provider_prepare_t aos_kuksa_provider_store_t:file aos_kuksa_provider_credential_t;",
        "SELinux generic Provider transition",
    )
    require(
        policy,
        "manage_dirs_pattern(aos_kuksa_runtime_cleanup_t, aos_kuksa_pkcs11_store_t, aos_kuksa_pkcs11_store_t)",
        "SELinux bounded PKCS11 cleanup",
    )
    require(
        policy,
        "manage_files_pattern(aos_kuksa_runtime_cleanup_t, aos_kuksa_pkcs11_store_t, aos_kuksa_pkcs11_store_t)",
        "SELinux bounded PKCS11 cleanup",
    )
    require(policy, "files_search_runtime(aos_kuksa_runtime_cleanup_t)", "SELinux cleanup runtime traversal")
    require(policy, "miscfiles_read_localization(aos_kuksa_tls_prepare_t)", "SELinux TLS localization")
    forbid(policy, "delete_dirs_pattern(aos_kuksa_runtime_cleanup_t", "SELinux top-level cleanup")
    forbid(
        policy,
        "manage_dirs_pattern(aos_kuksa_tls_prepare_t, aos_kuksa_tls_store_t",
        "SELinux redundant TLS directory management",
    )
    forbid(
        policy,
        "aos_kuksa_provider_prepare_t vehicle_data_provider_store_t",
        "SELinux",
    )

    cleanup_source = (FACTORY / "src/runtime_cleanup.cpp").read_text(encoding="utf-8")
    require(cleanup_source, "/var/lib/aos-kuksa-provider/kuksa-token", "cleanup")
    require(cleanup_source, "/var/lib/aos-kuksa-tls/server.key", "cleanup")
    require(cleanup_source, "/var/lib/aos-kuksa-tls/server.pem", "cleanup")
    require(cleanup_source, "/var/lib/softhsm/tokens", "cleanup")
    require(cleanup_source, "kMaximumPkcs11TokenDirectories", "cleanup bound")
    require(cleanup_source, "kMaximumPkcs11FilesPerToken", "cleanup bound")
    require(cleanup_source, "AT_SYMLINK_NOFOLLOW", "cleanup no-symlink boundary")
    require(cleanup_source, "O_PATH | O_DIRECTORY", "cleanup parent lookup")
    forbid(cleanup_source, "systemd-slot-component/credentials", "cleanup")
    forbid(cleanup_source, "RemoveEmptyDirectory", "cleanup preserved runtime roots")
    forbid(cleanup_source, "kDirectories", "cleanup preserved runtime roots")
    cleanup_header = (FACTORY / "include/factory/integration.hpp").read_text(encoding="utf-8")
    forbid(cleanup_header, "CleanupDirectories", "cleanup preserved runtime roots")
    token_source = (FACTORY / "src/token_init.cpp").read_text(encoding="utf-8")
    require(token_source, "SelectSingleUninitializedSlot(states)", "token slot selection")
    require(token_source, "kPkcs11TokenInitialized", "token initialized flag")
    forbid(token_source, "info_(slot, &info) != kOk) candidates.push_back", "legacy slot bug")
    verifier_source = ROOT / "authorization/aos-kuksa-compat/src/verifier_prepare.cpp"
    verifier_text = verifier_source.read_text(encoding="utf-8")
    for needle in (
        "FinalizeSoftHsmAccess",
        "IsCanonicalUuid",
        "SerialForUuid",
        "AT_SYMLINK_NOFOLLOW",
        "status.st_nlink != 1",
        "matching_tokens != 1U",
        "exact_private_key",
        "02750U",
        "0660",
        "0640",
    ):
        require(verifier_text, needle, "bounded SoftHSM finalizer")
    forbid(verifier_text, "recursive_directory_iterator", "production recursive mutation")
    for forbidden_rule in (
        "corenet_tcp_connect_all_ports",
        "corenet_tcp_sendrecv_all_if",
        "corenet_tcp_sendrecv_all_nodes",
        "sysnet_dns_name_resolve",
        "audit2allow",
        "sys_admin",
    ):
        forbid(policy, forbidden_rule, "SELinux")


def main() -> int:
    try:
        validate()
    except (ValidationError, ValueError, json.JSONDecodeError) as error:
        print(f"KAC Factory validation failed: {error}")
        return 1
    print("KAC Factory validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
