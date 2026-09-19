<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .36 — CM connection and shared-storage corrections

Status: source/local gates passed; package/image and live qualification pending.
The operator authorized local storage proof first and a conditional successor
build on 19 September 2026. Preserve immutable .35 and the diagnostic Test.

This successor adds two bounded CM changes over .35:

- `0006-notify-outside-transport-lock.patch`: disconnect callbacks no longer
  hold the transport lock while acquiring Monitoring/Alerts locks. Isolated
  tests and two live external OFF/ON cycles passed on the retained Test.
- `0007-preserve-shared-instance-storage.patch`: retire obsolete instance
  version records without deleting shared storage while another full instance
  identity owner remains. Active/cached/disabled/scheduled collections are
  considered. Failed retirement stays visible; final-owner cleanup is retained.

The library pin, API, storage paths/schema, TTL, quotas, Cloud protocol,
permission capacity, service models and accepted .35 deltas are unchanged.
No new watchdog, storage backup/restore service or demo-specific exception.
SM and IAM sources are unchanged; validate their existing package inputs.
Do not bake deployed services, Subjects, credentials, models, queues or /run
overrides into Factory firmware. Operator Park/Resume remains removed.

Local native storage evidence: 43/43 tests pass on the pinned library with the
storage fix; unchanged library fails 17/43, including the storage-loss cases.
With the accepted library patch stack, 45/45 pass, ten repetitions (450 test
executions); ASan/UBSan also pass 45/45. Platform Python gates: 174/174.
These execute the native instance manager with stubbed image/storage interfaces;
they are not a live filesystem, 24-hour timer, Cloud or crash-atomicity proof.

Build gates: committed source, offline warm caches, targeted manager compilation,
45 native launcher/storage/reconciliation tests with the production toolchain,
five SM Factory-input tests, KAC/Provider tests, uniform 256-character permission
capacity, package QA, image QA, original six-partition assembly and transfer hash.
The build result must remain BUILT_NOT_LIVE_QUALIFIED until fresh qualification.

Live acceptance must include real service storage bytes and producers across
updates/CM restart, continued local analytics with external network OFF,
stopped backend ingress, reconnect/backlog delivery and clean Finish. Building
an image neither restores the damaged current Brake data nor completes P8.

Solution evidence: `docs/qualification/cm-shared-storage-fix-2026-09-19.md`.
