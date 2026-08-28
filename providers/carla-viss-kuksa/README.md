<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CARLA VISS-to-KUKSA Provider

This directory contains the development-only provider implemented for AOS-2.
It runs inside AosVM, subscribes to the approved CARLA VISS 3.1 projection over
verified TLS, validates and maps the selected VSS 6.0-compatible values, and
publishes one `kuksa.val.v1` batch into the VSS 5.0 Databroker.

The provider publishes only the paths in vehicle telemetry profile 0.1.1. A
missing or invalid value becomes KUKSA `NotAvailable`. If no valid VISS event
arrives for 250 ms, all retained values become unavailable exactly once; zero
is never used as a connectivity or freshness substitute.

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
and does not expose CARLA-specific overlay signals to services.

## Immutable VDP source profiles

The `releases` directory defines three build-selected profiles. VDP `1.0.0`
contains exactly the seven base-dynamics paths. VDP `2.0.0` adds the four
standard wheel linear-speed paths and four standard wheel angular-speed paths
in degrees per second. VDP `3.0.0` adds the eight accepted wheel-slip paths and
the schema-bound Brake Health and Tire Health advisory policy.

The deterministic prebuild copies only one release module into a candidate's
source inputs. The v1 and v2 inputs do not contain the advisory module, and no
runtime option selects another release. Each payload configuration is bound to
the digest of its immutable capability manifest.

Family frames must be complete, contract-valid and source-time monotonic before
data readiness recovers. Missing, malformed, stale or disconnected data is
published as KUKSA `NotAvailable`; process health remains separate. Selected-
Unit VISS client material and the fixed KUKSA Provider token are read only from
protected external/systemd credential paths. Unit identity and credentials do
not enter a release profile.

VDP v3 accepts only the two frozen canonical JSON Request schemas from their
exact service owners. It enforces path, value, freshness, lease, replay, rate
and correlation bounds before the narrow VISS Set. Only a correlated factual
Gateway Status is published back to KUKSA; VISS or KUKSA transport success is
never reported as application success. The Gateway remains final authority.

This repository evidence is source-level only. Real ARM64 packaging, trusted
Provider/VISS integration and FOTA qualification remain separate gates.
