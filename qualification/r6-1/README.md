<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# R6.1 Service Manager Runtime Qualification

- Result: Pass for the R6.1-1 mechanism decision
- Date: 2026-08-14
- Production readiness: Not claimed

This directory contains the qualification-only runtime used to prove the Aos
Service Manager component lifecycle seam against the exact AosVM 6.1.0 source
baseline.

The probe implements the real Aos `RuntimeItf`, reports the proposed
vehicle-data-provider component type, supports one in-memory start/stop
instance trace, and explicitly rejects Node reboot. It deliberately does not
implement systemd supervision, archives, slots, persistence, health checks,
apply, rollback, recovery, security policy, or garbage collection.

The probe is excluded from every normal upstream build. The R6.1 downstream
qualification patch adds it only when CMake receives the explicit
`AOS_SYSTEMD_SLOT_COMPONENT_DIR` path. It must never be packaged in a bootstrap
or FOTA artifact.

Passing this probe establishes that a custom Service Manager runtime is a
viable lifecycle and reporting extension point. It does not qualify the
production runtime or Cloud catalog behavior.

## Exact Baseline

The qualification used the released AosVM 6.1.0 source selection and the
Service Manager recipe revision `9eecb80c4994937b5c8cbe0464970f81e8ad4c2d`,
with `aos_core_lib_cpp` at
`60cb83535f773762c61ac5f544b31b7b88c502e3` and `aos_core_api` at
`af3552a0a5eb0237eff7f5f183780ca46c339cd3`.

The build ran in a non-provisioned Ubuntu 22.04 ARM64 VM with GCC 11.4.0,
Conan 2.31.2, CMake 3.31.10, clang-format 15.0.7, and SoftHSM 2.6.1. No Aos
Unit identity, user certificate, OEM signing key, or Cloud token entered the
builder.

## Passed Tests

The exact-source ARM64 build completed with the upstream warning-as-error and
stack-usage gates enabled. The following focused tests passed:

- all three `SystemdSlotComponentRuntimeTest` cases;
- `RuntimesTest.InitRuntimes` with four constructed runtimes;
- `SMClientTest.SendSMInfoWithMultipleRuntimesAndResources`;
- `SMControllerTest.SMClientConnected`.

The proposed component type was preserved through the local Service Manager
protocol v5 and Communication Manager boundary together with `arm64`.

## Cloud and Storage Findings

A read-only inspection of AosCloud API v11 implementation 6.1.26 showed that
the current `aos-vm;1.0.0` model has no desired component declarations, while
the provisioned Unit already reports the independent boot and rootfs component
types. The `aos-vm-main` Node Type has no component schema. A Unit Model or
Node Type revision is not required for the new runtime type. Actual bundle
upload and assignment remain later, separately authorized work.

The released Main Node mounts `/dev/aosvg/workdirs` as persistent ext4 storage
at `/var/aos/workdirs`; Service Manager already owns
`/var/aos/workdirs/sm`. The selected component root is therefore
`/var/aos/workdirs/sm/runtimes/systemd-slot-component`.

The accepted mechanism and its consequences are recorded in
[ADR 0001](../../docs/decisions/0001-service-manager-component-runtime.md).
