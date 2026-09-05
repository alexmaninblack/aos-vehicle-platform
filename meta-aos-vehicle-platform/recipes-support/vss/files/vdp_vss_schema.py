# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Build-time VDP telemetry schema composition; no runtime authority changes."""

import json

BASE_PATHS = (
    "Vehicle.Speed",
    "Vehicle.Acceleration.Longitudinal",
    "Vehicle.Acceleration.Lateral",
    "Vehicle.Acceleration.Vertical",
    "Vehicle.Chassis.Accelerator.PedalPosition",
    "Vehicle.Chassis.Brake.PedalPosition",
    "Vehicle.Chassis.Axle.Row1.SteeringAngle",
)
WHEEL_PATHS = tuple(
    "Vehicle.Chassis.Axle." + row + ".Wheel." + side + "." + signal
    for signal in ("AngularSpeed", "Speed")
    for row in ("Row1", "Row2") for side in ("Left", "Right")
)
SLIP_PATHS = tuple(
    "Vehicle.CarlaSimulation.ChaosWheel." + row + "." + side + "." + signal
    for signal in ("LongitudinalSlip", "LateralSlipAngle")
    for row in ("Row1", "Row2") for side in ("Left", "Right")
)


def lookup(schema, name):
    children = schema
    parts = name.split(".")
    for index, part in enumerate(parts):
        node = children.get(part)
        if not isinstance(node, dict):
            raise ValueError("Missing VDP schema path: " + name)
        if index < len(parts) - 1:
            if node.get("type") != "branch" or not isinstance(node.get("children"), dict):
                raise ValueError("VDP schema branch conflict: " + name)
            children = node["children"]
    return node


def validate(schema):
    for name in BASE_PATHS + WHEEL_PATHS + SLIP_PATHS:
        leaf = lookup(schema, name)
        datatype = "uint8" if name.endswith("PedalPosition") else "float"
        if leaf.get("type") != "sensor" or leaf.get("datatype") != datatype:
            raise ValueError("VDP schema type conflict: " + name)


def supplement(schema):
    result = json.loads(json.dumps(schema))
    for name in SLIP_PATHS:
        current = result
        parts = name.split(".")
        for part in parts[:-1]:
            branch = current.setdefault(part, dict(type="branch", description=part, children={}))
            if not isinstance(branch, dict) or branch.get("type") != "branch" or not isinstance(branch.get("children"), dict):
                raise ValueError("VDP schema branch conflict: " + name)
            current = branch["children"]
        signal = parts[-1]
        leaf = dict(type="sensor", datatype="float", description=(
            "CARLA Chaos wheel lateral slip angle in degrees." if signal == "LateralSlipAngle" else
            "CARLA Chaos wheel dimensionless longitudinal slip ratio."))
        if signal == "LateralSlipAngle":
            leaf["unit"] = "degrees"
        if signal in current and current[signal] != leaf:
            raise ValueError("VDP schema leaf conflict: " + name)
        current.setdefault(signal, leaf)
    validate(result)
    return result


def transform(path):
    result = supplement(json.loads(path.read_bytes()))
    path.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
