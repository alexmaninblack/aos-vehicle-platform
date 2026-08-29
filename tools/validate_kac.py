#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate the bounded removable KAC source and package contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "authorization/aos-kuksa-compat"
RECIPE = ROOT / (
    "meta-aos-vehicle-platform/recipes-aos/aos-kuksa-auth-compat/"
    "aos-kuksa-auth-compat_0.2.0.bb"
)
FILES = RECIPE.parent / "files"
POLICY = ROOT / (
    "meta-aos-vehicle-platform/recipes-security/refpolicy/files/"
    "aos_kuksa_auth_compat.te"
)
PORT_POLICY_PATCH = ROOT / (
    "meta-aos-vehicle-platform/recipes-security/refpolicy/files/"
    "0001-corenetwork-label-aos-kuksa-iam-port.patch"
)
POLICY_APPEND = ROOT / (
    "meta-aos-vehicle-platform/recipes-security/refpolicy/refpolicy-aos_git.bbappend"
)


class KacValidationError(RuntimeError):
    """Raised when the implementation leaves the accepted KAC boundary."""


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise KacValidationError(f"{label}: missing {needle!r}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise KacValidationError(f"{label}: forbidden {needle!r}")


def validate_kac() -> None:
    required = [
        SOURCE / "CMakeLists.txt",
        SOURCE / "include/kac/core.hpp",
        SOURCE / "include/kac/verifier_prepare.hpp",
        SOURCE / "src/core.cpp",
        SOURCE / "src/json.cpp",
        SOURCE / "src/grpc_iam_client.cpp",
        SOURCE / "src/pkcs11_signer.cpp",
        SOURCE / "src/server.cpp",
        SOURCE / "src/main.cpp",
        SOURCE / "src/verifier_prepare.cpp",
        SOURCE / "include/kac/provider.hpp",
        SOURCE / "src/provider.cpp",
        SOURCE / "src/provider_prepare.cpp",
        SOURCE / "tests/kac_tests.cpp",
        SOURCE / "tests/provider_tests.cpp",
        SOURCE / "tests/verifier_prepare_tests.cpp",
        RECIPE,
        FILES / "aos-kuksa-auth-compat.service",
        FILES / "aos-kuksa-verifier-prepare.service",
        FILES / "aos-kuksa-provider-prepare.service",
        FILES / "aos-kuksa-auth-compat.conf",
        POLICY,
        PORT_POLICY_PATCH,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise KacValidationError("missing KAC files: " + ", ".join(missing))

    recipe = RECIPE.read_text(encoding="utf-8")
    require(recipe, 'SRCREV_aoscoreapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"', "recipe")
    require(recipe, "nobranch=1", "recipe")
    require(
        recipe,
        'DEPENDS = "abseil-cpp grpc protobuf openssl grpc-native protobuf-native"',
        "recipe",
    )
    require(recipe, 'RDEPENDS:${PN} = "openssl pkcs11-provider softhsm"', "recipe")
    require(recipe, "aos-kuksa-provider-prepare", "recipe")
    forbid(recipe, "PACKAGES +=", "recipe")
    require(recipe, "inherit cmake systemd useradd", "recipe")
    require(recipe, "${THISDIR}/../../../authorization/aos-kuksa-compat", "recipe")
    forbid(recipe, "aos-image-vm", "recipe")
    forbid(recipe, "AUTOREV", "recipe")
    forbid(recipe, "do_rootfs", "recipe")

    helper = (FILES / "aos-kuksa-auth-compat.service").read_text(encoding="utf-8")
    verifier = (FILES / "aos-kuksa-verifier-prepare.service").read_text(encoding="utf-8")
    provider = (FILES / "aos-kuksa-provider-prepare.service").read_text(encoding="utf-8")
    tmpfiles = (FILES / "aos-kuksa-auth-compat.conf").read_text(encoding="utf-8")
    require(helper, "User=aos-kac", "helper unit")
    require(helper, "SupplementaryGroups=aos-kuksa-clients", "helper unit")
    require(helper, "LoadCredential=kuksa-jwt-pin:/var/aos/iam/.kuksa-jwt-pin", "helper unit")
    require(helper, "LoadCredential=aos-iam-ca:/var/aos/iam/certs/ca.pem", "helper unit")
    require(helper, "RestrictAddressFamilies=AF_UNIX AF_INET", "helper unit")
    require(helper, "IPAddressDeny=any", "helper unit")
    require(helper, "IPAddressAllow=127.0.0.1", "helper unit")
    require(helper, "TasksMax=32", "helper unit")
    require(helper, "LimitNOFILE=128", "helper unit")
    forbid(helper, "MemoryMax=", "helper unit")
    forbid(helper, "CPUQuota=", "helper unit")
    forbid(helper, "Environment=", "helper unit")
    require(verifier, "Type=oneshot", "verifier unit")
    require(verifier, "RestrictAddressFamilies=AF_UNIX", "verifier unit")
    require(verifier, "IPAddressDeny=any", "verifier unit")
    forbid(verifier, "IPAddressAllow=", "verifier unit")
    require(provider, "Type=oneshot", "provider unit")
    require(provider, "ExecStart=/usr/libexec/aos-kuksa-provider-prepare", "provider unit")
    require(provider, "LoadCredential=kuksa-jwt-pin:/var/aos/iam/.kuksa-jwt-pin", "provider unit")
    require(provider, "StateDirectory=aos-kuksa-provider", "provider unit")
    require(provider, "StateDirectoryMode=0700", "provider unit")
    forbid(provider, "systemd-slot-component/credentials", "provider unit")
    require(provider, "RestrictAddressFamilies=AF_UNIX", "provider unit")
    require(provider, "IPAddressDeny=any", "provider unit")
    forbid(provider, "IPAddressAllow=", "provider unit")
    forbid(provider, "Restart=on-failure", "provider unit")
    require(tmpfiles, "d /run/aos-kuksa-auth-compat 0750 aos-kac aos-kuksa-clients -", "tmpfiles")
    require(tmpfiles, "d /run/aos-kuksa-verifier 0755 root root -", "tmpfiles")

    source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(SOURCE.rglob("*")) if path.is_file()
    )
    for exact in (
        "127.0.0.1:8090",
        "aos-kuksa-auth-compat/v1",
        "aosedge-kuksa-auth-compat",
        "kuksa.val",
        "pkcs11:token=aos-kuksa;object=kuksa-jwt;type=private",
        "/run/aos-kuksa-auth-compat/request.sock",
        "/run/aos-kuksa-verifier/kuksa-jwt-public.pem",
        "aosedge-vdp-provider",
        "aos-vdp",
        "provide:Vehicle.Chassis.Axle.Row2.Wheel.Left.Speed",
        "/var/lib/aos-kuksa-provider",
        "CREDENTIALS_DIRECTORY",
        'kCaCredential = "aos-iam-ca"',
        "RemoveStaleTemporaryVerifier",
    ):
        require(source_text, exact, "source")
    for forbidden in (
        "pin-value=",
        "PKCS11_PIN",
        "/var/aos/iam/.usrpin",
        "system(",
        "popen(",
        "AF_INET6",
    ):
        forbid(source_text, forbidden, "source")

    grpc_source = (SOURCE / "src/grpc_iam_client.cpp").read_text(encoding="utf-8")
    forbid(grpc_source, "/var/aos/iam/certs/ca.pem", "IAM client source")
    require(grpc_source, 'std::getenv("CREDENTIALS_DIRECTORY")', "IAM client source")
    verifier_source = (SOURCE / "src/verifier_prepare.cpp").read_text(encoding="utf-8")
    for required in ("::lstat", "S_ISREG", "status.st_uid != ::geteuid()", "status.st_nlink != 1"):
        require(verifier_source, required, "verifier stale-state recovery")

    policy = POLICY.read_text(encoding="utf-8")
    require(policy, "aos_kuksa_auth_compat_t", "SELinux")
    require(policy, "aos_kuksa_verifier_prepare_t", "SELinux")
    require(policy, "aos_kuksa_provider_prepare_t", "SELinux")
    require(policy, "aos_kuksa_provider_store_t", "SELinux")
    require(policy, "type aos_kuksa_iam_port_t;", "SELinux")
    forbid(policy, "vehicle_data_provider_store_t", "SELinux")
    forbid(policy, "portcon tcp", "SELinux")
    forbid(policy, "corenet_port(aos_kuksa_iam_port_t)", "SELinux")
    require(policy, "corenet_tcp_sendrecv_generic_if(aos_kuksa_auth_compat_t)", "SELinux")
    require(policy, "corenet_tcp_sendrecv_generic_node(aos_kuksa_auth_compat_t)", "SELinux")
    for domain in (
        "aos_kuksa_auth_compat_t",
        "aos_kuksa_verifier_prepare_t",
        "aos_kuksa_provider_prepare_t",
    ):
        require(policy, f"allow initrc_t {domain}:process2 nnp_transition;", "SELinux NNP")
        require(policy, f"init_rw_script_stream_sockets({domain})", "SELinux systemd stream")
        require(policy, f"files_search_var_lib({domain})", "SELinux var-lib traversal")
        require(policy, f"files_search_runtime({domain})", "SELinux runtime traversal")
        require(policy, f"miscfiles_read_localization({domain})", "SELinux localization")
    require(
        policy,
        'type_transition aos_kuksa_provider_prepare_t aos_kuksa_provider_store_t:file aos_kuksa_provider_credential_t ".kuksa-token.tmp";',
        "SELinux named Provider transition",
    )
    forbid(
        policy,
        "type_transition aos_kuksa_provider_prepare_t aos_kuksa_provider_store_t:file aos_kuksa_provider_credential_t;",
        "SELinux generic Provider transition",
    )
    for domain in (
        "aos_kuksa_auth_compat_t, aos_kuksa_auth_runtime_t",
        "aos_kuksa_verifier_prepare_t, aos_kuksa_verifier_runtime_t",
        "aos_kuksa_provider_prepare_t, aos_kuksa_provider_store_t",
    ):
        forbid(policy, f"manage_dirs_pattern({domain}", "SELinux broad runtime directory management")
    for forbidden in (
        "corenet_tcp_connect_all_ports",
        "corenet_tcp_sendrecv_all_if",
        "corenet_tcp_sendrecv_all_nodes",
        "sysnet_dns_name_resolve",
        "audit2allow",
        "create_file_perms",
        "manage_lnk_files_pattern",
    ):
        forbid(policy, forbidden, "SELinux")
    port_policy_patch = PORT_POLICY_PATCH.read_text(encoding="utf-8")
    require(
        port_policy_patch,
        "network_port(aos_kuksa_iam, tcp,8090,s0)",
        "SELinux corenetwork patch",
    )
    forbid(port_policy_patch, "unreserved_port", "SELinux corenetwork patch")
    policy_append = POLICY_APPEND.read_text(encoding="utf-8")
    require(
        policy_append,
        "0001-corenetwork-label-aos-kuksa-iam-port.patch",
        "refpolicy append",
    )
    for suffix in (".te", ".fc", ".if"):
        require(policy_append, "aos_kuksa_auth_compat" + suffix, "refpolicy append")


def main() -> int:
    try:
        validate_kac()
    except KacValidationError as error:
        print(f"KAC validation failed: {error}")
        return 1
    print("KAC validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
