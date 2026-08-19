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

The contract contains only standard paths common to the selected VSS 5.0 and
VSS 6.0 inputs. CARLA-specific overlay signals are deliberately outside the
service interface.

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
The Vehicle Data Platform Component owns a thin Aos–KUKSA Credential Broker,
KUKSA trust configuration and provider platform-credential integration under
`authorization/aos-kuksa/`; these are not implemented in the current baseline.

A SOTA service declares its requested KUKSA paths and modes in Aos metadata.
Service Manager registers them and injects a per-instance `AOS_SECRET`. The
broker calls Aos IAM `GetPermissions` for the `kuksa` functional server and
maps only the currently registered paths/modes that are valid in the installed
VDP contract into a short-lived, path-scoped JWT. Invalid/stale secrets,
unknown modes, malformed paths and contract excess fail closed. The broker
stores neither service identity nor a duplicate per-service policy database.
KUKSA trusts only the broker's public verifier. The provider uses a separate
short-lived platform credential for its accepted `provide`/`create` paths;
the exact FOTA-component identity binding remains a design gate.

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

Repository separation and AOS-2 are complete. Provider `0.2.0` is signed and
locally verified but not published. The production runtime and demo store are
integrated into the unsigned local rootfs `6.1.1-maninblack.11` candidate.
The validation Unit remains on `6.1.1-maninblack.2`; no `.11` Cloud or Unit
mutation has occurred. The thin Credential Broker, protected signing
integration and provider platform-identity binding remain target work inside
the Vehicle Data Platform Component. The stock Aos IAM permission handler also
requires enablement and qualification in the accepted Factory Image.
