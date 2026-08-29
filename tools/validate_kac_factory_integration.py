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
        FACTORY / "tests/factory_integration_tests.cpp",
        RECIPE,
        FILES / "aos-kuksa-substrate.target",
        FILES / "aos-kuksa-provision-reset.service",
        FILES / "aos-kuksa-token-init.service",
        FILES / "aos-kuksa-runtime-cleanup.service",
        FILES / "aos-iam-prov.service.d/20-kuksa-token-init.conf",
        FILES / "aos-iam.service.d/20-kuksa-token-init.conf",
        FILES / "kuksa-databroker.service.d/20-kuksa-verifier.conf",
        FILES / "aos-vehicle-data-provider.service.d/20-kuksa-provider.conf",
        PORT_POLICY_PATCH,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise ValidationError("missing Factory files: " + ", ".join(missing))

    recipe = RECIPE.read_text(encoding="utf-8")
    require(recipe, 'DEPENDS = "softhsm"', "Factory recipe")
    require(
        recipe,
        'RDEPENDS:${PN} = "aos-deprov aos-iamanager aos-kuksa-auth-compat aos-servicemanager aos-vehicle-data-provider-platform kuksa-databroker softhsm"',
        "Factory recipe",
    )
    for executable in ("aos-kuksa-token-init", "aos-kuksa-runtime-cleanup"):
        require(recipe, executable, "Factory recipe")
    for forbidden in ("AUTOREV", "do_rootfs", "aos-image-vm", "PACKAGES +="):
        forbid(recipe, forbidden, "Factory recipe")

    reset = (FILES / "aos-kuksa-provision-reset.service").read_text(encoding="utf-8")
    init = (FILES / "aos-kuksa-token-init.service").read_text(encoding="utf-8")
    cleanup = (FILES / "aos-kuksa-runtime-cleanup.service").read_text(encoding="utf-8")
    substrate = (FILES / "aos-kuksa-substrate.target").read_text(encoding="utf-8")
    require(reset, "ConditionPathExists=!/var/aos/.provisionstate", "reset unit")
    require(reset, "ExecStart=/opt/aos/deprovision.sh", "reset unit")
    require(init, "TimeoutStartSec=10s", "token init unit")
    require(init, "RemainAfterExit=yes", "token init unit")
    require(cleanup, "aos-kuksa-runtime-cleanup", "cleanup unit")
    require(cleanup, "-/var/lib/aos-kuksa-provider", "cleanup unit")
    require(substrate, "WantedBy=aos.target", "substrate target")
    for text, label in ((reset, "reset"), (init, "token init"), (cleanup, "cleanup")):
        require(text, "RestrictAddressFamilies=AF_UNIX", label)
        require(text, "IPAddressDeny=any", label)
        forbid(text, "IPAddressAllow=", label)

    kuksa = (FILES / "kuksa-databroker.service.d/20-kuksa-verifier.conf").read_text(
        encoding="utf-8"
    )
    require(kuksa, "EnvironmentFile=", "KUKSA drop-in")
    require(kuksa, "--jwt-public-key=/run/aos-kuksa-verifier/kuksa-jwt-public.pem", "KUKSA drop-in")
    forbid(kuksa, "/etc/kuksa-val/jwt.key.pub", "KUKSA drop-in")

    provider = (
        ROOT
        / "meta-aos-vehicle-platform/recipes-aos/aos-kuksa-auth-compat/files/"
        "aos-kuksa-provider-prepare.service"
    ).read_text(encoding="utf-8")
    require(provider, "StateDirectory=aos-kuksa-provider", "Provider unit")
    require(provider, "StateDirectoryMode=0700", "Provider unit")
    forbid(provider, "systemd-slot-component/credentials", "Provider unit")

    vdp = (FILES / "aos-vehicle-data-provider.service.d/20-kuksa-provider.conf").read_text(
        encoding="utf-8"
    )
    require(vdp, "LoadCredential=\n", "VDP drop-in")
    require(
        vdp,
        "LoadCredential=kuksa-token:/var/lib/aos-kuksa-provider/kuksa-token",
        "VDP drop-in",
    )
    require(vdp, "ConditionPathExists=/var/lib/aos-kuksa-provider/kuksa-token", "VDP drop-in")
    forbid(vdp, "systemd-slot-component/credentials/kuksa-token", "VDP drop-in")

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
    if deprov.count("systemctl start aos-kuksa-runtime-cleanup.service") != 2:
        raise ValidationError("deprovision must clean async and full paths exactly once")
    if deprov.index("aos-kuksa-runtime-cleanup.service", deprov.index("deprovision_async")) > deprov.index(
        "rm /var/aos/.provisionstate"
    ):
        raise ValidationError("async cleanup must precede provision-state removal")

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
    require(
        policy,
        "type_transition aos_kuksa_provider_prepare_t aos_kuksa_provider_store_t:file aos_kuksa_provider_credential_t;",
        "SELinux",
    )
    forbid(
        policy,
        "aos_kuksa_provider_prepare_t vehicle_data_provider_store_t",
        "SELinux",
    )

    cleanup_source = (FACTORY / "src/runtime_cleanup.cpp").read_text(encoding="utf-8")
    require(cleanup_source, "/var/lib/aos-kuksa-provider/kuksa-token", "cleanup")
    forbid(cleanup_source, "systemd-slot-component/credentials", "cleanup")
    for forbidden_rule in ("corenet_tcp_connect_all_ports", "sysnet_dns_name_resolve", "audit2allow", "sys_admin"):
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
