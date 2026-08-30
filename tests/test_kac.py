# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from tools import validate_kac


class KacTests(unittest.TestCase):
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
