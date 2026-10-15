<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# VDP component packaging boundaries

For the current lab, use Demo Control's platform preparation flow. It composes
the reviewed **common runtime** with one immutable V1/V2/V3 capability profile,
allocates the package release separately, then signs/publishes with the selected
OEM identity. V1/V2 never enable V3 advisory merely because common code exists.
FOTA application requires Safe Stop; upload is not installation.

See the [Provider contract](../../providers/carla-viss-kuksa/README.md) and
[current operator workflow](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/operations/current-demo-workflow.md).
The integration manifest owns the exact prepared bases, common-runtime source,
Factory identity and artifact proof. Do not publish an older profile-only
payload as the current product.

## Retained low-level reproducibility tools

`build-provider-component` and `validate-provider-component` retain frozen
Provider 0.2.0 and VDP source/profile reproduction modes for existing consumers.
They are not the normal current common-runtime composition entry.

Inspect the supported interfaces without creating an artifact:

```sh
python3 packaging/fota/build-provider-component --help
python3 packaging/fota/validate-provider-component --help
```

The default Provider 0.2.0 builder reads its accepted source from
`e972d2bd7f14e27646bb5d7c10c7186ecdecfa9f` and refuses altered packaging inputs
or wheel locks under that immutable identity. Explicit `--vdp-version`
reproduction uses its own canonical producer manifests, exact ARM64
wheelhouse, offline guard, accepted source and output-capacity checks.
Those historical identities are not today's image or release selectors.

The validator's explicit `--stage` promotes only exact verified bytes and a
canonical producer manifest to the ignored digest-keyed local store. It is
not signing, Cloud publication, assignment or deployment. No newest-by-time
or mutable latest alias is accepted.

## Source prebuilds

`--source-prebuild-version` produces explicitly non-deployable deterministic
source inputs for the selected profile. It does not compile/extract ARM64
runtime dependencies, build an Aos envelope, sign or publish. A profile-only
source prebuild must not be mistaken for a current common-runtime package.

Selected profiles have distinct capability-manifest digests. V1 has seven
base paths; V2 adds wheel speeds; V3 adds slip inputs and the two typed advisory
flows. Runtime profile, source identity and allocated Cloud release number
remain separate namespaces.

## Payload and ownership

Unsigned output contains immutable application/runtime content, exact
configuration/source provenance, locked dependencies, SBOM and public notices.
The Factory owns the component runtime, fixed launcher, systemd/SELinux
integration and persistent-store boundary.

No credential, certificate, Unit identity, Cloud configuration, private key,
installer or systemd unit is embedded in a reusable Provider component.
Keep reusable bases and dependency caches intact. Disposable artifact work
belongs to the integration workspace's managed scratch, not a volume-root
temporary directory or an old experiment tree.
