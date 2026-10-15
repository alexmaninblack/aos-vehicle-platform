<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform Yocto Layer

Current controller-image selection, source provenance and exact qualified
preview follow the [integration baseline](../../aosedge-sdv-demo/docs/qualification/current-baseline.md)
and its Factory checkpoint. The layer produces the clean Linux/AosEdge base
for the ARM64 virtual controller, separate from later VDP and service delivery.
The [demo-v1.1 return point](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/84056efdf73c518d14929d66a772673212e8a2d9/docs/qualification/demo-v1.1-return-point.md)
is historical, not today's selected image.

The R6.1/.11 and original AosVM 6.1.0 descriptions below retain the substrate's
design history; they are not a current build selector, live inventory or an
instruction to recreate deleted images. Exact immutable image identity belongs
to the selected integration manifest, not an old boot-version example.

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

The historical early local output was rootfs candidate `.11`, built from platform
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

The current Factory composition configures the shared
Aos IAM permission handler with `enablePermissionsHandler: true` independently
of provisioning and includes the removable `aos-kuksa-auth-compat` package and
its non-secret named-resource/signer-verifier preparation seams. The same
temporary package now contains a third, strictly separate networkless one-shot
which prepares the fixed OEM Provider JWT; its socket/API remains Service-only.
`aos-kuksa-factory-integration` supplies finite provisioning/reboot/deprovision
ordering, token initialization and volatile cleanup. The fixed Provider token
persists ordinary reboot under `/var/lib/aos-kuksa-provider`, while VDP gets
only a private systemd credential snapshot and no source-store access. The
image recipe selects both packages. They were outside the historical `.11`
evidence; later Factory39 build and focused ignition/offline receipts cover the
current implementation without claiming complete live qualification. The helper remains
outside the VDP component payload, and the image must contain no provisioned
identity, private key, shared verifier, `AOS_SECRET`, Service JWT or static
Provider/Service credential.
