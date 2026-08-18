<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform

Vehicle-computer integration for AosEdge, KUKSA, and automotive data
providers. This repository follows the OEM platform/FOTA lifecycle and does
not contain cloud-managed business services or CARLA simulator runtime code.

## Current Baseline

The current accepted implementation provides:

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
`6.1.1-maninblack.2`; the demonstration Unit remains on `6.1.0`. Production
vehicle storage and the Aos–KUKSA Credential Broker/OEM access-policy flow
remain explicit target architecture gates.

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

Read:

- [architecture and ownership](docs/architecture.md);
- [provider design and qualification](docs/aos2-provider-design.md);
- [Service Manager runtime decision](docs/decisions/0001-service-manager-component-runtime.md);
- [contract compatibility](docs/contract-compatibility.md);
- [provider FOTA packaging](packaging/fota/README.md).

## Repository Layout

- `contracts/vehicle-telemetry-profile/`: authoritative vehicle-data contract;
- `providers/carla-viss-kuksa/`: development-only simulation provider;
- `packaging/fota/`: immutable provider component build and validation;
- `meta-aos-vehicle-platform/`: production Yocto runtime, storage, systemd,
  launcher, health, and SELinux integration;
- `config/kuksa/`: non-secret KUKSA platform configuration boundary;
- `authorization/aos-kuksa/`: target Credential Broker and OEM access-policy
  boundary inside the Vehicle Data Platform Component;
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
