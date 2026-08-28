# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Immutable VDP 3.0.0 release profile."""

from ..bridge import SignalSpec, finite_float, nonnegative_float, uint8_percent


VERSION = "3.0.0"
MANIFEST_SHA256 = "8b89a0b1afe715b86ac597628569ed46457327dbe23bf60ce18d893b1294680f"
SIGNALS = (
    SignalSpec("Vehicle.Speed", nonnegative_float),
    SignalSpec("Vehicle.Acceleration.Longitudinal", finite_float),
    SignalSpec("Vehicle.Acceleration.Lateral", finite_float),
    SignalSpec("Vehicle.Acceleration.Vertical", finite_float),
    SignalSpec("Vehicle.Chassis.Accelerator.PedalPosition", uint8_percent),
    SignalSpec("Vehicle.Chassis.Brake.PedalPosition", uint8_percent),
    SignalSpec("Vehicle.Chassis.Axle.Row1.SteeringAngle", finite_float),
    SignalSpec("Vehicle.Chassis.Axle.Row1.Wheel.Left.AngularSpeed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row1.Wheel.Right.AngularSpeed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row2.Wheel.Left.AngularSpeed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row2.Wheel.Right.AngularSpeed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row1.Wheel.Left.Speed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row1.Wheel.Right.Speed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row2.Wheel.Left.Speed", nonnegative_float),
    SignalSpec("Vehicle.Chassis.Axle.Row2.Wheel.Right.Speed", nonnegative_float),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row1.Left.LongitudinalSlip",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row1.Right.LongitudinalSlip",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row2.Left.LongitudinalSlip",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row2.Right.LongitudinalSlip",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row1.Left.LateralSlipAngle",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row1.Right.LateralSlipAngle",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row2.Left.LateralSlipAngle",
        finite_float,
    ),
    SignalSpec(
        "Vehicle.CarlaSimulation.ChaosWheel.Row2.Right.LateralSlipAngle",
        finite_float,
    ),
)
CAPABILITIES = (
    "INBOUND_BASE_DYNAMICS",
    "INBOUND_WHEEL_SPEEDS",
    "INBOUND_WHEEL_SLIP",
    "OUTBOUND_BRAKE_HEALTH_ADVISORY",
    "OUTBOUND_TIRE_HEALTH_ADVISORY",
)
ADVISORY_ENDPOINT_IDS = (
    "BRAKE_HEALTH_ADVISORY",
    "TIRE_HEALTH_ADVISORY",
)
