# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from dataclasses import dataclass

from tools import validate_kac_factory_integration


@dataclass
class _LifecycleModel:
    provisioned: bool = False
    reset_latched: bool = False
    iam_provisioning_active: bool = False
    verifier_active: bool = False
    token_exists: bool = False
    pin_exists: bool = False
    reset_count: int = 0
    cleanup_count: int = 0
    provision_state_removals: int = 0

    def _reset(self) -> None:
        self.cleanup_count += 1
        self.token_exists = False
        self.pin_exists = False
        self.reset_count += 1
        self.reset_latched = True

    def boot(self) -> None:
        self.reset_latched = False
        self.iam_provisioning_active = False
        self.verifier_active = False
        if not self.provisioned:
            self.sync_reset()
            self.iam_provisioning_active = True
        else:
            self.verifier_active = self.token_exists and self.pin_exists

    def sync_reset(self, *, cleanup_ok: bool = True) -> bool:
        if not cleanup_ok:
            return False
        self._reset()
        return True

    def iam_retry(self) -> None:
        if not self.reset_latched and not self.provisioned:
            self._reset()
        self.iam_provisioning_active = not self.provisioned

    def complete_provisioning(self) -> None:
        assert self.iam_provisioning_active
        assert not self.token_exists and not self.pin_exists
        self.token_exists = True
        self.pin_exists = True
        self.provisioned = True
        self.iam_provisioning_active = False
        self.verifier_active = True

    def async_deprovision(
        self,
        *,
        consumers_stopped: bool = True,
        reset_stopped: bool = True,
        cleanup_ok: bool = True,
    ) -> bool:
        if not consumers_stopped or not reset_stopped:
            return False
        self.iam_provisioning_active = False
        self.verifier_active = False
        self.reset_latched = False
        if not cleanup_ok:
            return False
        self.cleanup_count += 1
        self.token_exists = False
        self.provisioned = False
        self.provision_state_removals += 1
        self._reset()
        self.iam_provisioning_active = True
        return True


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
        self.assertIn("RemainAfterExit=yes", reset)
        self.assertNotIn(".kuksa-jwt-pin", reset)
        provisioning = (
            files / "aos-iam-prov.service.d/20-kuksa-provision-reset.conf"
        ).read_text(
            encoding="utf-8"
        )
        self.assertIn("Before=aos-iam-prov.service", reset)
        self.assertIn("Requires=aos-kuksa-provision-reset.service", provisioning)
        self.assertIn("After=aos-kuksa-provision-reset.service", provisioning)
        self.assertIn("ExecStartPre=", provisioning)
        self.assertNotIn("token-init", reset + provisioning)

    def test_deprovision_cleanup_is_fail_closed_in_both_paths(self) -> None:
        root = validate_kac_factory_integration.ROOT
        script = (
            root
            / "meta-aos-vehicle-platform/recipes-aos/aos-deprov/files/deprovision.sh"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            script.count("systemctl start aos-kuksa-runtime-cleanup.service"), 1
        )
        self.assertIn("run_kuksa_cleanup || return 1", script)
        self.assertIn("run_kuksa_cleanup || exit 1", script)
        consumer_stop = (
            "systemctl stop -- $(systemctl show -p Wants aos.target | cut -d= -f2) "
            "|| exit 1"
        )
        reset_stop = "systemctl stop aos-kuksa-provision-reset.service || exit 1"
        self.assertIn(consumer_stop, script)
        self.assertIn(reset_stop, script)
        self.assertNotIn("aos-kuksa-token-init", script)
        self.assertLess(script.index(consumer_stop), script.index(reset_stop))
        self.assertLess(
            script.index(reset_stop), script.index("run_kuksa_cleanup || exit 1")
        )
        self.assertLess(
            script.index("run_kuksa_cleanup || return 1"),
            script.index("/opt/aos/clearhsm.sh"),
        )
        self.assertLess(
            script.index("run_kuksa_cleanup || exit 1"),
            script.index("rm /var/aos/.provisionstate"),
        )

    def test_pre_sdk_state_has_one_reset_and_no_native_token_or_pin(self) -> None:
        lifecycle = _LifecycleModel()
        lifecycle.boot()
        self.assertEqual(lifecycle.reset_count, 1)
        self.assertTrue(lifecycle.iam_provisioning_active)
        self.assertFalse(lifecycle.token_exists)
        self.assertFalse(lifecycle.pin_exists)
        for _ in range(5):
            lifecycle.iam_retry()
        self.assertEqual(lifecycle.reset_count, 1)
        self.assertTrue(lifecycle.iam_provisioning_active)
        self.assertFalse(lifecycle.token_exists)
        self.assertFalse(lifecycle.pin_exists)

    def test_synchronous_reset_is_fail_closed_and_latches_once(self) -> None:
        lifecycle = _LifecycleModel()
        self.assertFalse(lifecycle.sync_reset(cleanup_ok=False))
        self.assertFalse(lifecycle.reset_latched)
        self.assertEqual(lifecycle.cleanup_count, 0)
        self.assertTrue(lifecycle.sync_reset())
        self.assertTrue(lifecycle.reset_latched)
        self.assertEqual(lifecycle.cleanup_count, 1)

    def test_obsolete_token_initializer_and_openssl_override_are_absent(self) -> None:
        validator = validate_kac_factory_integration
        matching = [
            path
            for directory in (validator.FILES, validator.AUTH_FILES)
            for path in directory.rglob("*.service")
            if "OPENSSL_CONF=" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(matching, [])
        self.assertFalse(
            (validator.FACTORY / "src/token_init.cpp").exists()
        )
        self.assertFalse(
            (validator.FILES / "aos-kuksa-token-init.service").exists()
        )

    def test_provision_restart_and_provisioned_reboot_validate_existing_token(self) -> None:
        lifecycle = _LifecycleModel()
        lifecycle.boot()
        lifecycle.complete_provisioning()
        reset_count = lifecycle.reset_count
        lifecycle.iam_retry()
        lifecycle.boot()
        self.assertTrue(lifecycle.provisioned)
        self.assertTrue(lifecycle.token_exists)
        self.assertTrue(lifecycle.pin_exists)
        self.assertTrue(lifecycle.verifier_active)
        self.assertEqual(lifecycle.reset_count, reset_count)

    def test_async_deprovision_rearms_once_and_supports_reprovision(self) -> None:
        lifecycle = _LifecycleModel()
        lifecycle.boot()
        lifecycle.complete_provisioning()
        self.assertTrue(lifecycle.async_deprovision())
        self.assertFalse(lifecycle.provisioned)
        self.assertTrue(lifecycle.reset_latched)
        self.assertTrue(lifecycle.iam_provisioning_active)
        self.assertFalse(lifecycle.token_exists)
        self.assertFalse(lifecycle.pin_exists)
        self.assertEqual(lifecycle.provision_state_removals, 1)
        lifecycle.complete_provisioning()
        self.assertTrue(lifecycle.async_deprovision())
        self.assertEqual(lifecycle.provision_state_removals, 2)

    def test_async_deprovision_failures_preserve_provision_state(self) -> None:
        for failure in (
            {"consumers_stopped": False},
            {"reset_stopped": False},
            {"cleanup_ok": False},
        ):
            lifecycle = _LifecycleModel()
            lifecycle.boot()
            lifecycle.complete_provisioning()
            self.assertFalse(lifecycle.async_deprovision(**failure))
            self.assertTrue(lifecycle.provisioned)
            self.assertEqual(lifecycle.provision_state_removals, 0)


if __name__ == "__main__":
    unittest.main()
