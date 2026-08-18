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
The Vehicle Data Platform Component owns an Aos–KUKSA Credential Broker and a
versioned OEM access policy under `authorization/aos-kuksa/`; neither is
implemented in the current baseline.

A SOTA service declares its requested KUKSA paths and modes in Aos metadata.
Service Manager registers them and injects a per-instance `AOS_SECRET`. The
broker calls Aos IAM `GetPermissions` for the `kuksa` functional server,
compares the complete requested set with the OEM policy for that service
identity, fails closed on any excess, and otherwise issues a short-lived,
path-scoped JWT. KUKSA trusts only the broker's public verifier. The provider
uses a separate platform credential for its accepted `provide`/`create` paths.

Existing manually issued, path-scoped tokens remain temporary qualification
fixtures only. Token issuance, signing material, `AOS_SECRET`, and private keys
must never be committed or placed in payloads, command lines, or logs.

## Current Status

Repository separation and AOS-2 are complete. Provider `0.2.0` is signed and
locally verified but not published. The production runtime and demo store are
integrated into the unsigned local rootfs `6.1.1-maninblack.11` candidate.
The validation Unit remains on `6.1.1-maninblack.2`; no `.11` Cloud or Unit
mutation has occurred. The Credential Broker and OEM access policy remain
target work inside the Vehicle Data Platform Component.
