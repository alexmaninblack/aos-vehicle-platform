<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform Yocto layer

This layer produces the clean Linux/AosEdge base (**Factory image**) for the
ARM64 virtual controller. It contains platform integration, not a provisioned
vehicle identity or preinstalled Brake/Tire applications. VDP profiles are
delivered later through OEM FOTA; services use their independent SOTA lifecycle.

Use the integration [current baseline](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/qualification/current-baseline.md)
and its image/source authorities for exact inputs and qualified media. Old
rootfs/Factory numbers are not build selectors. The normal
[developer route](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/getting-started/reproduce-demo.md)
reuses the prepared image; specialist image builds use the separate Linux Builder.

## Component runtime and storage

The layer owns Service Manager's `systemd-slot-component` runtime, atomic
A/B prepare/apply/revert/recovery, archive validation, fixed launcher, health
profile and SELinux policy. The demonstration storage backend is a fully
allocated 512 MiB ext4 image inside encrypted Aos workdirs, mounted at the
unchanged component root with `vehicle_data_provider_store_t`.

Preparation and activation reject an unexpected mount, identity, filesystem,
size, allocation, label, UUID or capacity and require SELinux Enforcing.
The nested filesystem is a bounded demonstration backend, not a decision
about production vehicle storage architecture.

The launcher runs as the fixed non-login `aos-vdp` account. It verifies UID,
GID, supplementary groups and empty effective/permitted/inheritable
capabilities, enables `no_new_privs`, and executes only the selected payload.
The systemd unit supplies no identity-changing capability.

## Authorization and boot integration

Factory configures native IAM's `enablePermissionsHandler: true` independently
of provisioning. The removable `aos-kuksa-auth-compat` package contains distinct
Service authorization, public verifier preparation and networkless Provider
credential preparation boundaries. It is outside VDP and both SOTA payloads.

`aos-kuksa-factory-integration` owns finite provisioning/reboot/deprovision
ordering, token initialization and volatile cleanup. The fixed Provider token
persists ordinary reboot under `/var/lib/aos-kuksa-provider`; VDP receives
only systemd's private credential snapshot, not source-store access. The
Service helper's socket/API cannot issue Provider authority.

The image recipe also reserves KUKSA's explicit TCP port 55555 from automatic
port allocation. It composes existing effective sysctl reservations and orders
NFS mountd and KUKSA after the normal systemd sysctl pass. Ambiguous, masked or
later overriding policy stops image creation; no runtime repair daemon or
recurring NFS restart is introduced. A source check is not cold-boot evidence
for a newly assembled image.

KUKSA integration retains the reviewed scope-path and VAL v1 source-timestamp
patches. See [compatibility](../docs/contract-compatibility.md) and
[architecture](../docs/architecture.md) for exact ownership and trust rules.

No provisioned identity, private key, shared verifier, `AOS_SECRET`, Service
JWT or static Provider credential belongs in a reusable Factory image.
Signing and Cloud operations are integration-owned, not implemented by this layer.

## Image lifecycle and proof

A complete unprovisioned image establishes the platform before controller
creation/provisioning. A rootfs FOTA envelope is a separate retrofit or later
platform-maintenance artifact, not the independently delivered VDP component.
Never replace a backing image beneath a provisioned VM.

Current scoped M1 API/UI, serial updates, ignition and offline results are
recorded by the integration baseline. They do not establish every security
negative, nonempty-queue power loss, host sleep/wake or production storage
architecture. Source checks and build success are not live qualification.
