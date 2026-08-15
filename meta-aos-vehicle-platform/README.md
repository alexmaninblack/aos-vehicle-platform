<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform Yocto Layer

This layer contains the OEM integration delta for the R6.1 vehicle-data
provider component runtime. It is applied after the unchanged AosVM 6.1.0
`qemuarm64` Main Node baseline has built and booted successfully. Boot remains
at `6.1.0`; the integration manifest assigns every immutable rootfs candidate.

The layer now contains the accepted Service Manager component runtime, atomic
A/B prepare/apply/revert/recovery implementation, guarded provider archive
boundary, fixed launcher and health profile, and SELinux policy. R6.1-6.5a
adds a demo-only storage backend: a fully allocated 512 MiB ext4 image inside
the encrypted Aos workdirs volume is mounted at the unchanged component root
with the dedicated `vehicle_data_provider_store_t` context. Preparation and
activation fail closed on an unexpected mount, identity, filesystem, size,
allocation, label, UUID, capacity, or SELinux state.

The provider payload runs as the dedicated non-login `aos-vdp` account. A
fixed native launcher is the only command allowed to bypass the unit's
configured user: it enters `vehicle_data_provider_t` with only `CAP_SETUID`
and `CAP_SETGID`, enables `no_new_privs`, drops all real/effective/saved user
and group identities, and refuses to execute the payload unless its effective,
permitted, and inheritable capability sets are empty. This ordering is needed
because the AosVM SELinux baseline suppresses the executable-label transition
after systemd applies `DynamicUser` or `NoNewPrivileges` itself.

The nested filesystem is an explicitly bounded demonstration backend. It does
not decide the production vehicle storage architecture; a dedicated logical
volume, controlled workdirs migration, or equivalent OEM platform storage
boundary still requires a separate architecture decision. No signing or Cloud
operation is implemented by this layer.
