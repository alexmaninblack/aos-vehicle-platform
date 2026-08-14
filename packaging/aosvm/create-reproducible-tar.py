#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Create a normalized gzip-compressed tar archive without macOS metadata."""

from __future__ import annotations

import argparse
import gzip
import os
import tarfile
from pathlib import Path


def normalized(info: tarfile.TarInfo, executable: bool) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.pax_headers = {}
    if info.isdir():
        info.mode = 0o755
    elif info.isfile():
        info.mode = 0o755 if executable else 0o644
    return info


def create(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    if not source.is_dir() or source.is_symlink():
        raise ValueError("source must be a safe directory")
    paths = [source, *sorted(source.rglob("*"))]
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}")
    try:
        with temporary.open("xb") as raw_archive:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_archive, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT
                ) as archive:
                    for path in paths:
                        if path.name.startswith("._") or path.is_symlink():
                            raise ValueError(f"unsafe bundle path: {path}")
                        relative = path.relative_to(source.parent)
                        info = normalized(
                            archive.gettarinfo(path, arcname=str(relative)),
                            path.is_file() and os.access(path, os.X_OK),
                        )
                        if path.is_file():
                            with path.open("rb") as source_file:
                                archive.addfile(info, source_file)
                        else:
                            archive.addfile(info)
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    create(arguments.source, arguments.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
