# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Immutable VDP 1.0.0 release profile."""

from ..bridge import SignalSpec, finite_float, nonnegative_float, uint8_percent


VERSION = "1.0.0"
MANIFEST_SHA256 = "fcca3270d6467827d34ad28fb99c7e71a7c46ebf4c0943de153fb9ec1ecb1a9b"
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
