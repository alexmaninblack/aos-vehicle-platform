<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Third-Party Notices

Generated ARM64 provider artifacts use hash-locked Python wheels for these
runtime dependencies. The legacy 0.1.1 side-load archive contains the original
wheels. The R6.1 component extracts and normalizes their runtime files at build
time; it omits gRPC's default public `roots.pem` bundle because the platform
always supplies the explicitly selected KUKSA trust anchor instead.

| Component | Version | License | Source |
| --- | --- | --- | --- |
| Eclipse KUKSA Python SDK | 0.5.0 | Apache-2.0 | <https://github.com/eclipse-kuksa/kuksa-python-sdk> |
| gRPC Python | 1.75.0 | Apache-2.0 | <https://github.com/grpc/grpc> |
| Protocol Buffers Python runtime | 5.29.6 | BSD-3-Clause | <https://github.com/protocolbuffers/protobuf> |
| websockets | 15.0.1 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
| typing_extensions | 4.15.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |

The exact upstream revisions and wheel digests are recorded in
`DEPENDENCIES.json` and `packaging/aosvm/runtime/requirements-arm64.txt`.
The wheels retain their upstream package metadata and license files. They are
downloaded only while creating an ignored build artifact and are not committed
to this repository.

AosEdge, COVESA VSS, CARLA, and their protocols are also referenced for
architecture and compatibility. Their code isn't copied into this repository.

The R6.1 qualification probe compiles against exact Apache-2.0 AosCore C++ and
AosCore API revisions. A small Apache-2.0 downstream patch adds an explicit,
disabled-by-default external runtime hook and extends upstream tests. The
upstream source is fetched only into the isolated builder and isn't vendored.
