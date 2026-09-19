# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Recipe/source gates; behavior is tested in the native CM launcher suite."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager"
NAME = "0007-preserve-shared-instance-storage.patch"
PATCH = RECIPE / "files" / NAME
PRODUCT_FILES = {
    "src/core/cm/launcher/instance.cpp",
    "src/core/cm/launcher/instance.hpp",
    "src/core/cm/launcher/instancemanager.cpp",
    "src/core/cm/launcher/instancemanager.hpp",
}
TEST_FILES = {
    "src/core/cm/launcher/tests/CMakeLists.txt",
    "src/core/cm/launcher/tests/storage_retention.cpp",
}


class CMSharedStoragePatchTests(unittest.TestCase):
    def test_recipe_applies_to_pinned_library_once_after_connection_fix(self):
        recipe = (RECIPE / "aos-communicationmanager_git.bbappend").read_text()
        self.assertEqual(recipe.count("file://" + NAME), 1)
        self.assertIn("file://" + NAME + ";patchdir=../service-update-deps/aos_core_lib_cpp", recipe)
        self.assertIn('SRCREV_serviceupdatelib = "60cb83535f773762c61ac5f544b31b7b88c502e3"', recipe)
        self.assertLess(recipe.index("0006-notify"), recipe.index(NAME))
        self.assertIn("-DAOS_CONFIG_TYPES_FUNCTION_LEN=256", recipe)

    def test_patch_has_only_launcher_and_regression_scope(self):
        patch = PATCH.read_text()
        paths = set(re.findall(r"^diff --git a/(\S+) b/\S+$", patch, re.MULTILINE))
        self.assertEqual(paths, PRODUCT_FILES | TEST_FILES)
        self.assertIn("Upstream-Status: Pending", patch)
        self.assertNotIn("/var/aos/", patch)
        self.assertNotIn("brake-health", patch)

    def test_applies_to_cached_source_and_retains_complete_identity_check(self):
        source = ROOT / "build/aos_core_lib_cpp"
        existing = PRODUCT_FILES | {"src/core/cm/launcher/tests/CMakeLists.txt"}
        if not all((source / path).is_file() for path in existing):
            self.skipTest("Cached native library is not available")
        with tempfile.TemporaryDirectory(prefix="cm-storage-patch-") as directory:
            root = Path(directory)
            for path in existing:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / path, root / path)
            subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=root, check=True)
            subprocess.run(["git", "apply", str(PATCH)], cwd=root, check=True)
            manager = (root / "src/core/cm/launcher/instancemanager.cpp").read_text()
            self.assertIn("candidate.Get() != &instance", manager)
            self.assertIn("candidate->GetInfo().mInstanceIdent == instance.GetInfo().mInstanceIdent", manager)
            for owners in ("mActiveInstances", "mCachedInstances", "mScheduledInstances"):
                self.assertIn(owners + ".ContainsIf(otherOwner)", manager)
            self.assertIn("Failed retirement must remain visible", manager)
            self.assertIn("return RemoveInstances(mCachedInstances", manager)


if __name__ == "__main__":
    unittest.main()
