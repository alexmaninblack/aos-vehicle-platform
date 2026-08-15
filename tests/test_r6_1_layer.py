# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Tests for the R6.1 atomic component lifecycle layer validator."""

from __future__ import annotations

import unittest

from tools import validate_r6_1_layer


class R61LayerTests(unittest.TestCase):
    def test_tracked_layer_passes(self) -> None:
        validate_r6_1_layer.validate_layer()

    def test_component_identity_is_fixed(self) -> None:
        self.assertEqual(
            validate_r6_1_layer.COMPONENT_ROOT,
            "/var/aos/workdirs/sm/runtimes/systemd-slot-component",
        )
        self.assertEqual(validate_r6_1_layer.COMPONENT_TYPE, "vehicle-data-provider")

    def test_refpolicy_files_are_installed_from_a_shell_task(self) -> None:
        content = validate_r6_1_layer.POLICY_APPEND.read_text(encoding="utf-8")
        self.assertIn("do_compile:prepend()", content)
        self.assertNotIn("do_patch:append()", content)

    def test_refpolicy_uses_the_pinned_runtime_interface(self) -> None:
        content = validate_r6_1_layer.POLICY.read_text(encoding="utf-8")
        self.assertIn("init_read_runtime_files(vehicle_data_provider_t)", content)
        self.assertNotIn("init_read_runtime(vehicle_data_provider_t)", content)
        self.assertIn("class service { start stop status reload };", content)

    def test_component_profile_is_bootstrap_owned(self) -> None:
        health = validate_r6_1_layer.HEALTH_ADAPTER.read_text(encoding="utf-8")
        launcher = validate_r6_1_layer.LAUNCHER.read_text(encoding="utf-8")
        unit = validate_r6_1_layer.UNIT.read_text(encoding="utf-8")
        self.assertIn("aos-vehicle-data-provider-selftest@$slot.service", health)
        self.assertIn('systemctl reload "$unit"', health)
        self.assertIn("systemctl is-active", health)
        self.assertIn("--self-test", launcher)
        self.assertIn("--mark-unavailable", launcher)
        self.assertIn("ExecReload=/bin/kill -HUP $MAINPID", unit)

    def test_demo_store_is_fixed_bounded_and_non_destructive(self) -> None:
        prepare = validate_r6_1_layer.STORE_PREPARE.read_text(encoding="utf-8")
        check = validate_r6_1_layer.STORE_CHECK.read_text(encoding="utf-8")
        mount = validate_r6_1_layer.STORE_MOUNT.read_text(encoding="utf-8")
        self.assertIn(f"store_size={validate_r6_1_layer.STORE_SIZE}", prepare)
        self.assertIn(
            f"backing_file={validate_r6_1_layer.STORE_BACKING}", prepare
        )
        self.assertIn('rm -f -- "$partial_file"', prepare)
        self.assertNotRegex(prepare, r"rm[^\n]*\$backing_file")
        self.assertNotRegex(prepare, r"mkfs[^\n]*\$backing_file")
        self.assertNotIn("AOS_", prepare)
        self.assertNotIn("AOS_", check)
        self.assertIn("store backing file is sparse or incompletely allocated", check)
        self.assertNotIn(
            f"Z {validate_r6_1_layer.COMPONENT_ROOT}",
            validate_r6_1_layer.TMPFILES.read_text(encoding="utf-8"),
        )
        self.assertIn("Options=loop,nodev,nosuid,noatime,errors=remount-ro", mount)
        self.assertNotIn("noexec", mount)

    def test_provider_parent_access_is_search_only(self) -> None:
        policy = validate_r6_1_layer.POLICY.read_text(encoding="utf-8")
        rules = [
            line.strip()
            for line in policy.splitlines()
            if "vehicle_data_provider_t aos_var_run_t:" in line
        ]
        self.assertEqual(
            ["allow vehicle_data_provider_t aos_var_run_t:dir search;"], rules
        )

    def test_early_store_preparation_has_no_local_fs_cycle(self) -> None:
        unit = validate_r6_1_layer.STORE_PREPARE_UNIT.read_text(encoding="utf-8")
        policy = validate_r6_1_layer.POLICY.read_text(encoding="utf-8")
        mount = validate_r6_1_layer.STORE_MOUNT.read_text(encoding="utf-8")
        self.assertIn("DefaultDependencies=no", unit)
        self.assertNotIn("PrivateTmp=yes", unit)
        self.assertIn("DefaultDependencies=no", mount)
        self.assertIn("Conflicts=umount.target", mount)
        self.assertIn(
            "init_rw_script_stream_sockets(systemd_modules_load_t)", policy
        )

    def test_arm64_runtime_qualifier_is_a_build_output(self) -> None:
        append = validate_r6_1_layer.SERVICE_MANAGER_APPEND.read_text(
            encoding="utf-8"
        )
        self.assertIn("-DWITH_TEST=ON", append)
        self.assertIn('DEPENDS:append = " softhsm"', append)
        self.assertIn(
            "-DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST", append
        )
        self.assertIn('find "${D}${prefix}/usr" -depth -delete', append)


if __name__ == "__main__":
    unittest.main()
