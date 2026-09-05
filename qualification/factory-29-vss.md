<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .29: VDP telemetry schema

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
