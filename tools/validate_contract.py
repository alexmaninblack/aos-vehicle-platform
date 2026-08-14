#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate the platform-owned vehicle telemetry contract without dependencies."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "contracts/vehicle-telemetry-profile/v0.1/profile.json"
EXPECTED_SIGNALS = {
    "Vehicle.Speed": ("float", "km/h"),
    "Vehicle.Acceleration.Longitudinal": ("float", "m/s^2"),
    "Vehicle.Acceleration.Lateral": ("float", "m/s^2"),
    "Vehicle.Acceleration.Vertical": ("float", "m/s^2"),
    "Vehicle.Chassis.Accelerator.PedalPosition": ("uint8", "percent"),
    "Vehicle.Chassis.Brake.PedalPosition": ("uint8", "percent"),
    "Vehicle.Chassis.Axle.Row1.SteeringAngle": ("float", "degree"),
}


class ContractError(ValueError):
    """Raised when a profile violates the project contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _require_finite_number(value: Any, label: str) -> None:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        f"{label} must be a finite number",
    )


def load_profile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    _require(isinstance(value, dict), "profile root must be an object")
    return value


def validate_profile(profile: dict[str, Any]) -> None:
    _require(profile.get("schemaVersion") == 1, "schemaVersion must be 1")
    _require(
        profile.get("license")
        == {"copyright": "2026 maninblack", "spdx": "Apache-2.0"},
        "profile license metadata is missing or incorrect",
    )

    contract = profile.get("contract")
    _require(isinstance(contract, dict), "contract must be an object")
    version = contract.get("version", "")
    _require(
        isinstance(version, str) and re.fullmatch(r"0\.[0-9]+\.[0-9]+", version),
        "R-2 contract version must be semantic version 0.x",
    )
    _require(contract.get("status") == "draft", "R-2 contract must remain draft")

    compatibility = profile.get("compatibility")
    expected_compatibility = {
        "brokerVssVersion": "5.0",
        "sourceVssVersion": "6.0",
        "kuksaDatabrokerVersion": "0.5.0",
        "kuksaApi": "kuksa.val.v1",
        "architecture": "arm64",
    }
    _require(
        compatibility == expected_compatibility,
        "prototype compatibility pins do not match the approved R-2 baseline",
    )

    defaults = profile.get("defaults")
    _require(isinstance(defaults, dict), "defaults must be an object")
    nominal = defaults.get("nominalUpdateRateHz")
    minimum = defaults.get("minimumUpdateRateHz")
    freshness = defaults.get("freshnessTimeoutMs")
    _require_finite_number(nominal, "nominalUpdateRateHz")
    _require_finite_number(minimum, "minimumUpdateRateHz")
    _require(nominal >= minimum > 0, "update rates must satisfy nominal >= minimum > 0")
    _require(
        isinstance(freshness, int) and not isinstance(freshness, bool) and freshness > 0,
        "freshnessTimeoutMs must be a positive integer",
    )
    _require(
        freshness >= math.ceil(1000 / minimum),
        "freshness timeout must be at least one minimum-rate frame",
    )
    _require(defaults.get("staleBehavior") == "mark-unavailable", "stale values must become unavailable")
    _require(defaults.get("unavailableBehavior") == "do-not-substitute", "unavailable values must not be substituted")

    signals = profile.get("signals")
    _require(isinstance(signals, list), "signals must be an array")
    paths: list[str] = []
    for index, signal in enumerate(signals):
        _require(isinstance(signal, dict), f"signals[{index}] must be an object")
        path = signal.get("path")
        _require(isinstance(path, str), f"signals[{index}].path must be a string")
        _require("CarlaSimulation" not in path, f"{path} is a CARLA-specific overlay path")
        paths.append(path)

        expected_type_unit = EXPECTED_SIGNALS.get(path)
        _require(expected_type_unit is not None, f"unexpected signal path: {path}")
        _require(
            (signal.get("datatype"), signal.get("unit")) == expected_type_unit,
            f"{path} has an unexpected datatype or unit",
        )
        _require(signal.get("required") is True, f"{path} must be part of the required interface")

        permissions = signal.get("permissions")
        _require(isinstance(permissions, dict), f"{path} permissions must be an object")
        _require(permissions.get("provider") == f"provide:{path}", f"{path} provider permission is not least-privilege")
        _require(permissions.get("consumer") == f"read:{path}", f"{path} consumer permission is not least-privilege")

        valid_range = signal.get("validRange")
        _require(isinstance(valid_range, dict), f"{path} validRange must be an object")
        kind = valid_range.get("kind")
        _require(kind in {"finite", "minimum", "closed"}, f"{path} has an unsupported range kind")
        if kind in {"minimum", "closed"}:
            _require_finite_number(valid_range.get("minimum"), f"{path} minimum")
        if kind == "closed":
            _require_finite_number(valid_range.get("maximum"), f"{path} maximum")
            _require(valid_range["minimum"] <= valid_range["maximum"], f"{path} range is inverted")

    _require(len(paths) == len(set(paths)), "signal paths must be unique")
    _require(set(paths) == set(EXPECTED_SIGNALS), "profile must contain the approved R-2 signal set")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    try:
        profile = load_profile(args.profile)
        validate_profile(profile)
    except ContractError as exc:
        print(f"Contract validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Contract {profile['contract']['version']} is valid: {args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
