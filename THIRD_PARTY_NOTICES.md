<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Third-Party Notices

Generated ARM64 provider bundles contain unmodified Python wheels for these
runtime dependencies:

| Component | Version | License | Source |
| --- | --- | --- | --- |
| Eclipse KUKSA Python SDK | 0.5.0 | Apache-2.0 | <https://github.com/eclipse-kuksa/kuksa-python-sdk> |
| gRPC Python | 1.75.0 | Apache-2.0 | <https://github.com/grpc/grpc> |
| Protocol Buffers Python runtime | 5.29.5 | BSD-3-Clause | <https://github.com/protocolbuffers/protobuf> |
| websockets | 15.0.1 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
| typing_extensions | 4.15.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |

The exact upstream revisions and wheel digests are recorded in
`DEPENDENCIES.json` and `packaging/aosvm/runtime/requirements-arm64.txt`.
The wheels retain their upstream package metadata and license files. They are
downloaded only while creating an ignored build artifact and are not committed
to this repository.

AosEdge, COVESA VSS, CARLA, and their protocols are also referenced for
architecture and compatibility. Their code isn't copied into this repository.
