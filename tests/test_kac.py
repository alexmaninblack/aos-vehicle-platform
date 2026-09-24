# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from tools import validate_kac


class KacTests(unittest.TestCase):
    def test_crun_client_uses_exact_live_proven_rules(self) -> None:
        validate_kac.validate_crun_client_policy(validate_kac.POLICY.read_text())

    def test_crun_client_rejects_missing_or_broader_access(self) -> None:
        policy = validate_kac.POLICY.read_text()
        exact = "allow container_engine_t aos_kuksa_auth_runtime_t:dir { getattr search };"
        variants = [
            policy.replace(exact, ""),
            policy.replace(exact, exact.replace("getattr search", "getattr search write")),
            policy.replace("allow container_engine_t ", "allow container_engine_domain "),
            policy + "\nallow container_engine_t aos_kuksa_pkcs11_store_t:file read;\n",
            policy + "\naos_kuksa_auth_compat_connect(container_engine_t)\n",
            policy + "\npermissive container_engine_t;\n",
            policy + "\ntunable_policy(`container_mounton_non_security',`')\n",
        ]
        for candidate in variants:
            with self.subTest(candidate=variants.index(candidate)):
                with self.assertRaises(validate_kac.KacValidationError):
                    validate_kac.validate_crun_client_policy(candidate)

    def test_bounded_kac_implementation_passes(self) -> None:
        validate_kac.validate_kac()

    def test_helper_has_no_cpu_or_memory_ceiling(self) -> None:
        unit = (validate_kac.FILES / "aos-kuksa-auth-compat.service").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("MemoryMax=", unit)
        self.assertNotIn("CPUQuota=", unit)
        self.assertIn("TasksMax=32", unit)
        self.assertIn("LimitNOFILE=128", unit)

    def test_verifier_preparation_is_networkless_and_can_finalize_sgid(self) -> None:
        unit = (validate_kac.FILES / "aos-kuksa-verifier-prepare.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("User=root", unit)
        self.assertIn("Group=root", unit)
        self.assertIn("SupplementaryGroups=aos-kac", unit)
        self.assertIn("NoNewPrivileges=yes", unit)
        self.assertIn("CapabilityBoundingSet=\n", unit)
        self.assertIn("AmbientCapabilities=\n", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertEqual(
            [line for line in unit.splitlines() if line.startswith("ReadWritePaths=")],
            ["ReadWritePaths=/run/aos-kuksa-verifier /var/lib/softhsm/tokens"],
        )
        self.assertNotIn("RestrictSUIDSGID=", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertIn("IPAddressDeny=any", unit)
        self.assertNotIn("IPAddressAllow=", unit)

        source = (
            validate_kac.SOURCE / "src/verifier_prepare.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("constexpr mode_t kFinalTokenDirectoryMode = 02750U;", source)
        self.assertIn("::fchmod(token.get(), kFinalTokenDirectoryMode)", source)

    def test_other_kac_units_retain_suid_sgid_restriction(self) -> None:
        for name in (
            "aos-kuksa-auth-compat.service",
            "aos-kuksa-provider-prepare.service",
        ):
            unit = (validate_kac.FILES / name).read_text(encoding="utf-8")
            self.assertIn("RestrictSUIDSGID=yes", unit, name)

    def test_each_signer_unit_selects_only_the_exact_softhsm_module(self) -> None:
        expected = (
            "Environment=PKCS11_PROVIDER_MODULE=/usr/lib/softhsm/libsofthsm2.so"
        )
        for name in (
            "aos-kuksa-verifier-prepare.service",
            "aos-kuksa-provider-prepare.service",
            "aos-kuksa-auth-compat.service",
        ):
            unit = (validate_kac.FILES / name).read_text(encoding="utf-8")
            self.assertEqual(
                [line for line in unit.splitlines() if line.startswith("Environment=")],
                [expected],
                name,
            )

    def test_helper_uses_native_aos_ca_contract(self) -> None:
        unit = (validate_kac.FILES / "aos-kuksa-auth-compat.service").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "LoadCredential=aos-iam-ca:/usr/share/ca-certificates/aos/AosRootCA.crt",
            unit,
        )
        self.assertNotIn("/var/aos/iam/certs/ca.pem", unit)

    def test_runtime_directory_keeps_consumers_read_only(self) -> None:
        config = (validate_kac.FILES / "aos-kuksa-auth-compat.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "d /run/aos-kuksa-auth-compat 0750 aos-kac aos-kuksa-clients -",
            config,
        )
        self.assertIn(
            "a+ /run/aos-kuksa-auth-compat - - - - u:root:-wx", config
        )
        self.assertNotIn("0770 aos-kac aos-kuksa-clients", config)

    def test_startup_diagnostics_are_fixed_stage_names_only(self) -> None:
        server = (validate_kac.SOURCE / "src/server.cpp").read_text(
            encoding="utf-8"
        )
        verifier = (validate_kac.SOURCE / "src/verifier_prepare.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("startup stage=%s failed errno=%d", server)
        self.assertIn("stage=%s failed errno=%d", verifier)
        self.assertNotIn("startup path=", server)
        self.assertNotIn("pin=", server + verifier)

    def test_package_is_separately_removable(self) -> None:
        recipe = validate_kac.RECIPE.read_text(encoding="utf-8")
        self.assertNotIn("aos-image-vm", recipe)
        self.assertIn("aos-kuksa-auth-compat_0.2.0.bb", validate_kac.RECIPE.name)
        self.assertIn("aos-kuksa-provider-prepare", recipe)
        self.assertNotIn("PACKAGES +=", recipe)

    def test_provider_is_a_separate_networkless_one_shot(self) -> None:
        unit = (validate_kac.FILES / "aos-kuksa-provider-prepare.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Type=oneshot", unit)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", unit)
        self.assertIn("IPAddressDeny=any", unit)
        self.assertIn("StateDirectory=aos-kuksa-provider", unit)
        self.assertIn("StateDirectoryMode=0700", unit)
        self.assertNotIn("systemd-slot-component/credentials", unit)
        self.assertNotIn("IPAddressAllow=", unit)


if __name__ == "__main__":
    unittest.main()
