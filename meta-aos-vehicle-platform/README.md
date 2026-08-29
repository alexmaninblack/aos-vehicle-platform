<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform Yocto Layer

This layer contains the OEM integration delta for the R6.1 vehicle-data
provider component runtime. It is applied after the unchanged AosVM 6.1.0
`qemuarm64` Main Node baseline has built and booted successfully. Boot remains
at `6.1.0`; the integration manifest assigns every immutable rootfs candidate.

The layer contains the accepted Service Manager component runtime, atomic
A/B prepare/apply/revert/recovery implementation, guarded provider archive
boundary, fixed launcher and health profile, and SELinux policy. R6.1-6.5a
adds a demo-only storage backend: a fully allocated 512 MiB ext4 image inside
the encrypted Aos workdirs volume is mounted at the unchanged component root
with the dedicated `vehicle_data_provider_store_t` context. Preparation and
activation fail closed on an unexpected mount, identity, filesystem, size,
allocation, label, UUID, capacity, or SELinux state.

The provider payload and its fixed native launcher run as the dedicated
non-login `aos-vdp` account established by systemd. The unit supplies an empty
capability bounding set. After entering `vehicle_data_provider_t`, the
launcher verifies the fixed UID, GID, supplementary-group state, and empty
effective, permitted, and inheritable capability sets; enables
`no_new_privs`; and only then executes the payload. The launcher retains no
identity-changing capability.

The nested filesystem is an explicitly bounded demonstration backend. It does
not decide the production vehicle storage architecture; a dedicated logical
volume, controlled workdirs migration, or equivalent OEM platform storage
boundary still requires a separate architecture decision. No signing or Cloud
operation is implemented by this layer.

The accepted local output is rootfs candidate `.11`, built from platform
revision `a12c0aa7f8a680b35407776b12bcc025970abc73`. It closes the runtime
dependency chain required by provider `0.2.0`. Candidate `.11` is unsigned and
has not been uploaded, assigned, or installed; the validation Unit therefore
remains on `.2` and the demo Unit on `.1`.

The same Yocto build also produced the complete unprovisioned raw VM disk used
for disposable qualification. In the target manufacturing flow, an accepted
version of that complete image supplies this runtime before provisioning. The
rootfs FOTA candidate remains a separate retrofit/platform-maintenance
artifact and is not required to introduce the initial runtime into a newly
manufactured Unit.

The successor Factory source composition now configures the shared
Aos IAM permission handler with `enablePermissionsHandler: true` independently
of provisioning and include the removable `aos-kuksa-auth-compat` package and
its non-secret named-resource/signer-verifier preparation seams. The same
temporary package now contains a third, strictly separate networkless one-shot
which prepares the fixed OEM Provider JWT; its socket/API remains Service-only.
`aos-kuksa-factory-integration` supplies finite provisioning/reboot/deprovision
ordering, token initialization and volatile cleanup. The fixed Provider token
persists ordinary reboot under `/var/lib/aos-kuksa-provider`, while VDP gets
only a private systemd credential snapshot and no source-store access. The
image recipe selects both packages, but these source bytes have not yet passed package, image or VM
qualification and are not part of current `.11` evidence. The helper remains
outside the VDP component payload, and the image must contain no provisioned
identity, private key, shared verifier, `AOS_SECRET`, Service JWT or static
Provider/Service credential.
