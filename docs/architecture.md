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

## Prototype Pins

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

## Authorization Boundary

The Aos-to-KUKSA Authorization Adapter is planned as AOS-5. Its future home is
`authorization/aos-kuksa/`. It is not implemented in the R-2 scaffold. The
prototype contract records least-privilege `provide` and `read` scopes so the
future adapter can map Aos service identity to KUKSA permissions without
changing the data profile.

Until AOS-5 is implemented, any temporary test credentials are integration
fixtures outside this repository. They are not a production authorization
design and must never be committed.

## Current Status

R-2 publishes a reviewable draft contract and static gates only. Provider
behavior, KUKSA configuration, AosVM packaging, and Authorization Adapter
behavior remain intentionally unimplemented.
