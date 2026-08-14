<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vehicle Telemetry Profile

This directory is the authoritative platform-owned interface between vehicle
data providers and independently deployed Aos services.

Each published profile lives in a versioned directory and validates against
`contract.schema.json`. The first draft is
[`v0.1/profile.json`](v0.1/profile.json). It references standard VSS paths but
does not copy or relicense a COVESA VSS tree.

Validate the current draft from the repository root:

```text
python3 tools/validate_contract.py
```
