<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CARLA VISS-to-KUKSA Provider

This directory contains the development-only provider implemented for AOS-2.
It runs inside AosVM, subscribes to the approved CARLA VISS 3.1 projection over
verified TLS, validates and maps the selected VSS 6.0-compatible values, and
publishes one `kuksa.val.v1` batch into the VSS 5.0 Databroker.

The historical 0.1.1 profile used a 250 ms freshness timeout. Current packages
select the immutable VDP V1/V2/V3 capability profile described below and its
configured freshness bounds. Missing, malformed or expired values become
KUKSA `NotAvailable`; zero is never a connectivity/freshness substitute. Do not
confuse provider timing with Brake's 5-second input budget, FOTA's selected
Safe Stop profile or the advisory lease.

The runtime deliberately uses the full KUKSA `Set` API with `try_v2=False`.
KUKSA Python SDK 0.5.0's simplified multi-value helper can repeat its v1
fallback once per element when the v2 API is unavailable in Databroker 0.5.0.
One explicit v1 batch avoids duplicate publication and unnecessary load.

Source lives under `src/carla_viss_kuksa_provider`. Dependency-free contract
and stale-state tests run with the repository's normal unittest gate. The
independently managed FOTA component recipe and exact ARM64 wheel lock live
under `packaging/fota`.

Production platform profiles must be able to exclude this component
completely. The provider conforms to the published vehicle telemetry profile
and exposes only the selected profile, including V3's approved wheel-slip
overlay signals; no simulator oracle is exposed.

## Immutable VDP source profiles

The `releases` directory defines three build-selected profiles. VDP `1.0.0`
contains exactly the seven base-dynamics paths. VDP `2.0.0` adds the four
standard wheel linear-speed paths and four standard wheel angular-speed paths
in degrees per second. VDP `3.0.0` adds the eight accepted wheel-slip paths and
the schema-bound Brake Health and Tire Health advisory policy.

The historical deterministic source prebuild copied one release module and
omitted later modules. Normal Demo Control preparation now uses the current
common runtime with one immutable selected release profile. V1/V2 never enable
the typed-advisory capability; no operator runtime switch changes the profile.
Each payload configuration is bound to its capability-manifest digest.

Family frames must be complete, contract-valid and source-time monotonic before
data readiness recovers. Missing, malformed, stale or disconnected data is
published as KUKSA `NotAvailable`; process health remains separate. Selected-
Unit VISS client material and the fixed KUKSA Provider token are read only from
protected external/systemd credential paths. Unit identity and credentials do
not enter a release profile.

Time-based VISS subscriptions can repeat the latest snapshot between source
ticks. An identical complete snapshot with the same source timestamp is ignored:
it is not republished and does not renew freshness or recover stale data. The
normal stale timeout is checked even on a continuously busy duplicate stream.
Changed values at the same timestamp and backward timestamps remain invalid.

VDP v3 accepts only the two frozen canonical JSON Request schemas from their
exact service owners. It enforces path, value, freshness, lease, replay, rate
and correlation bounds before the narrow VISS Set. Only a correlated factual
Gateway Status is published back to KUKSA; VISS or KUKSA transport success is
never reported as application success. The Gateway remains final authority.

Source tests do not prove deployment. Real ARM64 packaging, trusted Provider,
VISS and FOTA have scoped integration evidence through Factory39; see the
[current baseline](../../../aosedge-sdv-demo/docs/qualification/current-baseline.md).
Full fresh .39 progression and the remaining negative matrix are separate gates.
