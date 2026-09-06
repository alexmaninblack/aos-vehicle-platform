<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .29: VDP telemetry schema

## Post-release Stop/Start correction — 2026-09-06

Operator-approved completion barrier: StopInstance returns success only after
actual stop, without holding the runtime mutex while waiting. stopped.json
retains the inactive predecessor's A/B slot for rollback across runtime restart.
StartInstance remains asynchronous; no upstream launcher modification.

Native proof: 7/7 targeted tests pass in 286 ms. An initial double-join race
during cancellation was corrected before this passing run. Only SM was built
offline; Builder stopped. Executable SHA-256:
0ea27410730ca188fb40641a5a110e0396436807ff8380f44a74cd5ada63d9b8.

Live Test .29: StopInstance at 03:48:35.001468 UTC, StartInstance at
03:48:35.747153 UTC, candidate committed around 03:48:36.825 UTC. VDP 7.0.0
(v1 content), slot b, PID 5063, 7 paths, READY/LIVE/NONE, NRestarts=0.
Cloud installed=7.0.0, pending=null; Production unchanged. No ten-minute retry,
forced send or manual VDP start. The lost SM-apply response was reconciled
by read-only SHA/service observation, followed by a confirmed no-op command.

This checkpoint is input for Factory .30, not a mutation of published .29.
Persistent source/profile integration and clean .30 E2E remain unqualified.
Temporary Test SM remains at /run/democtl-sm-stop-start.

## Original immutable .29 build

Base is exact Factory .28 source e0a0d101a58a9aaec5123ff9eda4e0459f5db62d.
The sole functional change is build-time composition of the public VSS schema:
eight existing VDP v3 ChaosWheel leaves are added to the upstream VSS 5.0 tree.
The transform validates all v1/v2/v3 telemetry paths (7/15/23), rejects missing
or conflicting leaves and preserves every unrelated existing node.

The preceding Test-only transient proof used the unchanged VDP 3.0.0 bundle
and achieved active slot a, matching process configuration, READY/LIVE/NONE,
Cloud installed=3.0.0, SELinux Enforcing and no observed kernel AVC denials.
Effective schema SHA-256 was
357e5af4e1ee6fa881c6a0ddf55e87320bedc966dd4faf7c70e14e57ba0fa73d.
The Factory recipe produces this schema at package time. It does not copy a
provisioned VM, /run state, private material or a runtime bind mount.

No SM/CM code, certificate, ACL, SELinux policy, KUKSA executable or VDP payload
change is included. Three inherited .28 qualification/backport files receive
missing SPDX metadata required by the existing repository gate; their C++ patch
hunks are unchanged. Test and Production share one immutable raw manufacturing
image; each later deployment must use a fresh overlay and its own identity.
The existing .28 artifact and running qualification state are retained until
the successor passes. Current Production is outside the live mutation scope.

Source gates: six schema regression tests and 21 R6.1 layer tests pass, as does
the layer validator. Full quality, package/image QA and live .29 results are
recorded in the Solution qualification document and external artifact manifest.
The post-read factory-29.conf preserves offline cache use and changes only the
rootfs release identity to 6.1.1-maninblack.29.

Required live matrix: fresh .29 empty-slot boot; provisioning/Online; VDP v1,
v2 and v3 actual process plus complete-frame publication; Safe Stop; restart
and absence of temporary schema overrides. READY is provider-reported and is
not an independent KUKSA consumer read. Full v3 advisory and mTLS remain
deferred as explicitly agreed by the operator.

## Subsequent Test-only SM proof (not part of the Factory artifact)

On 2026-09-06 the operator authorized an explicit `demo-5s` Safe Stop freshness
profile for the local CARLA Test demonstration. The setting
`safeStopFreshnessProfile` defaults to `standard` (250 ms), accepts only
`standard` or `demo-5s`, and changes only source-age checks to 5000 ms in the
latter profile. All other evaluator gates and transport read timeouts stay
unchanged. Future timestamps are still rejected. This admits genuinely delayed
samples too and is not the unchanged Safe Stop profile 1.1.1 qualification.

The isolated source delta was compiled offline with the existing pinned SM
recipe: 1716 tasks, 1708 reused; 61 runtime-suite tests, 59 passed and the two
explicit real-provider qualification cases skipped. The exported ARM64 SM
SHA-256 is f0e8c3806c95befc880276f7ca1a05de82a9d866abe9bb665ba3ba868aaedde2.
The Builder was stopped after export. This delta is not in the immutable .29
image; live Test results and the accepted exception are recorded in the
Solution qualification and Platform FOTA Safe Stop contract documentation.
