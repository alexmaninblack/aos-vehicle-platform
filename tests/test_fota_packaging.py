# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOTA = ROOT / "packaging/fota"


class FotaPackagingTests(unittest.TestCase):
    def test_unsigned_aos_config_selects_the_fixed_component_contract(self) -> None:
        configuration = json.loads((FOTA / "config.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("publish", configuration)
        self.assertEqual(configuration["schemaVersion"], 2)
        self.assertEqual(len(configuration["items"]), 1)
        item = configuration["items"][0]
        self.assertEqual(item["identity"]["type"], "component")
        self.assertEqual(
            item["identity"]["codename"],
            "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider",
        )
        self.assertEqual(item["version"], "0.2.0")
        self.assertEqual(
            item["images"][0]["archInfo"]["architecture"], "arm64"
        )
        self.assertEqual(
            item["images"][0]["mediaType"],
            "application/vnd.aos.vehicle-data-provider.layer.v1.tar",
        )

    def test_entrypoint_accepts_only_the_two_bootstrap_slots(self) -> None:
        entrypoint = (FOTA / "vehicle-data-provider").read_text(encoding="utf-8")
        self.assertIn("systemd-slot-component/slots/a/bin/vehicle-data-provider", entrypoint)
        self.assertIn("systemd-slot-component/slots/b/bin/vehicle-data-provider", entrypoint)
        self.assertIn("/usr/bin/python3 -I", entrypoint)
        self.assertNotIn("pip install", entrypoint)

    def test_builder_locks_the_normalized_arm64_runtime(self) -> None:
        builder = (FOTA / "build-provider-component").read_text(encoding="utf-8")
        requirements = (
            ROOT / "packaging/aosvm/runtime/requirements-arm64.txt"
        ).read_text(encoding="utf-8")
        for digest in (
            "c60404292e5ded4e0436b1c8568e9daf4981c4db94907b96f482173ed9ce2c4a",
            "36764a4ad9dc1eb891042fab51e8cdf7cc014ad82cee807c10796fb708455041",
            "a8866b2cff111f0f863c1b3b9e7572dc7eaea23a7fae27f6fc613304046483e6",
            "e8b56bdcdb4505c8078cb6c7157d9811a85790f2f2b3632c7d1462ab5783d215",
            "f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548",
        ):
            self.assertIn(digest, builder)
            self.assertIn(digest, requirements)
        self.assertIn('"grpc/_cython/_credentials/roots.pem"', builder)
        self.assertIn("tarfile.USTAR_FORMAT", builder)


if __name__ == "__main__":
    unittest.main()
