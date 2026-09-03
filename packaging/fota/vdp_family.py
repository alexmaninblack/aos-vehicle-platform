# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Deterministic source-only prebuild composition for VDP 1.0.0-3.0.0."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
COMPONENT_TYPE = "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider"
VERSIONS = ("1.0.0", "1.0.14", "1.0.15", "2.0.0", "3.0.0")
PROFILE_MODULE = {
    "1.0.0": "v1.py",
    "1.0.14": "v1_0_14.py",
    "1.0.15": "v1_0_15.py",
    "2.0.0": "v2.py",
    "3.0.0": "v3.py",
}
COMMON_PROVIDER_MODULES = (
    "bridge.py",
    "manifest.py",
    "readiness.py",
    "runtime.py",
)
FORBIDDEN = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN " + b"RSA PRIVATE KEY-----",
    b"-----BEGIN " + b"EC PRIVATE KEY-----",
    b"AOS" + b"_SECRET",
    b'"publish"',
)


class PrebuildError(ValueError):
    """Raised when source inputs cannot produce the exact immutable profile."""


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def compose(version: str, source_revision: str) -> tuple[bytes, dict[str, object]]:
    if version not in VERSIONS:
        raise PrebuildError("unsupported VDP semantic version")
    if len(source_revision) != 40 or any(
        character not in "0123456789abcdef" for character in source_revision
    ):
        raise PrebuildError("source revision must be a full Git object ID")
    package = ROOT / "providers/carla-viss-kuksa/src/carla_viss_kuksa_provider"
    release = ROOT / f"providers/carla-viss-kuksa/releases/{version}"
    files: dict[str, bytes] = {
        "bin/vehicle-data-provider": (
            ROOT / "packaging/fota/vehicle-data-provider"
        ).read_bytes(),
        "config/capability-manifest.json": (
            release / "capability-manifest.json"
        ).read_bytes(),
        "config/provider.json": (release / "provider.json").read_bytes(),
        "DEPENDENCIES.json": (ROOT / "DEPENDENCIES.json").read_bytes(),
        "THIRD_PARTY_NOTICES.md": (ROOT / "THIRD_PARTY_NOTICES.md").read_bytes(),
        "licenses/Apache-2.0.txt": (ROOT / "LICENSES/Apache-2.0.txt").read_bytes(),
        "python/provider_main.py": (
            ROOT / "packaging/fota/provider_main.py"
        ).read_bytes(),
        "python/carla_viss_kuksa_provider/__init__.py": (
            "# SPDX-FileCopyrightText: 2026 maninblack\n"
            "# SPDX-License-Identifier: Apache-2.0\n\n"
            f'__version__ = "{version}"\n'
        ).encode(),
        "python/carla_viss_kuksa_provider/__main__.py": (
            package / "__main__.py"
        ).read_bytes(),
        "python/carla_viss_kuksa_provider/releases/__init__.py": (
            package / "releases/__init__.py"
        ).read_bytes(),
        (
            "python/carla_viss_kuksa_provider/releases/"
            + PROFILE_MODULE[version]
        ): (package / "releases" / PROFILE_MODULE[version]).read_bytes(),
        "python/carla_viss_kuksa_provider/vdp_release_profile.py": (
            "# SPDX-FileCopyrightText: 2026 maninblack\n"
            "# SPDX-License-Identifier: Apache-2.0\n\n"
            f"from .releases.{PROFILE_MODULE[version][:-3]} import *  # noqa: F401,F403\n"
        ).encode(),
    }
    for module in COMMON_PROVIDER_MODULES:
        files[f"python/carla_viss_kuksa_provider/{module}"] = (
            package / module
        ).read_bytes()
    if version == "3.0.0":
        files["python/carla_viss_kuksa_provider/advisory.py"] = (
            package / "advisory.py"
        ).read_bytes()

    manifest_sha = sha256_bytes(files["config/capability-manifest.json"])
    files["component.json"] = canonical_json(
        {
            "architecture": "arm64",
            "capabilityManifest": "config/capability-manifest.json",
            "capabilityManifestSha256": manifest_sha,
            "component": "vehicle-data-platform",
            "componentType": COMPONENT_TYPE,
            "configuration": "config/provider.json",
            "entrypoint": "bin/vehicle-data-provider",
            "os": "linux",
            "runtimeInterface": 1,
            "schemaVersion": 2,
            "semanticVersion": version,
        }
    )
    source_files = [
        {"path": path, "sha256": sha256_bytes(content)}
        for path, content in sorted(files.items())
    ]
    prebuild = {
        "$comment": (
            "SPDX-FileCopyrightText: 2026 maninblack; "
            "SPDX-License-Identifier: Apache-2.0"
        ),
        "architecture": "arm64",
        "capabilityManifestSha256": manifest_sha,
        "componentType": COMPONENT_TYPE,
        "dependencyLockSha256": sha256_file(
            ROOT / "packaging/fota/requirements-arm64.txt"
        ),
        "kind": "vdp-source-prebuild-v1",
        "notDeployable": True,
        "runtimeInterface": 1,
        "schemaVersion": 1,
        "semanticVersion": version,
        "sourceFiles": source_files,
        "sourceRevision": source_revision,
    }
    files["prebuild.json"] = canonical_json(prebuild)
    archive = _ustar(files)
    validate_bytes(archive, version, source_revision)
    return archive, prebuild


