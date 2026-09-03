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

## Deployable VDP v1-v3 candidates

The authorized offline path prepares one immutable unsigned `linux/arm64`
Component FOTA candidate for each accepted VDP release. It requires the exact
five-file ARM64 wheelhouse, an explicit offline guard, a clean worktree that
contains accepted source revision `5303787379d8e852e09b3ccab3e87e099c0be5cf`,
and at least 55 GiB free on the selected output filesystem. The repeatable
`1.0.14` / `1.0.15` qualification pair is pinned to Platform revision
`5303787379d8e852e09b3ccab3e87e099c0be5cf` and Factory image
`6.1.1-maninblack.27` raw SHA-256
`6d947579865d33860c88e63a4630e88ab95a6941efc3a62468d89deb61faad78`:

```text
AOS_VDP_BUILD_OFFLINE=1 PIP_NO_INDEX=1 \
python3 packaging/fota/build-provider-component \
  --vdp-version 1.0.0 \
  --wheelhouse /verified/local/arm64-wheelhouse \
  /temporary/output/vdp-1.0.0

python3 packaging/fota/validate-provider-component \
  --vdp-version 1.0.0 \
  --producer-manifest manifests/release-candidates/aosedge-vdp-component-1.0.0.manifest.json \
  /temporary/output/vdp-1.0.0
```

Repeat with `2.0.0` and `3.0.0`. Build every version twice under fresh
temporary roots and require byte equality for the prepared artifact, layer,
candidate record and canonical producer manifest before staging. After that
comparison, `--stage` on the validator copies only the prepared bytes and the
verified producer manifest to
`.local/release-candidates/sha256/<prepared-sha256>/`. The local store is
excluded from Git and is never a signing, publication, Cloud or deployment
operation. Staging rejects a manifest unless its bytes exactly equal the
version-controlled canonical producer manifest. Provenance binds the exact
embedded `dependency-lock/requirements-arm64.txt` bytes as a build input.

The prepared filenames are fixed; there is no `latest` alias. VDP v1 contains
only the seven-path base-dynamics release, v2 is its wheel-speed strict
superset, and v3 alone contains wheel-slip plus the two typed advisory flows.
The payload includes exact source/configuration identity, the five normalized
runtime wheels, SPDX SBOM, licenses, notices and provenance. It contains no
credential, certificate, Unit identity, Cloud configuration or signing data.

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
