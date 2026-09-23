# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Packaging gates; behavioral proof lives in the solution's native harness."""
from pathlib import Path
import os
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
    def test_recipe_includes_fix_once_with_coordinated_mainline_pin(self):
        text = (RECIPE / "aos-communicationmanager_git.bbappend").read_text()
        self.assertEqual(text.count("file://" + NAME), 1)
        self.assertIn('SRCREV_serviceupdatelib = "5560291ba6914e36a5b841ade4d8fc54134a9e91"', text)
        self.assertIn(' -DAOS_CONFIG_TYPES_FUNCTION_LEN=256', text)

    def test_patch_scope_and_review_status(self):
        text = PATCH.read_text()
        paths = re.findall(r"^diff --git a/(\S+) b/\S+$", text, re.MULTILINE)
        self.assertEqual(set(paths), {"src/cm/communication/communication.cpp",
                                     "src/cm/communication/communication.hpp"})
        self.assertIn("Upstream-Status: Pending", text)
        self.assertIn("std::atomic_bool", text)

    def test_patch_applies_to_pristine_pinned_mainline_source(self):
        configured = os.environ.get("AOS_CORE_APP_SOURCE")
        if not configured:
            self.skipTest("Set AOS_CORE_APP_SOURCE to a repository containing the mainline pin")
        source = Path(configured)
        files = ["src/cm/communication/communication.cpp", "src/cm/communication/communication.hpp"]
        with tempfile.TemporaryDirectory(prefix="cm-lock-patch-") as directory:
            root = Path(directory)
            for file in files:
                (root / file).parent.mkdir(parents=True, exist_ok=True)
                (root / file).write_bytes(subprocess.check_output([
                    "git", "show", "9d613a46df3c7f550062e2f19ae3406c57715694:" + file], cwd=source))
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
