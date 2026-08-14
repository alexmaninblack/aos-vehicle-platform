<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# ADR 0001: Use a Service Manager Runtime for the Provider Component

- Status: Accepted
- Date: 2026-08-14
- Scope: R6.1 vehicle-data-provider FOTA lifecycle

## Context

The development CARLA-to-KUKSA provider is currently installed beside the
released AosVM platform. That is useful for development, but it does not give
the provider an independent OEM FOTA lifecycle or a distinct entry in the
AosCloud component inventory.

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

The persistent root is on the released `/dev/aosvg/workdirs` ext4 logical
volume. The production implementation will place inactive and active payloads,
transaction metadata, and recovery state below that root. Exact A/B layout,
atomic switching, interruption recovery, and garbage collection are R6.1-3
work and are not implemented by the qualification probe.

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

The future FOTA bundle `type` must exactly match the reported runtime type.
Publishing that bundle creates the catalog metadata and assigning it creates
desired update state. Those Cloud mutations remain deferred to R6.1-6.

## Qualification Evidence

Against the exact released Service Manager source revision, the isolated
ARM64 qualification build proved:

- the Service Manager factory constructs the new runtime;
- the runtime reports the exact type, `arm64`, Linux, and one instance;
- an in-memory start/stop/status lifecycle completes without reboot;
- Service Manager protocol v5 serializes the proposed type;
- Communication Manager receives and preserves the type and architecture.

The qualification probe contains no archive, systemd, persistence, health,
slot, apply, rollback, or recovery implementation and must never be shipped as
the production runtime.

## Consequences

- R6.1-2 must build a bootstrap rootfs containing the production runtime and
  policy before a provider component can be deployed.
- R6.1-3 must implement and qualify the atomic A/B lifecycle below the selected
  persistent root.
- Provider releases can then use an OEM FOTA lifecycle independently of
  AosCore/rootfs releases.
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
