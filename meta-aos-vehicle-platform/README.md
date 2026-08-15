<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform Yocto Layer

This layer contains the OEM integration delta for the R6.1 vehicle-data
provider component runtime. It is applied after the unchanged AosVM 6.1.0
`qemuarm64` Main Node baseline has built and booted successfully. Boot remains
at `6.1.0`; the current local target is rootfs `6.1.1-maninblack.3`.

The layer now contains the accepted Service Manager component runtime, atomic
A/B prepare/apply/revert/recovery implementation, guarded provider archive
boundary, fixed launcher and health profile, and SELinux policy. R6.1-6.5a
adds a demo-only storage backend: a fully allocated 512 MiB ext4 image inside
the encrypted Aos workdirs volume is mounted at the unchanged component root
with the dedicated `vehicle_data_provider_store_t` context. Preparation and
activation fail closed on an unexpected mount, identity, filesystem, size,
allocation, label, UUID, capacity, or SELinux state.

The nested filesystem is an explicitly bounded demonstration backend. It does
not decide the production vehicle storage architecture; a dedicated logical
volume, controlled workdirs migration, or equivalent OEM platform storage
boundary still requires a separate architecture decision. No signing or Cloud
operation is implemented by this layer.
