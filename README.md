<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform

Vehicle-data platform integration for AosEdge, KUKSA, and automotive
providers.

## Status

Repository separation R-0 through R-5 and AOS-2 are complete. The
development-only CARLA VISS-to-KUKSA provider, its ARM64 offline runtime lock,
guarded AosVM packaging, fail-safe stale handling, and clean-restart behavior
passed end-to-end qualification on 2026-08-14. The future Authorization
Adapter and production vehicle providers aren't implemented or claimed
operational yet.

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

The stable application boundary remains the draft
[vehicle telemetry profile 0.1.1](contracts/vehicle-telemetry-profile/v0.1.1/profile.json).
The AOS-2 implementation is described in
[the provider design](docs/aos2-provider-design.md), including the accepted
end-to-end CARLA-to-KUKSA qualification result.

## Repository Layout

- `contracts/vehicle-telemetry-profile/`: versioned, machine-readable data
  contract;
- `providers/carla-viss-kuksa/`: development-only provider boundary;
- `config/kuksa/`: non-secret KUKSA platform configuration boundary;
- `packaging/aosvm/`: system packaging boundary;
- `authorization/aos-kuksa/`: deferred AOS-5 Authorization Adapter boundary;
- `tests/` and `tools/`: static contract and repository quality gates;
- `docs/`: architecture and compatibility policy.

Run the local gates with:

```text
python3 tools/validate_contract.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/quality_gate.py
```

## Security and Secrets

Do not commit private keys, access tokens, certificates, provisioned device
identities, cloud account material, vehicle-specific configuration, VM images,
or raw operational logs. See [SECURITY.md](SECURITY.md).

## License

Original project work is licensed under the Apache License, Version 2.0, with
copyright held under the exact name `maninblack`. Third-party material retains
its own license and notices. See [LICENSE](LICENSE), [NOTICE](NOTICE), and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
