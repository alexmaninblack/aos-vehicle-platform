#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""One offline Camera Access foundation scenario; no build or live runtime."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FILES = {"README.md", "docs/architecture.md", "tests/test_camera_access.py",
                 "tests/test_camera_access_gate.py", "tools/check_camera_access.py"}
ALLOWED_PREFIXES = ("camera-access/", "contracts/camera-access/")


def preserved_source(paths: list[str]) -> bool:
    """This packet cannot change retained VDP/Factory/build selectors."""
    return all(path in ALLOWED_FILES or path.startswith(ALLOWED_PREFIXES) for path in paths)


def main() -> int:
    started = time.monotonic()
    result = dict(scenario="CAMERA_ACCESS_FOUNDATION_SOURCE", outcome="FAIL", phases=[],
                  nativeAuthorization="NOT_RUN", deployment="NOT_RUN", liveCamera="NOT_RUN",
                  carlaOrFactoryRebuilt=False, liveRuntimeStarted=False)
    try:
        changed = subprocess.check_output(["git", "diff", "--name-only", "main", "--"], cwd=ROOT, text=True).splitlines()
        changed += subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True).splitlines()
        if not preserved_source(changed):
            raise ValueError("RETAINED_PLATFORM_SOURCE_CHANGED")
        for name, args in (
            ("camera-unit-contract", ["-m", "unittest", "discover", "-s", "tests", "-p", "test_camera_access*.py"]),
            ("repository-policy", ["tools/quality_gate.py"]),
            ("retained-telemetry-contract", ["tools/validate_contract.py"]),
            ("retained-factory-layer", ["tools/validate_r6_1_layer.py"]),
        ):
            print(json.dumps(dict(stage=name, state="STARTED")), flush=True)
            begin = time.monotonic()
            run = subprocess.run([sys.executable, "-B", *args], cwd=ROOT, check=False)
            result["phases"].append(dict(stage=name, seconds=round(time.monotonic()-begin, 3), exit=run.returncode))
            if run.returncode:
                raise ValueError("SOURCE_GATE_FAILED")
        result["outcome"] = "PASS_SOURCE_ONLY"
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        code = str(error)
        result["code"] = code if code in ("RETAINED_PLATFORM_SOURCE_CHANGED", "SOURCE_GATE_FAILED") else "SOURCE_CHECK_ERROR"
    result["seconds"] = round(time.monotonic()-started, 3)
    print(json.dumps(result), flush=True)
    return 0 if result["outcome"] == "PASS_SOURCE_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
