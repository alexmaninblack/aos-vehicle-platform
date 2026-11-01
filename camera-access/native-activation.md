<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vision native Camera Access contract

This packet implements the local native boundary selected by the operator on
2026-10-31. It does not change the retained Brake/Tire VM or Main's image selector.
The executable [native profile](../contracts/camera-access/native-profile.json)
is authoritative for fixed names, paths and protocol limits.

## Consumer access

Native Aos ResourceManager, not Camera Access, assigns `vision-camera-read`.
The native container runtime resolves its `aos-camera-read` group, adds that
supplementary GID, and projects only `/run/aos-camera-access/read` at
`/run/aosedge/platform/camera`, with bind/ro/nosuid/nodev/noexec. The maximum
allocation is one native service instance. Unix connect permission still
requires DAC and SELinux; a read-only bind does not make a socket read-only.

The pinned Aos OCI target was observed as `container_engine_t`, not an assumed
`container_t`: UID 5000, allocated reader GID, zero effective capabilities and
`NoNewPrivs=1`. The policy permits only read-mount metadata and connection to
the read socket; it adds no OEM or component-store permission. Resource/DAC,
actual UID and closed peer/protocol checks remain mandatory. This is not a
claim of distinct per-service SELinux/MCS isolation. Actual runtime labels
must be requalified if AosCore changes them.

Nonessential Camera-domain certificate/VM-sysctl directory searches remained
denied while pair delivery and revocation worked. Only those observed search
denials are dontaudited; no certificate or sysctl read access is granted.

The daemon reads Linux SO_PEERCRED. The consumer must be a non-root Aos
service UID, not the daemon UID. The read protocol accepts only `status` or
`pair`, with no caller-supplied service identity, camera selection, image input,
configuration, credentials or motion request. Each connection has one request
and an absolute two-second deadline, a maximum 4096-byte JSON header and at
most one two-JPEG response. JSON uses a four-byte network-order length prefix;
duplicate keys, nonfinite numbers and extra request fields fail closed.
Both original and world-associated times are preserved in frame metadata.

The trusted OEM side uses a separate 0600 socket below a 0700 directory, never
projected into a consumer. It accepts only root/the dedicated OEM UID, after
kernel peer observation. `hello` returns a process-generation identifier;
all other operations must bind it. A fresh authenticated OEM upstream session
must establish a new source epoch after restart. This local socket is not
Gateway authentication: the host-to-guest ingress adapter remains a separate
gate. There is no TCP listener or new credential database in this packet.

Stop/removal closes owned sockets, clears images and invalidates the component
generation. Resource revocation requires the native instance owner to stop
the consumer and reinstantiate without the resource. Editing a resource JSON
alone is not active-instance revocation. No new revocation daemon is introduced.

## Independent OEM activation

The existing systemd-slot component engine accepts two exact profiles. The
legacy VDP default keeps its original identity, unit, payload layout, store,
Safe Stop and recovery behavior. `camera-access-v1` requires the exact Camera
Access type, own A/B working directory, own unit and health adapter. A Camera
Access payload uses `camera-access`, `bin/camera-access`, `config/camera.json`;
it is never relabelled as VDP and cannot adopt a VDP slot.

The bootstrap supplies a dedicated unprivileged account, read group, fixed
launcher, disabled systemd unit and offline self-test unit. The native SM
owns install/activation, health, update, rollback and durable recovery. Source
availability is separate from process health: an active daemon with no selected
camera is healthy but explicitly unavailable. No GPU, inference, VDP, KUKSA
credential or Cloud producer key is included in this payload.

The Vision-specific image must select this bootstrap and resource instead of
the VDP component target and Brake/Tire input projection. It must keep the
existing authenticated physical Safe Stop/update contract. Missing credentials
or provisioned identity block activation; they are not grounds for a fake gate,
shared Unit identity or an unsafe overlay rebase.

## Verification and scope

Offline tests prove protocol bounds and separation, not native authorization.
Targeted Linux ARM64 compile/tests must cover the changed engine and retained
VDP cases before any package/image. Actual acceptance additionally requires
M4 native SM resource delivery, UID/GID/mount/SELinux evidence, first activation,
idempotent repeat, restart, unauthorized consumer and OEM-operation denial,
resource revocation, fresh audit review and unchanged retained Main state.
Manual crun, a root socket probe or a mocked runtime is never that acceptance.
Keep separate source, targeted-binary, bootstrap-image and live receipts.
