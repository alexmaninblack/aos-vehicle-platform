# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from tools import validate_kac_factory_integration


class KacFactoryIntegrationTests(unittest.TestCase):
    def test_bounded_factory_integration_passes(self) -> None:
        validate_kac_factory_integration.validate()

    def test_no_timer_path_or_renewal_unit(self) -> None:
        files = validate_kac_factory_integration.FILES
        names = {path.name for path in files.rglob("*") if path.is_file()}
        self.assertFalse(any(name.endswith((".timer", ".path")) for name in names))
        self.assertFalse(any("renew" in name for name in names))

    def test_unrelated_service_kac_sources_remain_frozen(self) -> None:
        root = validate_kac_factory_integration.ROOT
        changed = {
            line[3:]
            for line in __import__("subprocess").check_output(
                ["git", "diff", "--name-status", "HEAD"], cwd=root, text=True
            ).splitlines()
            if line and not line.startswith(("R", "C"))
        }
        frozen = {
            "authorization/aos-kuksa-compat/include/kac/core.hpp",
            "authorization/aos-kuksa-compat/src/core.cpp",
            "authorization/aos-kuksa-compat/src/json.cpp",
            "authorization/aos-kuksa-compat/src/pkcs11_signer.cpp",
            "authorization/aos-kuksa-compat/src/main.cpp",
            "authorization/aos-kuksa-compat/src/server.cpp",
            "authorization/aos-kuksa-compat/tests/kac_tests.cpp",
        }
        self.assertTrue(changed.isdisjoint(frozen))

    def test_provider_source_is_not_the_vdp_store(self) -> None:
        root = validate_kac_factory_integration.ROOT
        provider = (
            root
            / "meta-aos-vehicle-platform/recipes-aos/aos-kuksa-auth-compat/files/"
            "aos-kuksa-provider-prepare.service"
        ).read_text(encoding="utf-8")
        dropin = (
            validate_kac_factory_integration.FILES
            / "aos-vehicle-data-provider.service.d/20-kuksa-provider.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("StateDirectory=aos-kuksa-provider", provider)
        self.assertIn(
            "LoadCredential=kuksa-token:/var/lib/aos-kuksa-provider/kuksa-token",
            dropin,
        )
        self.assertIn(
            "LoadCredential=kuksa-ca:/var/lib/aos-kuksa-tls/server.pem",
            dropin,
        )
        self.assertNotIn("systemd-slot-component/credentials", provider + dropin)

    def test_reset_recreates_only_the_token_parent(self) -> None:
        files = validate_kac_factory_integration.FILES
        reset = (files / "aos-kuksa-provision-reset.service").read_text(
            encoding="utf-8"
        )
        self.assertEqual(reset.count("ExecStartPost="), 1)
        self.assertIn(
            "ExecStartPost=/usr/bin/install -d -m 0700 -o root -g root /var/aos/iam",
            reset,
        )
        self.assertNotIn(".kuksa-jwt-pin", reset)
        token_init = (files / "aos-kuksa-token-init.service").read_text(
            encoding="utf-8"
        )
        self.assertIn("Requires=aos-kuksa-provision-reset.service", token_init)
        self.assertIn("After=aos-kuksa-provision-reset.service", token_init)
        self.assertIn(
            "ReadWritePaths=/var/aos/iam /var/lib/softhsm", token_init
        )
        self.assertNotIn("ReadWritePaths=-/var/aos/iam", token_init)


if __name__ == "__main__":
    unittest.main()
