<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform

OEM platform integration: vehicle data, KUKSA authorization, Factory integration and Safe Stop-gated VDP FOTA. Brake/Tire applications belong to separate SOTA repositories.

<a id="sdv-lab-entry"></a>

For the **whole demo**, start at the [SDV Lab README](https://github.com/alexmaninblack/aosedge-sdv-demo).
Only the product repository is manually cloned for its pinned multi-component
build. The instructions below are for working on **this component alone**;
a host check does not publish, install or qualify a vehicle package.

## 1 Prepare a macOS component workspace

Use native Apple Silicon Terminal. These component commands are for development,
not a qualified full-demo installation. Run blocks in order and stop on error.
The revised instructions await the joint walkthrough; they were not executed
during this documentation update.

Choose an already mounted external APFS SSD:

```sh
uname -m
printf 'Mounted external APFS volume (for example /Volumes/BUILD): '
read -r SDV_VOLUME
diskutil info "$SDV_VOLUME"
df -h "$SDV_VOLUME"
```

Expect `arm64` and the actual external volume. Do not create a missing mount
directory. After confirming storage:

```sh
SDV_WORK="$SDV_VOLUME/sdv-components"
mkdir -p "$SDV_WORK" "$SDV_VOLUME/tmp"
export TMPDIR="$SDV_VOLUME/tmp"
export HOMEBREW_CACHE="$SDV_WORK/cache/homebrew"
```

Install Apple's Command Line Tools with `xcode-select --install` if missing,
and finish the system dialog. Install [Homebrew](https://docs.brew.sh/Installation)
if absent. Then:

```sh
eval "$(/opt/homebrew/bin/brew shellenv)"
brew install cmake python@3.12
export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"
git --version
cmake --version
python3 --version
xcrun clang++ --version
```

Do not use the installed demo's private interpreter or a Rosetta toolchain.

## 2 Clone this component

```sh
git clone --branch main https://github.com/alexmaninblack/aos-vehicle-platform.git "$SDV_WORK/aos-vehicle-platform"
cd "$SDV_WORK/aos-vehicle-platform"
git rev-parse HEAD
```

Record the printed revision with your results. `main` is current development,
not a release pin. To reproduce the complete candidate, use the product
repository's manifest-driven route instead of independently choosing branches.

## 3 Run the source checks

There is no standalone macOS platform server to launch from this repository.
These checks inspect contracts, the layer and host-side behavior; they do not
build or boot a Yocto image.

```sh
python3 -B tools/validate_contract.py
python3 -B tools/validate_r6_1_layer.py
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B tools/quality_gate.py
```

Each command must exit successfully. This is source-check evidence, not
Factory, FOTA or live service acceptance.

## 4 Build and run the integrated platform

Use the [product repository](https://github.com/alexmaninblack/aosedge-sdv-demo) for the complete installer.
Its developer route **reuses** the pinned Factory .41 and VDP bases.
For a new image, the separate
[Factory subroute](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/5e30b410cbeadd2f73063b1bd313253aff612595/docs/getting-started/full-source-build.md#factory-subroute)
requires the SSD-backed ARM64 Builder and explicit source/cache inputs.
Fresh Builder acquisition is not yet a turnkey clean-Mac route.

Do not copy a Factory image over a running VM's backing disk. VDP releases
are prepared and signed by Demo Control, applied through Safe Stop and checked
one version at a time. Source checks above need no Cloud credentials.

## 5 Finish

The source checks are foreground commands and leave no platform service to
stop. Keep their results and the recorded revision. For an integrated run,
stop through Demo Control; stopping is not destructive **Finish demo**.

## Component documentation

- [Architecture and ownership](docs/architecture.md)
- [Vehicle telemetry contract](contracts/vehicle-telemetry-profile/README.md)
- [Provider FOTA packaging](packaging/fota/README.md)
- [Security](SECURITY.md) and [third-party notices](THIRD_PARTY_NOTICES.md)

## Implementation reference and dated evidence

The material below preserves detailed contracts, milestones and specialist
examples. Historical commands are not the first-use sequence above. Original
qualification dates/scope remain unchanged by this documentation revision.

<details>
<summary>Expand implementation reference and historical evidence</summary>

## Current baseline — 7 October 2026

The selected integration candidate is **Kit028 / Setup042 / Factory .41**.
The [source return point](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/5e30b410cbeadd2f73063b1bd313253aff612595/docs/qualification/kit028-setup042-source-publication-2026-10-05.md)
distinguishes the exact Factory build source from subsequent license-only source
changes; the [current baseline](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/5e30b410cbeadd2f73063b1bd313253aff612595/docs/qualification/current-baseline.md)
owns qualification. Historical demo-v1.1 / Factory .39 is not the current kit.

Factory contains mainline-derived AosCore with explicit retained patches,
KUKSA, native IAM permissions, KAC and the empty-slot OEM component runtime.
The .41 build includes CM VLAN-allocation correction and preservation of original
source timestamps in KUKSA VAL v1. VDP V1/V2/V3 use the common runtime and are
prepared unsigned, then signed for the selected OEM. FOTA requires Safe Stop;
Brake/Tire SOTA artifacts belong to their own repositories.

Kit028's installed M1 sequence passed 98 scripted steps including serial
profiles, real products, offline recovery and ignition. Full native acceptance,
moving SOTA, secure UI token entry and installation interruption/repair remain
open. The immutable Factory build manifest stays `BUILT_NOT_LIVE_QUALIFIED`;
later installed evidence does not rewrite it. VDP-TIMEOUT-01 and brief
load-sensitive readiness remain deferred. See the
[implementation map](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/5e30b410cbeadd2f73063b1bd313253aff612595/docs/architecture/current-implementation.md).

The .11/0.2.0 material below is historical; its old IAM/helper gaps and Unit
assignments are not descriptions of the current platform or live state.

## Historical early platform baseline

The early .11 implementation provided:

- vehicle telemetry profile `0.1.1` over `kuksa.val.v1`;
- a development-only CARLA VISS-to-KUKSA provider;
- immutable provider component `0.2.0`, signed and locally verified but not
  published or assigned in AosCloud;
- a production Service Manager `systemd-slot-component` runtime with atomic
  A/B apply, rollback, recovery, and one active instance;
- a fixed non-login `aos-vdp` identity, empty Linux capability set, SELinux
  isolation, systemd credentials, fail-safe DNS/TLS behavior, and soft KUKSA
  lifecycle dependency;
- a bounded 512 MiB nested-ext4 provider store for the demonstration AosVM;
- an OEM Yocto layer used by the accepted local rootfs
  `6.1.1-maninblack.11` candidate.

The `.11` rootfs candidate is unsigned and has not been uploaded or installed
on a provisioned Unit. The validation Unit remains on
`6.1.1-maninblack.2`; the demonstration Unit remains on
`6.1.1-maninblack.1`. Production vehicle storage, the separately packaged
current-release KUKSA Authorization Compatibility helper, protected per-Unit
signing integration, and the trusted Provider connection profile remain
explicit target architecture gates. The helper is Factory/System integration
outside the VDP FOTA payload and both SOTA services. The current live AosVM
configuration does not enable the stock IAM permission handler required by
that target Service credential flow.

The `.11` build produced two lifecycle-distinct outputs from the same rootfs
content: a complete unprovisioned raw VM image and an unsigned rootfs FOTA
envelope. The raw image is engineering evidence for an OEM factory-image
baseline in which the provider-specific empty-slot runtime exists before Unit
provisioning. The rootfs envelope is an optional retrofit or later platform
update for an older provisioned Unit; it is not the independently delivered
Vehicle Data Platform Component.

Accepted provider `0.2.0` is pinned to source revision
`e972d2bd7f14e27646bb5d7c10c7186ecdecfa9f`. The FOTA builder refuses to
produce different bytes under that version if a release input changes.

## Architecture

```text
DEVELOPMENT HOST                   AOS VEHICLE COMPUTER

CARLA -> VISS 3.1 -> provider -> KUKSA Databroker -> Aos service
                     platform      platform           separate repository
```

A production vehicle replaces the CARLA provider with CAN, SOME/IP, DDS, or
OEM-specific providers while preserving the versioned KUKSA/VSS contract.

The target demo services are QM-domain maintenance applications. This
repository validates their outbound typed advisories as defense in depth; the
Vehicle Gateway owns the final deny-by-default boundary and no service gains
vehicle-motion or safety-critical authority.

Read:

- [architecture and ownership](docs/architecture.md);
- [provider design and qualification](docs/aos2-provider-design.md);
- [Service Manager runtime decision](docs/decisions/0001-service-manager-component-runtime.md);
- [contract compatibility](docs/contract-compatibility.md);
- [opt-in Test service public-input resources](docs/service-runtime-inputs.md);
- [provider FOTA packaging](packaging/fota/README.md).

## Repository Layout

- `contracts/vehicle-telemetry-profile/`: authoritative vehicle-data contract;
- `providers/carla-viss-kuksa/`: development-only simulation provider;
- `packaging/fota/`: immutable provider component build and validation;
- `meta-aos-vehicle-platform/`: production Yocto runtime, storage, systemd,
  launcher, health, and SELinux integration;
- `config/kuksa/`: non-secret KUKSA platform configuration boundary;
- `authorization/aos-kuksa-compat/`: implemented separately packaged removable
  current-release Service authorization helper, packaged separately from VDP;
- `authorization/aos-kuksa/`: superseded historical design notes retained only
  to prevent accidental reuse of the former VDP-owned broker model;
- `tests/` and `tools/`: repository, contract, packaging, and layer gates.

Legacy SSH side-load packaging and the qualification-only runtime probe were
removed from the current tree after the production runtime passed. They remain
available through Git history only.

## Validation

```text
python3 tools/validate_contract.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/validate_r6_1_layer.py
python3 tools/quality_gate.py
```

## Security and License

Never commit private keys, tokens, certificates, provisioned identities,
Cloud account material, vehicle-specific credentials, VM images, or raw
operational logs. See [SECURITY.md](SECURITY.md).

Original project work is Apache-2.0 under the exact copyright name
`maninblack`. Third-party material retains its own terms; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

</details>
