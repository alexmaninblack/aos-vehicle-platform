# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Recipe parity and focused native permission-key storage regression."""

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / "meta-aos-vehicle-platform/recipes-aos"


class PermissionKeyCapacityTests(unittest.TestCase):
    def test_iam_response_uses_registered_function_map_capacity(self):
        recipe = RECIPES / "aos-iamanager/aos-iamanager_git.bbappend"
        name = "0001-use-function-count-for-permission-response.patch"
        self.assertIn('SRC_URI += "file://' + name + '"', recipe.read_text())
        patch = (recipe.parent / "files" / name).read_text()
        removed = [line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]
        added = [line for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++")]
        self.assertEqual(1, len(removed))
        self.assertIn(removed[0].replace("-", "+", 1).replace("cFuncServiceMaxCount", "cFunctionsMaxCount"), added)
        self.assertIn("src/iam/iamserver/publicmessagehandler.cpp", patch)
        self.assertIn("RepliesWithAll32LongFunctionKeysWithoutTruncation", patch)

    def test_all_managers_compile_all_cpp_units_with_the_same_capacity(self):
        for recipe in ("aos-communicationmanager", "aos-servicemanager", "aos-iamanager"):
            text = (RECIPES / recipe / (recipe + "_git.bbappend")).read_text()
            self.assertEqual(["256"], re.findall(r"-DAOS_CONFIG_TYPES_FUNCTION_LEN=(\d+)", text))
            self.assertIn('CXXFLAGS:append = " -DAOS_CONFIG_TYPES_FUNCTION_LEN=256"', text)
            self.assertNotIn("-DAOS_CONFIG_TYPES_PERMISSIONS_LEN=", text)
            self.assertNotIn("-DAOS_CONFIG_TYPES_FUNCTIONS_MAX_COUNT=", text)

    def test_native_capacity_before_and_after(self):
        source = Path(os.environ.get("AOS_CORE_LIB_SOURCE", ROOT / "build/aos_core_lib_cpp"))
        include = source / "src"
        header = include / "core/common/types/permissions.hpp"
        if not header.is_file():
            self.skipTest("Set AOS_CORE_LIB_SOURCE to the pinned local Core library for native compilation")
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        if not compiler or not shutil.which(compiler[0]):
            self.skipTest("A C++ compiler is required for the native storage regression")
        # Keep the portable fixture tied to the production field, not a mock
        # of its implementation. The native parser uses this Assign method.
        self.assertRegex(header.read_text(), r"StaticString<cFunctionLen>\s+mFunction;")
        self.assertIn("cFunctionLen = AOS_CONFIG_TYPES_FUNCTION_LEN", header.read_text())
        fixture = ROOT / "tests/fixtures/permission_key_capacity.cpp"
        with tempfile.TemporaryDirectory(prefix="aos-permission-key-") as temporary:
            for capacity, accepted, flags in ((32, 3, []), (256, 6, ["-DAOS_CONFIG_TYPES_FUNCTION_LEN=256"])):
                executable = Path(temporary) / ("capacity-" + str(capacity))
                built = subprocess.run(compiler + ["-std=c++17", "-Wall", "-Wextra", "-Werror"]
                    + flags + ["-I", str(include), str(fixture), "-o", str(executable)],
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(0, built.returncode, built.stdout + built.stderr)
                result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=5)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(
                    f"capacity={capacity} accepted={accepted} rejected={6 - accepted} boundary=PASS repeat=PASS\n",
                    result.stdout)


if __name__ == "__main__":
    unittest.main()
