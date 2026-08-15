<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vehicle Telemetry Profile

This directory is the authoritative platform-owned interface between vehicle
data providers and independently deployed Aos services.

Each published profile lives in a versioned directory and validates against
`contract.schema.json`. The current accepted prototype profile is
[`v0.1.1/profile.json`](v0.1.1/profile.json). Patch 0.1.1 corrects the steering
unit metadata from `degree` to the standard VSS 5.0 and VSS 6.0 identifier
`degrees`; it does not change the numeric value or conversion. The superseded
0.1.0 profile remains immutable for baseline traceability. Profiles reference
standard VSS paths but do not copy or relicense a COVESA VSS tree.

Validate the current profile from the repository root:

```text
python3 tools/validate_contract.py
```
