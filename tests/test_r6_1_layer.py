# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Tests for the R6.1-2 Yocto bootstrap layer validator."""

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


if __name__ == "__main__":
    unittest.main()
