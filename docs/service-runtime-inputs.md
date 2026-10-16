<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Service public inputs and native credential resources

The Factory integrates the resource declarations and cold-start hook used by
[ADR 0015](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/architecture/decisions/0015-use-native-aos-service-runtime-inputs.md).
The integration [input contract](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/architecture/demo-control-service-inputs.md)
owns the exact schema/sequence. This platform document owns resource placement
and boot ordering, not another current Factory selector.

## Public resource boundary

The [resource asset](../meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/resources-demo-services.cfg)
defines separate `brake-runtime-inputs` and `tire-runtime-inputs`. Build-time
composition merges these with existing native resources; nothing is copied
from a live VM. Each service mounts only its own stable
`/run/aos-demo-service-inputs/<team>` at `/run/aosedge/platform/service-inputs`
with `bind,ro,nosuid,nodev,noexec`. It cannot mount the parent or peer resource.

Public `metadata.json` has five fields and schemaVersion 2. It and `kuksa-ca.pem`
are root-owned 0444 in a root-owned 0755 stable directory. Only the public
`/var/lib/aos-kuksa-tls/server.pem` is projected. Native instance identity and
package release are separate inputs; public metadata is not an exact active
functional-profile attestation.

## Private credentials

Services separately request `kuksa` and `kuksa-auth-client`. The existing socket
bind/group are unchanged. Each container has a 64-KiB token tmpfs with
`rw,nosuid,nodev,noexec`, root mode 1777. Bootstrap creates an unpredictable
private 0700 session and regular 0400 token owned by its actual UID/GID.
Analytics receives only its path, never `AOS_SECRET`. KAC/native IAM own issue,
renewal and scope; no fixed UID, privileged chown or token-owner SM patch.
The separate systemd-slot runtime and unrelated native corrections remain.

## Startup and refresh

The selected native resource manager reads configuration at initialization,
not hot reload, and does not create/chown bind sources. Directories must exist
before instance construction. Configuration activation is an explicit existing
Demo Control action, not binary replacement or implicit status repair.

Project inputs before assignment, refresh only after committed VDP/slot/process
agreement, and reconstruct volatile `/run` inputs before retained assignments
launch after reboot. Packaged `40-aos-demo-service-inputs.conf` uses SM
`ExecStartPre` for cold projection and `ExecStartPost` for bounded verification,
with the same projector source as Demo Control. Empty source directories exist
even without compatible VDP data; unavailable metadata is withheld, not invented.
Warm refresh is explicit `democtl service runtime-prepare test`; no autonomous
warm-refresh daemon or persisted public-metadata cache is added.

## Verification boundary

Prove native non-root execution, exact private mounts, peer isolation, public
read-only access, KAC/TLS/subscription renewal and scoped SELinux behavior under
the actual service identity. Source tests alone establish none of those live
facts. No rootfs remount, widened policy, TOFU or Production-role change.
The [current integration baseline](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/qualification/current-baseline.md)
owns image-specific installed/ignition/offline proof and remaining cold-offline
or negative cases. Earlier source increments and Factory numbers remain in Git,
not as another installation checklist.
