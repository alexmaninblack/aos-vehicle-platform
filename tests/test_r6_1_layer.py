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

    def test_provider_has_bounded_credentials_and_dns_access(self) -> None:
        policy = validate_r6_1_layer.POLICY.read_text(encoding="utf-8")
        self.assertIn("sysnet_dns_name_resolve(vehicle_data_provider_t)", policy)
        self.assertIn("dev_read_urand(vehicle_data_provider_t)", policy)
        self.assertIn(
            "allow vehicle_data_provider_t initrc_runtime_t:dir { getattr search };",
            policy,
        )
        self.assertIn(
            "allow vehicle_data_provider_t initrc_runtime_t:file { getattr open read };",
            policy,
        )
        self.assertEqual(
            [
                line.strip()
                for line in policy.splitlines()
                if "vehicle_data_provider_t initrc_runtime_t:" in line
            ],
            [
                "allow vehicle_data_provider_t initrc_runtime_t:dir "
                "{ getattr search };",
                "allow vehicle_data_provider_t initrc_runtime_t:file "
                "{ getattr open read };",
            ],
        )

    def test_kuksa_is_ordered_but_not_a_hard_lifecycle_dependency(self) -> None:
        unit = validate_r6_1_layer.UNIT.read_text(encoding="utf-8")
        self.assertIn(
            "After=network-online.target kuksa-databroker.service", unit
        )
        self.assertIn(
            "Wants=network-online.target kuksa-databroker.service", unit
        )
        self.assertNotIn("Requires=kuksa-databroker.service", unit)

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

    def test_provider_launcher_verifies_a_dedicated_non_root_identity(self) -> None:
        launcher = validate_r6_1_layer.LAUNCHER.read_text(encoding="utf-8")
        unit = validate_r6_1_layer.UNIT.read_text(encoding="utf-8")
        selftest = validate_r6_1_layer.SELFTEST_UNIT.read_text(encoding="utf-8")
        recipe = validate_r6_1_layer.PLATFORM_RECIPE.read_text(encoding="utf-8")
        policy = validate_r6_1_layer.POLICY.read_text(encoding="utf-8")
        self.assertIn("User=aos-vdp", unit)
        self.assertIn("ExecStart=/usr/libexec/", unit)
        self.assertIn("CapabilityBoundingSet=\n", unit)
        self.assertNotIn("DynamicUser=", unit)
        self.assertNotIn("NoNewPrivileges=", unit)
        self.assertIn("User=aos-vdp", selftest)
        self.assertIn("ExecStart=/usr/libexec/", selftest)
        self.assertIn("CapabilityBoundingSet=\n", selftest)
        self.assertIn("inherit systemd useradd", recipe)
        self.assertIn("PR_SET_NO_NEW_PRIVS", launcher)
        self.assertIn("allow vehicle_data_provider_t self:process getcap;", policy)
        self.assertIn("getgroups(1, &supplementary_group)", launcher)
        self.assertNotIn("setgroups", launcher)
        self.assertNotIn("setresuid", launcher)
        self.assertNotIn("setresgid", launcher)
        self.assertNotIn("initgroups", launcher)
        self.assertIn(
            "allow vehicle_data_provider_t self:fifo_file rw_fifo_file_perms;",
            policy,
        )
        self.assertIn(
            "init_rw_script_stream_sockets(vehicle_data_provider_t)", policy
        )
        self.assertNotIn(
            "systemd_tmpfilesd_managed(vehicle_data_provider_store_t)", policy
        )
        self.assertNotIn("self:capability { setgid setuid }", policy)
        self.assertLess(
            launcher.index("getgroups(1, &supplementary_group)"),
            launcher.index("PR_SET_NO_NEW_PRIVS"),
        )
        self.assertLess(
            launcher.index("PR_SET_NO_NEW_PRIVS"), launcher.index("execv(executable")
        )

    def test_demo_store_is_fixed_bounded_and_non_destructive(self) -> None:
        prepare = validate_r6_1_layer.STORE_PREPARE.read_text(encoding="utf-8")
        check = validate_r6_1_layer.STORE_CHECK.read_text(encoding="utf-8")
        mount = validate_r6_1_layer.STORE_MOUNT.read_text(encoding="utf-8")
        self.assertIn(f"store_size={validate_r6_1_layer.STORE_SIZE}", prepare)
        self.assertIn(
            f"backing_file={validate_r6_1_layer.STORE_BACKING}", prepare
        )
        self.assertIn('rm -f -- "$partial_file"', prepare)
        self.assertIn(
            'dd if=/dev/zero of="$partial_file" bs=1048576 count=512', prepare
        )
        self.assertIn("conv=fsync status=none", prepare)
        self.assertIn(
            "-E nodiscard,lazy_itable_init=0,lazy_journal_init=0", prepare
        )
        self.assertNotIn("fallocate", prepare)
        self.assertNotRegex(prepare, r"rm[^\n]*\$backing_file")
        self.assertNotRegex(prepare, r"mkfs[^\n]*\$backing_file")
        self.assertNotIn("AOS_", prepare)
        self.assertNotIn("AOS_", check)
        self.assertIn(
            'store_parent_options=$(findmnt -rn -T "$store_parent" -o OPTIONS)',
            prepare,
        )
        self.assertNotIn("fail 'workdirs is not writable'", prepare)
        self.assertIn("store backing file is sparse or incompletely allocated", check)
        self.assertNotRegex(check, r"blkid[^\n]*\$backing_file")
        self.assertIn(
            'blkid -p -s UUID -o value "$mount_source"', check
        )
        self.assertIn(
            "runtime_loop=/run/aos-vehicle-data-provider-store/loop", check
        )
        self.assertNotIn("losetup", check)
        self.assertNotIn(
            f"Z {validate_r6_1_layer.COMPONENT_ROOT}",
            validate_r6_1_layer.TMPFILES.read_text(encoding="utf-8"),
        )
        self.assertIn("Options=nodev,nosuid,noatime,errors=remount-ro", mount)
        self.assertNotIn("Options=loop,", mount)
        self.assertNotIn("noexec", mount)

    def test_store_loop_administration_is_fixed_and_confined(self) -> None:
        helper = validate_r6_1_layer.LOOP_HELPER.read_text(encoding="utf-8")
        prepare = validate_r6_1_layer.STORE_PREPARE.read_text(encoding="utf-8")
        prepare_unit = validate_r6_1_layer.STORE_PREPARE_UNIT.read_text(
            encoding="utf-8"
        )
        attach_unit = validate_r6_1_layer.STORE_ATTACH_UNIT.read_text(
            encoding="utf-8"
        )
        mount = validate_r6_1_layer.STORE_MOUNT.read_text(encoding="utf-8")
        policy = validate_r6_1_layer.POLICY.read_text(encoding="utf-8")
        self.assertIn(validate_r6_1_layer.STORE_BACKING, helper)
        self.assertIn("O_NOFOLLOW", helper)
        self.assertNotIn("argv[2]", helper)
        self.assertNotIn("aos-vehicle-data-provider-loop", prepare)
        self.assertIn("CapabilityBoundingSet=\n", prepare_unit)
        self.assertNotIn("CAP_SYS_ADMIN", prepare_unit)
        self.assertIn("CapabilityBoundingSet=CAP_SYS_ADMIN", attach_unit)
        self.assertIn("AmbientCapabilities=\n", attach_unit)
        self.assertNotIn("NoNewPrivileges=yes", attach_unit)
        self.assertIn(
            "ExecStart=/usr/libexec/aos-vehicle-data-provider-loop attach",
            attach_unit,
        )
        self.assertIn(
            "ExecStop=/usr/libexec/aos-vehicle-data-provider-loop detach",
            attach_unit,
        )
        self.assertIn("What=/run/aos-vehicle-data-provider-store/loop", mount)
        self.assertIn("vehicle_data_provider_store_admin_t", policy)
        self.assertIn("vehicle_data_provider_store_prepare_t", policy)
        self.assertIn("vehicle_data_provider_store_runtime_t", policy)
        self.assertIn(
            "allow vehicle_data_provider_store_admin_t self:capability sys_admin;",
            policy,
        )
        self.assertIn(
            "allow mount_t vehicle_data_provider_store_runtime_t:lnk_file "
            "read_lnk_file_perms;",
            policy,
        )
        self.assertIn(
            "fstools_exec(vehicle_data_provider_store_prepare_t)", policy
        )
        self.assertIn(
            "allow vehicle_data_provider_store_prepare_t "
            "aos_var_run_t:filesystem getattr;",
            policy,
        )
        self.assertIn(
            "allow vehicle_data_provider_store_admin_t "
            "aos_var_run_t:filesystem getattr;",
            policy,
        )
        self.assertIn(
            "allow mount_t vehicle_data_provider_store_t:filesystem relabelfrom;",
            policy,
        )
        self.assertNotIn("fstools_domtrans(vehicle_data_provider_store_prepare_t)", policy)
        self.assertNotIn("mount_t aos_var_run_t", policy)

    def test_store_parent_layout_is_separate_and_unprivileged(self) -> None:
        layout = validate_r6_1_layer.STORE_LAYOUT.read_text(encoding="utf-8")
        layout_unit = validate_r6_1_layer.STORE_LAYOUT_UNIT.read_text(
            encoding="utf-8"
        )
        prepare_unit = validate_r6_1_layer.STORE_PREPARE_UNIT.read_text(
            encoding="utf-8"
        )
        self.assertIn("service_manager_root=/var/aos/workdirs/sm", layout)
        self.assertIn("runtime_root=/var/aos/workdirs/sm/runtimes", layout)
        self.assertNotIn("rm ", layout)
        self.assertIn("ReadWritePaths=/var/aos/workdirs", layout_unit)
        self.assertIn("CapabilityBoundingSet=\n", layout_unit)
        self.assertNotIn("CAP_SYS_ADMIN", layout_unit)
        self.assertIn(
            "Requires=var-aos-workdirs.mount "
            "aos-vehicle-data-provider-store-layout.service",
            prepare_unit,
        )
        self.assertIn(
            "ReadWritePaths=/var/aos/workdirs/sm/runtimes", prepare_unit
        )

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
        self.assertIn(
            "init_rw_script_stream_sockets(vehicle_data_provider_store_prepare_t)",
            policy,
        )
        self.assertIn(
            "kernel_read_system_state(vehicle_data_provider_store_prepare_t)",
            policy,
        )
        self.assertIn(
            "allow vehicle_data_provider_store_prepare_t self:fifo_file "
            "rw_fifo_file_perms;",
            policy,
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
