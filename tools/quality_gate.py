#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Run dependency, credential, binary, language, and SPDX policy checks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_FROM_HEADER = {"LICENSE", "NOTICE", "LICENSES/Apache-2.0.txt"}
BINARY_SUFFIXES = {
    ".7z", ".bin", ".cer", ".crt", ".der", ".dmg", ".img", ".iso",
    ".jar", ".jks", ".key", ".ova", ".ovf", ".p12", ".pfx", ".pem",
    ".qcow2", ".tar", ".war", ".zip",
}
ALLOWED_DEPENDENCY_LICENSES = {
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "GPL-2.0-only",
    "GPL-3.0-or-later",
    "ISC",
    "MIT",
    "MPL-2.0",
    "PSF-2.0",
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def check_spdx(files: list[Path]) -> list[str]:
    errors: list[str] = []
    copyright_tag = "SPDX-FileCopyright" + "Text: 2026 maninblack"
    license_tag = "SPDX-License-" + "Identifier: Apache-2.0"
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative in EXCLUDED_FROM_HEADER:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if copyright_tag not in text:
            errors.append(f"{relative}: missing approved SPDX copyright")
        if license_tag not in text:
            errors.append(f"{relative}: missing Apache-2.0 SPDX identifier")
    return errors


def check_binaries_and_credentials(files: list[Path]) -> list[str]:
    errors: list[str] = []
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    secret_patterns = (
        re.compile(r"(?i)(?:access|api|auth|client|refresh)[_-]?token\s*[:=]\s*['\"][^'\"]{12,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(re.escape(private_key_marker)),
    )
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in BINARY_SUFFIXES:
            errors.append(f"{relative}: prohibited binary or credential file type")
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            errors.append(f"{relative}: binary content is not permitted in the scaffold")
            continue
        text = data.decode("utf-8", errors="replace")
        if relative == "tools/quality_gate.py":
            continue
        for pattern in secret_patterns:
            if pattern.search(text):
                errors.append(f"{relative}: possible committed credential")
                break
    return errors


def check_dependencies() -> list[str]:
    inventory = json.loads((ROOT / "DEPENDENCIES.json").read_text(encoding="utf-8"))
    return validate_dependency_inventory(inventory)


def validate_dependency_inventory(inventory: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(inventory, dict):
        return ["DEPENDENCIES.json: root must be an object"]
    for scope in ("runtime", "build", "ci"):
        dependencies = inventory.get(scope)
        if not isinstance(dependencies, list):
            errors.append(f"DEPENDENCIES.json: {scope} must be an array")
            continue
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                errors.append(f"DEPENDENCIES.json: {scope} entry must be an object")
                continue
            name = dependency.get("name", "<unnamed>")
            revision = dependency.get("revision", "")
            license_expression = dependency.get("license", "")
            terms = (
                license_expression.split(" & ")
                if isinstance(license_expression, str)
                else []
            )
            if (
                not terms
                or " & ".join(terms) != license_expression
                or any(not term or term not in ALLOWED_DEPENDENCY_LICENSES for term in terms)
            ):
                errors.append(f"DEPENDENCIES.json: {name} has an unknown license")
            git_pin = isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision)
            archive = (
                revision.removeprefix("archive-sha256:")
                if isinstance(revision, str) and revision.startswith("archive-sha256:")
                else None
            )
            archive_pin = archive is not None and re.fullmatch(r"[0-9a-f]{64}", archive)
            if archive_pin and dependency.get("artifactSha256") != archive:
                errors.append(
                    f"DEPENDENCIES.json: {name} archive and artifact hashes differ"
                )
            elif not git_pin and not archive_pin:
                errors.append(f"DEPENDENCIES.json: {name} is not pinned to a commit")
    return errors


def main() -> int:
    files = tracked_files()
    errors = check_spdx(files)
    errors.extend(check_binaries_and_credentials(files))
    errors.extend(check_dependencies())
    if errors:
        print("Repository quality gate failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Repository quality gate passed for {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
