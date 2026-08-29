<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vehicle Telemetry Contract Compatibility

## Versioning

The contract uses semantic versioning independently from repository releases.

- Patch changes clarify metadata without changing accepted data.
- Minor changes add backward-compatible optional signals or capabilities.
- Major changes remove or rename signals, change type or unit, narrow a valid
  range, change timing guarantees, or require new permissions.

Consumers declare a compatible contract range. An integration baseline pins
one exact contract file and its SHA-256 digest.

The implemented VDP source family follows the accepted additive component
graph rather than treating these as runtime-selectable modes:

- `1.0.0` exposes exactly seven base-dynamics paths;
- `2.0.0` is a strict v1 superset with four wheel linear-speed and four wheel
  angular-speed paths, with angular speed in degrees per second; and
- `3.0.0` is a strict v2 superset with eight wheel-slip paths and the two typed
  Brake/Tire advisory request/status flows.

Each release has a distinct capability-manifest digest. An unknown version,
changed manifest, contract-digest mismatch, missing path or missing capability
fails closed. The existing Provider `0.2.0` remains historical evidence and is
not relabelled as VDP v1.

Draft 0.1.1 is a metadata-only patch: both pinned VSS trees use the unit token
`degrees` for `Vehicle.Chassis.Axle.Row1.SteeringAngle`, while draft 0.1.0 used
the non-standard singular spelling. The underlying value remains degrees and
no provider or consumer conversion changes.

## Availability and Freshness

Every profile signal is part of the required interface, but a live value can
be unavailable. Providers must never replace missing or stale measurements
with plausible zeroes. They mark the value unavailable after the profile's
freshness timeout. Consumers must distinguish unavailable data from a valid
zero measurement.

The draft profile expects 30 Hz updates, accepts providers operating at 20 Hz
or faster, and uses a 250 ms freshness timeout. This allows several missed
frames before a value becomes stale while still exposing a broken telemetry
path promptly in a demonstration.

## Deprecation

A signal scheduled for removal is first marked deprecated in a minor contract
release. It remains available through at least the next minor release. Removal
requires a major version and a qualified integration baseline with compatible
provider and consumer versions.

## KUKSA authorization compatibility seam

The removable helper implements protocol `aos-kuksa-auth-compat/v1` as an
independent migration seam. Compatible native AosCore replacement behavior
must preserve strict one-frame request/response schemas, fixed resource
`kuksa`, exact `r -> read` and `rw -> actuate` mapping, complete rejection of
unsupported authority, the pinned RS256 claims/timing profile and all negative
isolation cases. A released native implementation must be requalified before
the package is removed; protocol compatibility alone does not authorize that
migration.
