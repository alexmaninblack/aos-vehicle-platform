# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Factory port policy composes normal sysctl inputs without a runtime helper."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "meta-aos-vehicle-platform/recipes-core/images/aos-image-vm.bbappend"
POLICY = "usr/lib/sysctl.d/99-aos-kuksa-ports.conf"


class FactoryReservedPortsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.body = textwrap.dedent(RECIPE.read_text().split("python aos_kuksa_reserved_ports() {\n", 1)[1].split("\n}", 1)[0])

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def apply(self):
        def fatal(message):
            raise ValueError(message)
        exec(self.body, dict(d=SimpleNamespace(getVar=lambda _: str(self.root)), bb=SimpleNamespace(fatal=fatal)))
        return (self.root / POLICY).read_text()

    def test_empty_image_and_repeat_have_one_public_policy_and_finite_ordering(self):
        first = self.apply()
        self.assertIn("net.ipv4.ip_local_reserved_ports = 55555\n", first)
        self.assertEqual(first, self.apply())
        self.assertEqual((self.root / POLICY).stat().st_mode & 0o777, 0o644)
        for unit in ("nfs-mountd.service", "kuksa-databroker.service"):
            text = (self.root / "usr/lib/systemd/system" / (unit + ".d/10-aos-kuksa-ports.conf")).read_text()
            self.assertEqual(text, "[Unit]\nRequires=systemd-sysctl.service\nAfter=systemd-sysctl.service\n")
        self.assertFalse((self.root / "var").exists())
        self.assertNotIn("ExecStart", self.body)
        self.assertNotIn("systemctl", self.body)

    def test_existing_effective_ranges_and_ports_survive(self):
        original = self.write("usr/lib/sysctl.d/60-other.conf", "net/ipv4/ip_local_reserved_ports = 100-102,55554\n")
        self.assertIn("= 100-102,55554-55555\n", self.apply())
        self.assertEqual(original.read_text(), "net/ipv4/ip_local_reserved_ports = 100-102,55554\n")

    def test_directory_precedence_and_last_assignment_match_sysctl(self):
        self.write("usr/lib/sysctl.d/50-ports.conf", "net.ipv4.ip_local_reserved_ports = 100\n")
        self.write("etc/sysctl.d/50-ports.conf", "net.ipv4.ip_local_reserved_ports = 200\n")
        self.write("usr/lib/sysctl.d/60-ports.conf", "net.ipv4.ip_local_reserved_ports = 300\nnet.ipv4.ip_local_reserved_ports = 400\n")
        self.assertIn("= 400,55555\n", self.apply())

    def test_empty_assignment_and_disabled_file_are_not_older_policy(self):
        self.write("usr/lib/sysctl.d/50-ports.conf", "net.ipv4.ip_local_reserved_ports = 100\n")
        mask = self.root / "etc/sysctl.d/50-ports.conf"
        mask.parent.mkdir(parents=True)
        mask.symlink_to("/dev/null")
        self.assertIn("= 55555\n", self.apply())

    def test_image_absolute_symlink_never_reads_host_configuration(self):
        self.write("etc/sysctl.conf", "net.ipv4.ip_local_reserved_ports = 1234\n")
        link = self.root / "etc/sysctl.d/90-sysctl.conf"
        link.parent.mkdir(parents=True)
        link.symlink_to("/etc/sysctl.conf")
        self.assertIn("= 1234,55555\n", self.apply())

    def test_bad_or_later_policy_is_rejected_before_writing(self):
        for value in ("bad", "65536", "102-100", "10,,12"):
            self.write("usr/lib/sysctl.d/60-ports.conf", "net.ipv4.ip_local_reserved_ports = " + value + "\n")
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.apply()
            self.assertFalse((self.root / POLICY).exists())
        self.write("usr/lib/sysctl.d/60-ports.conf", "net.ipv4.ip_local_reserved_ports = 100\n")
        self.write("usr/lib/sysctl.d/99-z-later.conf", "net.ipv4.ip_local_reserved_ports = 200\n")
        with self.assertRaisesRegex(ValueError, "overriding"):
            self.apply()

    def test_masking_the_owned_policy_is_rejected(self):
        self.write("etc/sysctl.d/99-aos-kuksa-ports.conf", "# locally masked\n")
        with self.assertRaisesRegex(ValueError, "masked"):
            self.apply()

    def test_repeat_recomposes_changed_inputs_not_an_old_generated_union(self):
        path = self.write("usr/lib/sysctl.d/60-other.conf", "net.ipv4.ip_local_reserved_ports = 100\n")
        self.assertIn("= 100,55555\n", self.apply())
        path.write_text("net.ipv4.ip_local_reserved_ports = 200\n")
        self.assertIn("= 200,55555\n", self.apply())

    def test_linked_directory_cannot_redirect_image_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "usr/lib/sysctl.d"
        link.parent.mkdir(parents=True)
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Linked"):
            self.apply()
        self.assertEqual(list(outside.iterdir()), [])
