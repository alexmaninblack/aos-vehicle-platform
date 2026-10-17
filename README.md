<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform

OEM platform integration: vehicle data, KUKSA authorization, Factory integration and Safe Stop-gated VDP FOTA. Brake/Tire applications belong to separate SOTA repositories.

<a id="sdv-lab-entry"></a>

For the **whole demo**, start at the [SDV Lab README](https://github.com/alexmaninblack/aosedge-sdv-demo).
The product launcher prepares its pinned multi-component checkouts automatically.
The instructions below are for working on **this component alone**;
a host check does not publish, install or qualify a vehicle package.

## 1 Prepare a macOS component workspace

Use native Apple Silicon Terminal. These component commands are for development,
not a qualified full-demo installation. Run blocks in order and stop on error.

Choose an existing writable local APFS parent folder, on the internal disk or
an external SSD. Use the product launcher instead for automatic full-demo
preparation; this section is only the component workflow:

```sh
uname -m
printf 'Existing local APFS parent folder (absolute path): '
read -r SDV_PARENT
test -d "$SDV_PARENT" && test -w "$SDV_PARENT" && df -h "$SDV_PARENT"
```

Expect `arm64` and enough free space on the selected volume. Stop if the
folder/access check fails; do not create a replacement for a disconnected
volume. An external SSD is optional. After confirming storage:

```sh
SDV_WORK="$SDV_PARENT/sdv-components"
mkdir -p "$SDV_WORK"
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
Its developer route **reuses** the pinned ARM64 controller image (Factory)
and unsigned VDP bases; it does not rebuild them for a normal installer build.
For a new image, the separate
[Factory subroute](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/getting-started/full-source-build.md#factory-subroute)
requires a separately prepared ARM64 Linux Builder and explicit source/cache inputs.
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

## Platform reference

The Factory image is the unprovisioned Linux/AosEdge base for the ARM64
controller. VDP profiles are delivered afterward through OEM FOTA and require
Safe Stop; they are not separate factory images.

- [Yocto layer and image integration](meta-aos-vehicle-platform/README.md)
- [VDP packaging and validation](packaging/fota/README.md)
- [Native service input projection](docs/service-runtime-inputs.md)
- [Aos/KUKSA authorization integration](authorization/aos-kuksa-compat/README.md)

Use the integration repository's selected image and source plan when building
the complete lab. Do not replace an existing controller's backing image.

## Security and license

Keep certificates, keys, tokens, provisioned disks and operational data out of
Git. See [SECURITY.md](SECURITY.md). Original work is Apache-2.0 under
`maninblack`; see [LICENSE](LICENSE), [NOTICE](NOTICE) and
[third-party notices](THIRD_PARTY_NOTICES.md).