def prepare(output: Path, version: str, source_revision: str) -> None:
    if output.exists() or output.is_symlink():
        raise PrebuildError(f"output already exists: {output}")
    archive, prebuild = compose(version, source_revision)
    temporary = output.with_name(output.name + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise PrebuildError(f"temporary output already exists: {temporary}")
    temporary.mkdir(parents=True)
    (temporary / "source-prebuild.tar").write_bytes(archive)
    summary = dict(prebuild)
    summary["sourcePrebuildSha256"] = sha256_bytes(archive)
    (temporary / "prebuild.json").write_bytes(canonical_json(summary))
    os.replace(temporary, output)


def validate_directory(output: Path, version: str) -> None:
    if not output.is_dir() or output.is_symlink():
        raise PrebuildError("source prebuild root is unsafe")
    archive = output / "source-prebuild.tar"
    summary_path = output / "prebuild.json"
    if not archive.is_file() or archive.is_symlink():
        raise PrebuildError("source prebuild archive is missing")
    if not summary_path.is_file() or summary_path.is_symlink():
        raise PrebuildError("source prebuild summary is missing")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("sourcePrebuildSha256") != sha256_file(archive):
        raise PrebuildError("source prebuild archive digest mismatch")
    revision = summary.get("sourceRevision")
    if not isinstance(revision, str):
        raise PrebuildError("source revision is missing")
    validate_bytes(archive.read_bytes(), version, revision)


def validate_bytes(archive: bytes, version: str, source_revision: str) -> None:
    files = _members(archive)
    required = {
        "bin/vehicle-data-provider",
        "component.json",
        "config/capability-manifest.json",
        "config/provider.json",
        "DEPENDENCIES.json",
        "THIRD_PARTY_NOTICES.md",
        "licenses/Apache-2.0.txt",
        "prebuild.json",
        "python/provider_main.py",
        "python/carla_viss_kuksa_provider/__init__.py",
        "python/carla_viss_kuksa_provider/__main__.py",
        "python/carla_viss_kuksa_provider/bridge.py",
        "python/carla_viss_kuksa_provider/manifest.py",
        "python/carla_viss_kuksa_provider/readiness.py",
        "python/carla_viss_kuksa_provider/runtime.py",
        "python/carla_viss_kuksa_provider/vdp_release_profile.py",
    }
    if not required.issubset(files):
        raise PrebuildError("source prebuild layout is incomplete")
    release_modules = {
        name for name in files if name.startswith("python/carla_viss_kuksa_provider/releases/v")
    }
    expected_release = {
        "python/carla_viss_kuksa_provider/releases/" + PROFILE_MODULE[version]
    }
    if release_modules != expected_release:
        raise PrebuildError("source prebuild contains another release profile")
    advisory = "python/carla_viss_kuksa_provider/advisory.py"
    if (advisory in files) != (version == "3.0.0"):
        raise PrebuildError("source prebuild advisory module does not match release")
    for name, content in files.items():
        if any(marker in content for marker in FORBIDDEN):
            raise PrebuildError(f"forbidden payload data: {name}")
    component = json.loads(files["component.json"])
    manifest = json.loads(files["config/capability-manifest.json"])
    config = json.loads(files["config/provider.json"])
    prebuild = json.loads(files["prebuild.json"])
    manifest_sha = sha256_bytes(files["config/capability-manifest.json"])
    if (
        component.get("architecture") != "arm64"
        or component.get("componentType") != COMPONENT_TYPE
        or component.get("runtimeInterface") != 1
        or component.get("schemaVersion") != 2
    ):
        raise PrebuildError("component target identity mismatch")
    if (
        prebuild.get("architecture") != "arm64"
        or prebuild.get("componentType") != COMPONENT_TYPE
        or prebuild.get("runtimeInterface") != 1
        or prebuild.get("kind") != "vdp-source-prebuild-v1"
    ):
        raise PrebuildError("source prebuild target identity mismatch")
    if manifest.get("componentType") != COMPONENT_TYPE:
        raise PrebuildError("capability manifest target identity mismatch")
    if component.get("semanticVersion") != version or manifest.get("semanticVersion") != version:
        raise PrebuildError("semantic version mismatch")
    if config.get("semanticVersion") != version:
        raise PrebuildError("provider configuration version mismatch")
    if component.get("capabilityManifestSha256") != manifest_sha:
        raise PrebuildError("component manifest digest mismatch")
    if config.get("capabilityManifestSha256") != manifest_sha:
        raise PrebuildError("provider manifest digest mismatch")
    if prebuild.get("sourceRevision") != source_revision:
        raise PrebuildError("prebuild source revision mismatch")
    if prebuild.get("notDeployable") is not True:
        raise PrebuildError("source prebuild must remain non-deployable")
    expected_source_files = [
        {"path": path, "sha256": sha256_bytes(content)}
        for path, content in sorted(files.items())
        if path != "prebuild.json"
    ]
    if prebuild.get("sourceFiles") != expected_source_files:
        raise PrebuildError("source prebuild input inventory mismatch")


def _ustar(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        directories: set[str] = set()
        for name in files:
            parent = PurePosixPath(name).parent
            while str(parent) != ".":
                directories.add(parent.as_posix())
                parent = parent.parent
        for name in sorted(directories):
            info = tarfile.TarInfo(name + "/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = "root"
            archive.addfile(info)
        for name, content in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.mode = 0o755 if name == "bin/vehicle-data-provider" else 0o644
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = "root"
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def _members(archive_bytes: bytes) -> dict[str, bytes]:
    observed: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            path = PurePosixPath(name)
            if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise PrebuildError("source prebuild contains an unsafe path")
            if member.isdir():
                continue
            if not member.isfile() or name in observed:
                raise PrebuildError("source prebuild contains an unsafe member")
            stream = archive.extractfile(member)
            if stream is None:
                raise PrebuildError("source prebuild member cannot be read")
            observed[name] = stream.read()
    return observed
