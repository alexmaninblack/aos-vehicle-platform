# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/validate_contract.py"
SPEC = importlib.util.spec_from_file_location("validate_contract", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = VALIDATOR.load_profile(VALIDATOR.DEFAULT_PROFILE)

    def test_published_profile_is_valid(self) -> None:
        VALIDATOR.validate_profile(self.profile)

    def test_superseded_profile_remains_valid(self) -> None:
        historical = VALIDATOR.load_profile(
            ROOT / "contracts/vehicle-telemetry-profile/v0.1/profile.json"
        )
        VALIDATOR.validate_profile(historical)

    def test_carla_overlay_is_rejected(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["signals"][0]["path"] = "Vehicle.CarlaSimulation.Frame"
        with self.assertRaisesRegex(VALIDATOR.ContractError, "CARLA-specific"):
            VALIDATOR.validate_profile(profile)

    def test_permission_must_match_signal_path(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["signals"][0]["permissions"]["consumer"] = "read:Vehicle.Acceleration.Longitudinal"
        with self.assertRaisesRegex(VALIDATOR.ContractError, "least-privilege"):
            VALIDATOR.validate_profile(profile)

    def test_stale_values_cannot_be_substituted(self) -> None:
        profile = copy.deepcopy(self.profile)
        profile["defaults"]["unavailableBehavior"] = "substitute-zero"
        with self.assertRaisesRegex(VALIDATOR.ContractError, "must not be substituted"):
            VALIDATOR.validate_profile(profile)


if __name__ == "__main__":
    unittest.main()
