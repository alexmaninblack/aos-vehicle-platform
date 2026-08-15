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
