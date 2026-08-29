<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Third-Party Notices

The accepted ARM64 provider component uses hash-locked Python wheels for these
runtime dependencies. The FOTA builder extracts and normalizes their runtime
files; it omits gRPC's default public `roots.pem` bundle because the platform
always supplies the explicitly selected KUKSA trust anchor instead.
The upstream native gRPC extension also embeds public default roots internally;
those bytes cannot be removed without rebuilding gRPC. They are inert in this
provider because every KUKSA connection passes the platform-owned CA file
explicitly. No private key or vehicle identity is included.

| Component | Version | License | Source |
| --- | --- | --- | --- |
| Eclipse KUKSA Python SDK | 0.5.0 | Apache-2.0 | <https://github.com/eclipse-kuksa/kuksa-python-sdk> |
| gRPC Python | 1.75.0 | Apache-2.0 | <https://github.com/grpc/grpc> |
| Protocol Buffers Python runtime | 5.29.6 | BSD-3-Clause | <https://github.com/protocolbuffers/protobuf> |
| websockets | 15.0.1 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
| typing_extensions | 4.15.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |

The exact upstream revisions and wheel digests are recorded in
`DEPENDENCIES.json` and `packaging/fota/requirements-arm64.txt`.
The wheels retain their upstream package metadata and license files. They are
downloaded only while creating an ignored build artifact and are not committed
to this repository.

AosEdge, COVESA VSS, CARLA, and their protocols are also referenced for
architecture and compatibility. Their code isn't copied into this repository.

## KUKSA authorization compatibility package

The removable native KUKSA authorization helper uses the exact Yocto-locked
C++ runtime and build dependencies below. Target runtime packages and native
generators are selected as matched pairs from the same frozen revisions.
Exact Git-mirror and archive digests are recorded in `DEPENDENCIES.json`.

| Component | Version | Use | Declared recipe license | Source |
| --- | --- | --- | --- | --- |
| gRPC C++ | 1.60.1 | Target runtime and `grpc-native` generator | Apache-2.0 & BSD-3-Clause & MPL-2.0 | <https://github.com/grpc/grpc> |
| Protocol Buffers C++ | 4.25.8 | Target runtime and `protobuf-native` compiler | BSD-3-Clause | <https://github.com/protocolbuffers/protobuf> |
| Abseil C++ | 20240116.3 | Target support runtime required by generated Protocol Buffers code | Apache-2.0 | <https://github.com/abseil/abseil-cpp> |
| OpenSSL | 3.2.6 | Target cryptographic runtime | Apache-2.0 | <https://github.com/openssl/openssl> |
| SoftHSM | 2.6.1 | Target PKCS#11 software token | BSD-2-Clause & ISC | <https://github.com/opendnssec/SoftHSMv2> |
| OpenSSL PKCS#11 provider | recipe 1.0 baseline | Target OpenSSL provider module | Apache-2.0 | <https://github.com/latchset/pkcs11-provider> |

`grpc-native` and `protobuf-native` are build-host tools and are not target
runtime packages. The package links only the target gRPC, Protocol Buffers,
Abseil and OpenSSL libraries; SoftHSM and the official OpenSSL PKCS#11 provider
remain runtime modules rather than directly linked libraries.
