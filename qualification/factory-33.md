<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .33 — persistent CM idle status recovery

Status: built on 13 September 2026; clean Test E2E not yet performed.

Build source: `f7922b02b15f6cf816f181e1bf97572b61859aea`. Image size:
6,997,147,648 bytes; SHA-256:
`a302b2f2e2f238b361682ab8a529ec036ff260e00b2fb9a4d21db325d8d45761`.
Offline compile, five native Factory tests, manager package QA, final CM
60-second interval and service-input package checks, filesystem/image QA,
disk assembly and host transfer passed. Builder stopped cleanly.

Live qualification is paused before any Unit mutation: execution approval
requires explicit retirement authority for the preserved isolated .31 Test
comparison, which shares Test Vehicles. Canonical .32, comparison .31 and
Production are unchanged. The detailed resume record is in the Solution
repository, `docs/qualification/factory-33-e2e-2026-09-13.md`.

Authorized on 13 September 2026. Preserve Production and the immutable .32
baseline until qualification completes. All live/build actions use Demo Control.

## Image changes

- Preserve all .32 native SM teardown, replacement/preparation recovery,
  CM snapshot reconciliation, Factory DNS/role and VDP Safe Stop behavior.
- Integrate the two exact CM patches proved on .32 on 13 September: the
  existing idle update worker sends a full Unit status every 60 seconds when
  connected, without a CM restart or reconnect. Code default remains disabled;
  the final Factory CM configuration enables `idleFullStatusInterval: 60s`.
- Preserve native packaged public-input resources and cold/verify SM hooks.
  No transient binaries/configuration, live identity, tokens or VM state enter
  the image. No Cloud changes and no service permission bypass.

The transient proof passed 11 updater and two configuration tests. A delayed
Cloud disconnect falsely set .32 Offline; the same CM process and WebSocket
restored Online 10.247 seconds later with its periodic full status. This is
client recovery, not a fix for Cloud stale-event ordering.

## Qualification order

1. Compile/package the proven changes offline, verify final CM configuration
   and unchanged service hooks, assemble/freeze once with transfer SHA.
2. Retire only current Test through Demo Control, retaining the two service
   Subjects without Unit recipients. Create fresh Test from immutable .33.
3. Publish the next allocated VDP V1 before provisioning; start, initialize
   DNS/role, provision into Test Vehicles, connect CARLA and confirm Online.
4. Install V1 only at Safe Stop. Prepare public inputs after committed VDP
   and running process agree, then bind/assign the retained service Subjects.
   Do not attach services before inputs exist or repair first launch by
   restarting SM. Native resources are already packaged in the image.
5. Prove VDP V1 -> V2 -> V3 with fresh monotonic releases, moving/Safe Stop
   gates, committed process/version and the expected telemetry capabilities.
6. Publish and replace Brake/Tire releases through SP and their separate
   Subjects; verify native instances, Cloud versions and isolated backends.
7. Exercise connectivity off/on, backend outage/retry, VM restart and
   stop/start with retained assignments. Require persistent CM interval and
   automatic input/container recovery without transient manager overrides.
8. Reconcile scoped logs, restarts and final Cloud state; report each result,
   preserving .32 and comparison evidence until .33 is accepted.

Services remain in explicit synthetic-data mode without `permissions`, as
reconfirmed by the user. Real KUKSA access/advisory is blocked by the platform
defect and is not qualified by mock ingestion. Numeric releases are allocated
by Demo Control, never reset or chosen by the operator.
