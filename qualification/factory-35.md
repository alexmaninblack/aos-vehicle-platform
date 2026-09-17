<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .35 — retained startup reconciliation

Status: build and complete staging Test qualification authorized on
17 September 2026. Not yet built or live-qualified. Preserve .34 until the
successor passes. Production is excluded.

The only native change over .34 is the proven CM launcher correction:
an unchanged Subject list must not erase a pending startup rebalance.
The stored-unscheduled native regression reports an already-running SM
instance and rejects a premature stop. Original code fails; corrected code
passes 19 launcher and service-reconciliation tests. A transient CM binary
on preserved .34 retained the native stores, SM and VDP. Presenter Continue
Resume completed with LIVE Manual telemetry and both advisories Monitoring.

Source patch: `0005-preserve-pending-startup-rebalance.patch`. No change to
SM, IAM, Cloud, permissions, Safe Stop authorization or model thresholds.
Retain .34's uniform 256-character permission capacity and all native KUKSA,
Provider, schema, service-input and advisory readiness behavior.

Build through `democtl image build 6.1.1-maninblack.35` from a committed source
revision, warm offline caches and the existing six-partition assembly.
Native launcher, Factory input, KUKSA/Provider, package QA and image QA are
gates before freezing the artifact. No credential, deployed release, Subject,
live database, transient /run file or generated binary belongs in Git/image
source. Verify the image digest at creation/transfer; preserve compact evidence.

Clean acceptance: UI create and stationary Manual connection; prepare/publish
before strict Provision; VDP V1/V2/V3 with component installation gated by Safe
Stop; Brake V1/V2/V3 and Tire V1 without a Safe Stop installation dependency;
real-data backend results and advisory/reset; network Offline/Online;
retained-identity Park/Resume with the packaged CM; final Finish/deprovision,
Cloud deletion and owned local cleanup. The host's identity-bound credential
projection recovery and exact-operation Resume continuation remain Demo
Control responsibilities. A build or recovered session is not a clean-run pass.

Execution evidence is maintained in the solution repository's
`docs/qualification/factory-35-e2e-2026-09-17.md`.
