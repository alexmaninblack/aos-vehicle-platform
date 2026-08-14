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
