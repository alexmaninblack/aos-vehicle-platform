# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Immutable VDP 1.0.16 release profile."""

from ..bridge import SignalSpec, finite_float, nonnegative_float, uint8_percent


VERSION = "1.0.16"
MANIFEST_SHA256 = "c5e5b008b6a90782e192d6581d9cd39f88022815be2b53e97baccf2952a61bcf"
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
