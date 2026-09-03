# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Immutable VDP 1.0.14 release profile."""

from ..bridge import SignalSpec, finite_float, nonnegative_float, uint8_percent


VERSION = "1.0.14"
MANIFEST_SHA256 = "a67c7a1e137943e025da49ced2bd8abb6106a18cd2500675ce30bacde0633f55"
SIGNALS = (
    SignalSpec("Vehicle.Speed", nonnegative_float),
    SignalSpec("Vehicle.Acceleration.Longitudinal", finite_float),
    SignalSpec("Vehicle.Acceleration.Lateral", finite_float),
    SignalSpec("Vehicle.Acceleration.Vertical", finite_float),
    SignalSpec("Vehicle.Chassis.Accelerator.PedalPosition", uint8_percent),
    SignalSpec("Vehicle.Chassis.Brake.PedalPosition", uint8_percent),
    SignalSpec("Vehicle.Chassis.Axle.Row1.SteeringAngle", finite_float),
)
CAPABILITIES = ("INBOUND_BASE_DYNAMICS",)
ADVISORY_ENDPOINT_IDS: tuple[str, ...] = ()
