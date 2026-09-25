<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Architecture and Ownership Boundary

## Purpose

This repository owns the vehicle-computer side of the KUKSA vehicle-data
boundary. It publishes a stable contract to independently deployable Aos
services and contains platform components that follow an OEM-controlled
platform/FOTA qualification lifecycle.

```text
DEVELOPMENT HOST                       AOS VEHICLE COMPUTER

CARLA -> VISS 3.1 -> CARLA provider -> KUKSA Databroker -> Aos service
                     [this repository]  [platform]         [separate repository]
```

The CARLA VISS-to-KUKSA provider is a development-only simulation adapter. A
production vehicle replaces it with one or more platform providers backed by
CAN, SOME/IP, DDS, or OEM-specific interfaces. Both kinds of provider publish
the same versioned KUKSA/VSS contract.

The telemetry service is not part of this repository. It may use only the
published contract and KUKSA API; it must not import the provider, connect to
CARLA/VISS, or depend on VM launcher and provisioning code.

For the accepted demo architecture, Brake Health and Tire Health are
QM-domain maintenance/inspection applications. Aos IAM/KUKSA permissions and
the outbound VDP allowlist provide least privilege and defense in depth; they
do not allocate a safety goal or vehicle-motion authority. The external
Vehicle Gateway remains the final authoritative boundary for the QM-origin
channel and independently denies arbitrary VSS, motion and safety-critical
operations.

## Accepted Prototype Pins

The initial contract is qualified against these inputs:

| Input | Pinned prototype value |
| --- | --- |
| AosVM Databroker VSS tree | VSS 5.0 |
| CARLA-side VISS projection | VSS 6.0-compatible standard paths |
| KUKSA Databroker | 0.5.0 |
| KUKSA API | `kuksa.val.v1` |
| Service CPU architecture | `arm64` |

The early 0.1.1 contract used standard paths common to VSS 5.0 and VSS 6.0.
The implemented VDP V3 profile additionally exposes the eight accepted CARLA
wheel-slip overlay signals for this demo; it does not expose hidden wear/friction
truth. See [contract compatibility](contract-compatibility.md).

## Runtime and Storage Boundary

The provider is an independently signed platform component managed by the Aos
Service Manager `systemd-slot-component` runtime. The rootfs owns the runtime,
systemd profile, fixed `aos-vdp` identity, health checks, KUKSA integration,
SELinux policy, and persistent-store mount. The provider component owns only
its immutable executable payload and runtime libraries.

The demonstration AosVM uses a fully allocated 512 MiB ext4 image inside the
existing encrypted workdirs volume and mounts it at the stable component root
with `vehicle_data_provider_store_t`. This preserves the required isolation
without relabelling AosCore workdirs. It is a demo backend, not the selected
production vehicle storage architecture.

## Authorization Boundary

The target architecture keeps upstream Eclipse KUKSA Databroker unchanged.
The separately packaged removable current-release KUKSA Authorization
Compatibility helper belongs to the Factory/System layer under
`authorization/aos-kuksa-compat/`; it is outside the Vehicle Data Platform
FOTA payload. The current branch implements it as a separately removable
source/Yocto package containing one unprivileged Service helper, one short
root-owned verifier-preparation executable and one separately confined,
networkless Provider-credential one-shot. Provider issuance is not reachable
through the Service socket/API. A second Factory-integration package owns only
the dedicated token initializer, volatile cleanup and finite systemd drop-ins.
Factory39 selects these packages. Build, native permissions, retained boot and
externalOFF operation have scoped integration receipts; the complete negative
and qualification matrix remains separate.

A SOTA service declares its requested KUKSA paths and modes in Aos metadata.
Service Manager registers them and injects a per-instance `AOS_SECRET`. The
helper calls Aos IAM `GetPermissions` for the fixed `kuksa` resource on every
issue/renewal and maps only the currently registered exact paths and supported
modes into a short-lived, path-scoped JWT. IAM `r` maps to KUKSA `read`; IAM
`rw` maps to KUKSA `actuate`; IAM `w`, unknown modes, wildcards, malformed
paths, partial trimming, `provide` and `create` reject the complete issuance.
The helper stores neither Service identity nor a duplicate permission/policy
database. KUKSA trusts only the prepared per-Unit public verifier.

The Provider is separate trusted OEM Platform integration with fixed
`aos-vdp` identity. It receives no authority from the Service helper. A fixed
seven-day, exact-path RS256 JWT is prepared from the same per-Unit PKCS#11 trust
root by the separate one-shot process and is consumed only through systemd
credentials. Its persistent source is isolated in the root-owned mode-`0700`
`/var/lib/aos-kuksa-provider` state directory, outside the VDP component store;
VDP receives only systemd's private credential snapshot. There is no renewal
daemon or exact in-session revocation claim; expiry is enforced at the next
KUKSA authentication/reconnect.

VDP v1-v3 capability profiles are immutable build selections. The normal Demo
Control preparation uses the current common runtime with one selected profile;
V1/V2 do not activate typed advisory even when common code is present. Historical
profile-only source prebuilds are not the current product preparation path.
The outbound v3 implementation accepts only the two contract-owned service,
path and canonical schema combinations, while the Gateway remains the final
application authority. No VDP application store, log database, tenant quota or
runtime authorization service is introduced.

Existing manually issued, path-scoped tokens remain temporary qualification
fixtures only. The target broker signing key is established per Unit and
protected through the Aos IAM/certificate-module and PKCS#11 integration.
Token issuance, signing material, `AOS_SECRET`, and private keys must never be
committed, baked into a Factory Image, or placed in payloads, command lines, or
logs.

OEM approval remains a lifecycle decision outside this repository. Before the
final explicit OEM authorization, the release workflow presents the exact
artifact and metadata digests, requested permissions, target, validation
evidence and owning-team acceptance. Passing tests never auto-approve, and
AosCloud remains the authoritative lifecycle record.

## Current Status

The source return point is demo-v1.1 / Factory39, not the historical .11
prototype. Native IAM permissions, KAC, per-Unit trust, selected-peer mTLS,
common-runtime VDP FOTA and typed V3 advisory are implemented. IAM's
`enablePermissionsHandler: true` is Factory configuration, independent of
provisioning.

See the [cross-repository implementation matrix](../../aosedge-sdv-demo/docs/architecture/current-implementation.md)
and [Factory39 evidence](../../aosedge-sdv-demo/docs/qualification/factory-39-build-2026-09-24.md).
Scoped ignition/offline receipts do not establish complete serial E2E, model
calibration, every security negative or a stock-upstream AosCore build.
Temporary VDP core capture is removed; historical VDP109 SIGSEGV cause remains
unresolved.
