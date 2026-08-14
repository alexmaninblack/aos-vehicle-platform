<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform

Vehicle-data platform integration for AosEdge, KUKSA, and automotive
providers.

## Status

This repository is in its governance bootstrap phase. No provider,
Authorization Adapter, or production vehicle integration is implemented or
claimed operational yet.

## Ownership Boundary

This repository owns vehicle-program platform components with an
OEM-controlled platform/FOTA qualification lifecycle:

- versioned vehicle-data contracts;
- vehicle-data providers, beginning with a development-only CARLA
  VISS-to-KUKSA provider;
- KUKSA platform and trust configuration;
- system-level AosVM packaging;
- the future Aos-to-KUKSA Authorization Adapter;
- provider conformance and platform integration tests.

Cloud-managed business applications and the CARLA simulator runtime are not
owned here. The first telemetry application belongs to
`vehicle-telemetry-service`; end-to-end macOS/AosVM orchestration belongs to
`carla-aosedge-integration`.

## Security and Secrets

Do not commit private keys, access tokens, certificates, provisioned device
identities, cloud account material, vehicle-specific configuration, VM images,
or raw operational logs. See [SECURITY.md](SECURITY.md).

## License

Original project work is licensed under the Apache License, Version 2.0, with
copyright held under the exact name `maninblack`. Third-party material retains
its own license and notices. See [LICENSE](LICENSE), [NOTICE](NOTICE), and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
