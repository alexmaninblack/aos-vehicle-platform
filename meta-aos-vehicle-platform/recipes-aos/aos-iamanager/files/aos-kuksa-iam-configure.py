#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Add exactly the fixed KUKSA certificate module to an installed iam.cfg."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


MODULE = {
    "id": "kuksa-jwt",
    "plugin": "pkcs11",
    "algorithm": "rsa",
    "maxItems": 1,
    "selfSigned": True,
    "params": {
        "library": "/usr/lib/softhsm/libsofthsm2.so",
        "tokenLabel": "aos-kuksa",
        "userPinPath": "/var/aos/iam/.kuksa-jwt-pin",
        "modulePathInUrl": True,
    },
}


def transform(document: object) -> dict[str, object]:
    if not isinstance(document, dict):
        raise ValueError("iam.cfg must be one JSON object")
    if document.get("enablePermissionsHandler") is not True:
        raise ValueError("enablePermissionsHandler must already be true")
    modules = document.get("certModules")
    if not isinstance(modules, list) or any(not isinstance(item, dict) for item in modules):
        raise ValueError("certModules must be an array of objects")
    identifiers = [item.get("id") for item in modules]
    if any(not isinstance(identifier, str) or not identifier for identifier in identifiers):
        raise ValueError("every certificate module requires an id")
    if len(identifiers) != len(set(identifiers)) or "kuksa-jwt" in identifiers:
        raise ValueError("certificate module ids must be unique and kuksa-jwt absent")
    result = dict(document)
    result["certModules"] = [*modules, MODULE]
    return result


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: aos-kuksa-iam-configure.py IAM_CFG")
    path = Path(sys.argv[1])
    before = json.loads(path.read_text(encoding="utf-8"))
    after = transform(before)
    temporary = path.with_name(path.name + ".kuksa.tmp")
    temporary.write_text(json.dumps(after, indent=4) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
