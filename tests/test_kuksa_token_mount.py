# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Source-equivalent mount option tests, not native SM/live mount qualification."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files"


class KuksaTokenMountTests(unittest.TestCase):
    def test_exact_owner_options_and_negative_boundaries(self):
        compiler = shutil.which("c++")
        self.assertIsNotNone(compiler, "C++ compiler required for the affected mount option gate")
        with tempfile.TemporaryDirectory(prefix="kac-mount-test-") as temporary:
            binary = Path(temporary) / "test"
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I", str(FILES), str(ROOT / "tests/kuksa_token_mount_test.cpp"), "-o", str(binary)],
                check=True, timeout=30, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, timeout=5, capture_output=True, text=True)

    def test_recipe_and_native_hook_use_actual_instance_not_fixed_owner(self):
        patch = (FILES / "0002-bind-kuksa-token-tmpfs-to-instance-owner.patch").read_text()
        self.assertIn("mInstanceInfo.mUID, mInstanceInfo.mGID", patch)
        self.assertIn("std::make_unique<Mount>(mount)", patch)
        self.assertIn("AddMount(*instanceMount, runtimeConfig)", patch)
        self.assertNotIn("uid=5000", patch)
        recipe = (FILES.parent / "aos-servicemanager_git.bbappend").read_text()
        self.assertIn("file://0002-bind-kuksa-token-tmpfs-to-instance-owner.patch", recipe)
        self.assertIn("${S}/src/sm/launcher/runtimes/container/kuksatokenmount.hpp", recipe)


if __name__ == "__main__":
    unittest.main()
