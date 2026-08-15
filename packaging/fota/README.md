<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vehicle-Data Provider FOTA Packaging

This directory is the only supported packaging path for the development
CARLA VISS-to-KUKSA provider. It produces the deterministic ARM64 provider
component consumed by the Service Manager `systemd-slot-component` runtime.

Provider `0.2.0` is immutable. The builder pins its accepted source revision
to `e972d2bd7f14e27646bb5d7c10c7186ecdecfa9f` and refuses to rebuild that
version if any release input or the ARM64 dependency lock differs. Repository
documentation and Yocto integration may advance without silently producing
different bytes under the accepted provider version.

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
