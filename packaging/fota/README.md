<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vehicle-Data Provider FOTA Packaging

This directory is the only supported packaging path for the development
CARLA VISS-to-KUKSA provider. It produces the deterministic ARM64 provider
component consumed by the Service Manager `systemd-slot-component` runtime.

Provider `0.2.0` is immutable. The builder pins its accepted source revision
to `e972d2bd7f14e27646bb5d7c10c7186ecdecfa9f`, reads provider sources and
notices from that revision, and refuses changed packaging inputs or an altered
ARM64 dependency lock. Repository documentation, provider development, and
Yocto integration may advance without silently producing different bytes
under the accepted provider version.

The unsigned candidate contains the provider, five hash-locked ARM64 Python
dependencies, component metadata, provenance, an SPDX SBOM, licenses, and
third-party notices. It contains no installer, systemd unit, credential,
private key, Unit identity, or Cloud configuration.

Build and validate only from a clean checkout:

```text
python3 packaging/fota/build-provider-component build/provider-0.2.0
python3 packaging/fota/validate-provider-component build/provider-0.2.0
```

Signing, publication, assignment, and deployment are integration gates and
are intentionally absent from this repository workflow.

## VDP v1-v3 source prebuilds

The same entry points also prepare and validate deterministic, explicitly
non-deployable source inputs for VDP `1.0.0`, `2.0.0` and `3.0.0`:

```text
python3 packaging/fota/build-provider-component --source-prebuild-version 1.0.0 build/vdp-1-source
python3 packaging/fota/validate-provider-component --source-prebuild-version 1.0.0 build/vdp-1-source
```

Repeat with `2.0.0` or `3.0.0`. This mode performs no dependency download,
compilation, wheel extraction, ARM64 layer build, Aos envelope build, signing
or publication. It produces a deterministic USTAR of pinned source inputs plus
identity metadata so the separately authorized artifact build can consume one
reviewed profile without a source edit.

Each prebuild contains only its selected release profile. The v3 advisory
module is absent from v1 and v2. All releases contain their exact capability
manifest, contract digests, dependency-lock digest, provenance input, license
and notices. Secret-negative validation rejects credential material. The
historical default command remains the distinct Provider `0.2.0` path and
continues to read its accepted source bytes from the frozen revision.
