# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Immutable VDP 2.0.0 release profile."""

from ..bridge import SignalSpec, finite_float, nonnegative_float, uint8_percent


VERSION = "2.0.0"
MANIFEST_SHA256 = "6abda9b8771d01fa5fe2ce4280cf164973c4944739c732d0326134e4cf43e629"
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
)
CAPABILITIES = ("INBOUND_BASE_DYNAMICS", "INBOUND_WHEEL_SPEEDS")
ADVISORY_ENDPOINT_IDS: tuple[str, ...] = ()
