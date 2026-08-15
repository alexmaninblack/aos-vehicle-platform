<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform

Vehicle-data platform integration for AosEdge, KUKSA, and automotive
providers.

## Status

Repository separation R-0 through R-5 and AOS-2 are complete. The
development-only CARLA VISS-to-KUKSA provider, its ARM64 offline runtime lock,
guarded AosVM packaging, fail-safe stale handling, and clean-restart behavior
passed end-to-end qualification on 2026-08-14. R6.1-1 through R6.1-4 and the
complete R6.1-5 signing gate are accepted. The independently versioned `0.2.0`
provider candidate passed reproducibility, official unsigned validation, the
40-test ARM64 archive/lifecycle/recovery matrix, real install, live telemetry,
source-loss, update, downgrade, failed-candidate rollback, security, SELinux,
resource, and secret-exclusion gates on 2026-08-15. The accepted candidate was
then signed and independently verified locally; it has not been published or
assigned through AosCloud. Rootfs `6.1.1-maninblack.2` is installed only on the
validation Unit. R6.1-6.5a now implements a bounded nested-ext4 demo store for
the proposed `.3` rootfs while preserving the logical component path and the
existing workdirs mount. Signing, Cloud upload, and Unit mutation remain
separate later gates. The future Authorization Adapter and production vehicle
providers aren't implemented or claimed operational yet.

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
- `meta-aos-vehicle-platform/`: Yocto bootstrap, component runtime, fixed
  provider profile, policy, and archive boundary;
- `authorization/aos-kuksa/`: deferred AOS-5 Authorization Adapter boundary;
- `qualification/r6-1/`: qualification-only Service Manager runtime probe;
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
