<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Vehicle Telemetry Profile

This directory retains platform-owned prototype compatibility profiles and
their validator. It is not the selector for the delivered VDP's functional
profile, signals or timing. Use [current compatibility rules](../../docs/contract-compatibility.md)
and the integration [VDP contract](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/contracts/vdp-compatibility-profile/README.md)
for those boundaries.

Versioned profiles validate against `contract.schema.json`.
[`v0.1.1/profile.json`](v0.1.1/profile.json) retains the standard `degrees`
steering-unit spelling; the immutable 0.1.0 fixture preserves its original
metadata. These immutable fixtures are not competing current authoring
instructions. They reference standard VSS paths without copying or
relicensing a COVESA VSS tree.

Validate the retained prototype profile from the repository root:

```text
python3 tools/validate_contract.py
```
