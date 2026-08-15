<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR 0001: Use a Service Manager Runtime for the Provider Component

- Status: Accepted
- Date: 2026-08-14; demo storage amendment 2026-08-15
- Scope: R6.1 vehicle-data-provider FOTA lifecycle

## Context

The first CARLA-to-KUKSA prototype was installed beside the released AosVM
platform. That development arrangement did not give the provider an
independent OEM FOTA lifecycle or a distinct entry in the AosCloud component
inventory.

The released Aos Service Manager supports component runtimes for boot and
rootfs plus the normal container runtime. It does not provide a generic
systemd-managed A/B payload runtime. R6.1 therefore had to prove whether the
existing Service Manager runtime boundary can safely own a new component
without changing the provisioned Unit identity.

## Decision

Implement the production vehicle-data-provider lifecycle as a dedicated Aos
Service Manager runtime integrated by the OEM bootstrap image.

The fixed runtime contract is:

- plugin: `systemd-slot-component`;
- component flag: `isComponent: true`;
- unprefixed type in the Yocto input: `vehicle-data-provider`;
- reported type after the released Aos component prefix is applied:
  `aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider`;
- persistent root:
  `/var/aos/workdirs/sm/runtimes/systemd-slot-component`;
- maximum active instances: one;
- no Node reboot for ordinary provider prepare, start, stop, apply, or revert.

The bootstrap image owns the runtime implementation, Service Manager factory
registration, systemd launcher, health boundary, SELinux policy, stable
KUKSA-facing integration, and empty component store. The independently signed
provider bundle owns the provider executable and its runtime dependencies.

The logical persistent root remains below the released `/dev/aosvg/workdirs`
ext4 logical volume. The production runtime places inactive and active
payloads, transaction metadata, and recovery state below that root and owns
the qualified A/B switching, interruption recovery, rollback, and garbage
collection behavior.

The provisioned demonstration VM mounts the complete workdirs filesystem with
the fixed SELinux context `aos_var_run_t`. It therefore cannot give only the
provider subtree its accepted `vehicle_data_provider_store_t` type. For the
R6.1-6.5a demonstration gate, use a fully allocated 512 MiB ext4 image stored
inside workdirs and mount it at the unchanged logical root with the dedicated
fixed provider-store context. The image has a recorded per-Unit UUID and fixed
platform-controlled path, size, label, mount options, reserve, preparation,
and recovery rules. Existing AosCore workdirs data is neither relabelled nor
migrated, and the provider receives only directory-search access through the
generic parent path.

This nested filesystem is a demo backend, not the selected production vehicle
storage architecture. A dedicated logical volume, a controlled conversion to
per-inode labels, or an equivalent OEM platform abstraction remains a separate
architecture and migration decision. The Service Manager contract and signed
provider path do not depend on which accepted backend implements the logical
root.

Keep the existing Cloud identity unchanged:

- Unit Model: `aos-vm;1.0.0`;
- Node Type: `aos-vm-main`;
- topology: one Main Node.

The AosCloud v11 schema and the live read-only inventory show that runtime
component types are reported independently of the Unit Configuration. The
current Unit Configuration contains only its Node declaration and has no
desired components, while the Unit already reports separate boot and rootfs
components. The Node Type schema contains resource ratios, not component
definitions. A Unit Model or Node Type revision is therefore not required to
introduce this runtime type.

The provider FOTA bundle `type` exactly matches the reported runtime type.
Publishing a signed bundle creates the catalog metadata and assigning it
creates desired update state. The accepted `0.2.0` provider bundle and rootfs
candidate `.11` remain local: signing `.11`, Cloud upload, assignment, and
installation are separate explicit gates.

## Qualification Evidence

Against the exact released Service Manager source revision, the isolated
ARM64 qualification build proved:

- the Service Manager factory constructs the new runtime;
- the runtime reports the exact type, `arm64`, Linux, and one instance;
- an in-memory start/stop/status lifecycle completes without reboot;
- Service Manager protocol v5 serializes the proposed type;
- Communication Manager receives and preserves the type and architecture.

The qualification probe contained no archive, systemd, persistence, health,
slot, apply, rollback, or recovery implementation. It was never a production
runtime and was removed from the current tree after the production
implementation passed the corresponding gates; Git history retains the
evidence.

## Consequences

- The accepted rootfs candidate contains the production runtime and policy.
- The atomic A/B lifecycle below the selected persistent root is implemented
  and qualified.
- Provider releases can use an OEM FOTA lifecycle independently of
  AosCore/rootfs releases.
- The demonstration backend preserves that lifecycle without weakening the
  provider SELinux domain or changing the signed provider path contract.
- The provider unit uses a dedicated non-login `aos-vdp` account. Only the
  fixed launcher enters `vehicle_data_provider_t`; systemd has already
  established the UID/GID and an empty capability bounding set. The launcher
  verifies the fixed identity, supplementary-group state, and empty runtime
  capabilities, enables `no_new_privs`, and only then executes the selected
  payload. This preserves both the SELinux transition and a non-root payload
  on the pinned AosVM policy baseline without any identity-changing
  capability.
- Rootfs rollback from candidate `.11` to the currently installed `.2`, which
  lacks the nested mount support, must
  first suspend or remove the provider assignment; transparent cross-backend
  rollback is not claimed.
- The existing provisioned Unit is neither deprovisioned nor reprovisioned.
- The Update Manager fallback is rejected for this design because the Service
  Manager extension point passed the local factory, lifecycle, protocol, and
  CM gates. It may be reconsidered only if later production constraints expose
  a new blocking property.
- Cloud catalog acceptance, deployment, update, and rollback are not implied
  by the local qualification and remain explicit later gates.

## Alternatives Rejected

- Keep the provider side-loaded: no independent managed component lifecycle.
- Package the provider as a normal SOTA service: wrong OEM/platform ownership
  and privilege boundary.
- Couple every provider update to a full rootfs image: prevents independent
  provider releases.
- Use Update Manager immediately: unnecessary after the Service Manager seam
  was proven and less aligned with current runtime inventory reporting.
- Deprovision and reprovision the demonstration Unit: unnecessary and risks
  its persistent identity without solving the runtime problem.
