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
fails closed. Provider package versions, functional VDP profiles and telemetry
contract versions are separate identities. The steering-angle unit token is
`degrees`; wheel angular speed uses degrees per second. Consumers must not
infer a conversion or functional profile from a package number.

## Availability and Freshness

Every profile signal is part of the required interface, but a live value can
be unavailable. Providers must never replace missing or stale measurements
with plausible zeroes. They mark the value unavailable after the profile's
freshness timeout. Consumers must distinguish unavailable data from a valid
zero measurement.

There is no global current-system freshness budget. The selected VDP
configuration, Brake 5-second input budget, FOTA Safe Stop profile and advisory
lease/future bounds are separate contracts. Use the exact configuration for
the consumer and path being evaluated, not a prototype's generic timeout.
See the [current protocol map](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/contracts/implementation-status.md).

## Deprecation

A signal scheduled for removal is first marked deprecated in a minor contract
release. It remains available through at least the next minor release. Removal
requires a major version and a qualified integration baseline with compatible
provider and consumer versions.

## KUKSA authorization compatibility seam

The pinned KUKSA 0.5.0 integration has two explicit downstream seams: decimal
digits in authorization scope paths, and VAL v1 source-time preservation. The
timestamp patch returns `source_ts` when supplied, otherwise
retains the upstream receipt-time fallback. It changes none of the 16 value
types, `NotAvailable`, value-only conversions, authorization or VSS schemas.
The recipe gates all six timestamp regressions and 17 scope tests before
packaging. The selected Factory image contains the correction; the
[current baseline](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/qualification/current-baseline.md)
records its scoped M1 API/UI results and remaining limits. This is Factory
integration, not a VDP-only FOTA update. The focused timestamp/scope regressions
do not establish that the complete upstream test suite passes.

The removable helper implements protocol `aos-kuksa-auth-compat/v1` as an
independent migration seam. Compatible native AosCore replacement behavior
must preserve strict one-frame request/response schemas, fixed resource
`kuksa`, exact `r -> read` and `rw -> actuate` mapping, complete rejection of
unsupported authority, the pinned RS256 claims/timing profile and all negative
isolation cases. A released native implementation must be requalified before
the package is removed; protocol compatibility alone does not authorize that
migration.

The temporary deployable also contains a separate networkless Provider
preparer, but this is not a protocol extension. It accepts no caller input and
creates only the fixed `aos-vdp` seven-day token with the frozen 27-entry
scope. The Service daemon and Provider process share neither API nor runtime
state. Both temporary paths are removed together only after native AosCore has
qualified replacements.
