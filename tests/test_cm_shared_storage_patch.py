# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Recipe/source gates; behavior is tested in the native CM launcher suite."""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager"
NAME = "0002-mainline-cm-instance-lifecycle.patch"
PATCH = RECIPE / "files" / NAME
PRODUCT_FILES = {
    "src/core/cm/launcher/instance.cpp",
    "src/core/cm/launcher/instance.hpp",
    "src/core/cm/launcher/instancemanager.cpp",
    "src/core/cm/launcher/instancemanager.hpp",
    "src/core/cm/launcher/launcher.cpp",
}
TEST_FILES = {
    "src/core/cm/launcher/tests/CMakeLists.txt",
    "src/core/cm/launcher/tests/storage_retention.cpp",
    "src/core/cm/launcher/tests/launcher.cpp",
}


class CMSharedStoragePatchTests(unittest.TestCase):
    def test_recipe_applies_to_pinned_mainline_library_once(self):
        recipe = (RECIPE / "aos-communicationmanager_git.bbappend").read_text()
        self.assertEqual(recipe.count("file://" + NAME), 1)
        self.assertIn("file://" + NAME + ";patchdir=../service-update-deps/aos_core_lib_cpp", recipe)
        self.assertIn('SRCREV_serviceupdatelib = "5560291ba6914e36a5b841ade4d8fc54134a9e91"', recipe)
        self.assertIn("-DAOS_CONFIG_TYPES_FUNCTION_LEN=256", recipe)

    def test_patch_has_only_launcher_and_regression_scope(self):
        patch = PATCH.read_text()
        paths = set(re.findall(r"^diff --git a/(\S+) b/\S+$", patch, re.MULTILINE))
        self.assertEqual(paths, PRODUCT_FILES | TEST_FILES)
        self.assertIn("Upstream-Status: Pending", patch)
        self.assertNotIn("/var/aos/", patch)
        self.assertNotIn("brake-health", patch)

    def test_applies_to_pristine_pinned_source_and_retains_complete_identity_check(self):
        configured = os.environ.get("AOS_CORE_LIB_SOURCE")
        if not configured:
            self.skipTest("Set AOS_CORE_LIB_SOURCE to a repository containing the mainline pin")
        source = Path(configured)
        existing = PRODUCT_FILES | (TEST_FILES - {"src/core/cm/launcher/tests/storage_retention.cpp"})
        with tempfile.TemporaryDirectory(prefix="cm-storage-patch-") as directory:
            root = Path(directory)
            for path in existing:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_bytes(subprocess.check_output([
                    "git", "show", "5560291ba6914e36a5b841ade4d8fc54134a9e91:" + path], cwd=source))
            subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=root, check=True)
            subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True)
            manager = (root / "src/core/cm/launcher/instancemanager.cpp").read_text()
            self.assertIn("candidate.Get() != &instance", manager)
            self.assertIn("candidate->GetInfo().mInstanceIdent == instance.GetInfo().mInstanceIdent", manager)
            for owners in ("mActiveInstances", "mCachedInstances", "mScheduledInstances"):
                self.assertIn(owners + ".ContainsIf(otherOwner)", manager)
            self.assertIn("Failed retirement must remain visible", manager)
            self.assertIn("return RemoveInstances(mCachedInstances", manager)
            instance = (root / "src/core/cm/launcher/instance.cpp").read_text()
            self.assertIn("if (mUIDAcquired)", instance)
            self.assertIn("if (mGIDAcquired)", instance)


if __name__ == "__main__":
    unittest.main()
