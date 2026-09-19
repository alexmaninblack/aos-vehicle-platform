# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Packaging gates; behavioral proof lives in the solution's native harness."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager"
NAME = "0006-notify-outside-transport-lock.patch"
PATCH = RECIPE / "files" / NAME


class CMDisconnectLockPatchTests(unittest.TestCase):
    def test_recipe_includes_fix_once_without_repinning_library(self):
        text = (RECIPE / "aos-communicationmanager_git.bbappend").read_text()
        self.assertEqual(text.count("file://" + NAME), 1)
        self.assertIn('SRCREV_serviceupdatelib = "60cb83535f773762c61ac5f544b31b7b88c502e3"', text)
        self.assertIn(' -DAOS_CONFIG_TYPES_FUNCTION_LEN=256', text)

    def test_patch_scope_and_review_status(self):
        text = PATCH.read_text()
        paths = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
        self.assertEqual(set(paths), {"src/cm/communication/communication.cpp",
                                     "src/cm/communication/communication.hpp"})
        self.assertIn("Upstream-Status: Pending", text)
        self.assertIn("std::atomic_bool", text)

    def test_patch_applies_to_cached_native_source(self):
        source = ROOT / "build/aos_core_cpp"
        files = ["src/cm/communication/communication.cpp", "src/cm/communication/communication.hpp"]
        if not all((source / file).is_file() for file in files):
            self.skipTest("Pinned native checkout is not available locally")
        with tempfile.TemporaryDirectory(prefix="cm-lock-patch-") as directory:
            root = Path(directory)
            for file in files:
                (root / file).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / file, root / file)
            subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=root, check=True)
            subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True)
            text = (root / files[0]).read_text()
            close = text.split("Error Communication::CloseConnection()", 1)[1].split(
                "Error Communication::Disconnect()", 1)[0]
            self.assertNotIn("NotifyConnectionLost()", close)
            self.assertEqual(text.count("connectionLock {mConnectionMutex}"), 3)
            self.assertIn("mIsConnected.exchange(false)", text)
            self.assertIn("return mIsConnected.load();", text)


if __name__ == "__main__":
    unittest.main()
