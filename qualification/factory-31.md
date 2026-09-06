<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .31: terminal factory-placeholder status

This release carries the live-proven runtime correction on Factory .30 source
`c3e08586d3c3d11b192041a9a7226765e098c63c`. The empty-slot factory VDP 0.0.0
marker is handled before transaction conflict checks, is retired with inactive
status when a real release takes over, and early StartInstance rejection emits
failed status rather than leaving the native launcher in activating.
Upstream CM waits/timeouts and Safe Stop policy are unchanged.

Three ARM64 regressions passed in 43 ms. The transient .30 proof binary SHA-256
was `a9da669ace53e21a798bf9a9d3fe8988936ae924c7ed9513dd97520a1ae194d7`.
On 2026-09-06, VDP 8 continued running while CARLA drove at 19 km/h and VDP 9
waited for Safe Stop. After operator Safe Stop, StartInstance-to-CM-none was
1.289835 seconds. VDP 9 reported READY, 23 paths; Cloud installed=9.0.0,
pending=null. No VM/SM restart or CM timeout occurred during that transition.

Demo Control now writes the role before provisioning and source selection no
longer restarts SM. This host-side correction belongs to the Solution repo;
the image retains .30's persistent public source inputs, role-based freshness
profile, native DNS configuration and VDP v1/v2/v3 schema. Nothing is copied
from provisioned overlays or /run. Test and Production start from fresh overlays
of the same immutable .31 image, each with a distinct identity.

The new post-read configuration changes only the image release identity and
retains offline/cache guards. Factory .31 build/package QA, digest and clean
E2E results belong in its external artifact manifest and the Solution release
checkpoint. Prior .30 live proof is not clean .31 qualification. v3 advisory
and per-Unit telemetry mTLS remain deferred; no new feature or authority is
introduced. Published images, bundles and compiler outputs are not Git content.
