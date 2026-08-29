#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Enable the stock Aos IAM Permission Handler in the final product config."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate IAM configuration key: {key}")
        result[key] = value
    return result


def transform(path: Path) -> None:
    original = path.stat()
    with path.open(encoding="utf-8") as stream:
        config = json.load(stream, object_pairs_hook=reject_duplicates)
    if not isinstance(config, dict):
        raise ValueError("IAM configuration root must be an object")

    config["enablePermissionsHandler"] = True
    temporary = path.with_name(path.name + ".permissions-handler.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(config, stream, indent=4, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, original.st_mode & 0o777)
    os.replace(temporary, path)

    with path.open(encoding="utf-8") as stream:
        effective = json.load(stream, object_pairs_hook=reject_duplicates)
    if effective.get("enablePermissionsHandler") is not True:
        raise ValueError("effective enablePermissionsHandler is not Boolean true")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    transform(arguments.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
