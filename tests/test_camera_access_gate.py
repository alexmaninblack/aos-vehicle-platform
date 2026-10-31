# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""The source scenario cannot silently modify retained product inputs."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("camera_access_gate", ROOT/"tools/check_camera_access.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CameraGateTests(unittest.TestCase):
    def test_empty_or_exact_packet_source_is_allowed(self):
        self.assertTrue(MODULE.preserved_source([]))
        self.assertTrue(MODULE.preserved_source(["camera-access/src/aos_camera_access/core.py", "contracts/camera-access/profile.json", "README.md"]))

    def test_old_vdp_factory_credentials_and_caches_are_outside_the_packet(self):
        for path in ("providers/carla-viss-kuksa/provider.py", "meta-aos-vehicle-platform/recipes-aos/new.bb",
                     "packaging/fota/build.py", "credentials/current", "cache/object", "workspace/inputs.json"):
            with self.subTest(path=path):
                self.assertFalse(MODULE.preserved_source([path]))

    def test_prefix_lookalike_is_rejected(self):
        self.assertFalse(MODULE.preserved_source(["camera-access-other/unsafe.py"]))


if __name__ == "__main__":
    unittest.main()
