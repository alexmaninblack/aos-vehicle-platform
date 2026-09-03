# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Deterministic deployable VDP v1-v3 ARM64 candidate composition."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import vdp_family


ROOT = Path(__file__).resolve().parents[2]
CANONICAL_MANIFEST_ROOT = ROOT / "manifests/release-candidates"
CONTENT_STORE_ROOT = ROOT / ".local/release-candidates/sha256"
PRODUCT_SOURCE_REVISION = "667afb1512cf43ff27f1ab5327293208bf73045b"
PRODUCT_SOURCE_TREE = "164f907bf041dbc99df24d2ebe7b0e5d2bbaeab0"
FACTORY_VERSION = "6.1.1-maninblack.21"
FACTORY_RAW_SHA256 = "80e0c0dc4f7f9c51a25d3461047e2e3d85bf540059c7052af3944ce8650e19e1"
COMPONENT_TYPE = "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider"
LEGACY_MEDIA_TYPE = "application/vnd.aos.vehicle-data-provider.layer.v1.tar"
COMPONENT_MEDIA_TYPE = "application/vnd.aos.image.component.full.v1+gzip"
DEPLOYMENT_BUNDLE_VERSIONS = {"1.0.14", "1.0.15"}
MINIMUM_FREE_BYTES = 55 * 1024**3
WHEELHOUSE_ENVIRONMENT = "AOS_VDP_BUILD_OFFLINE"
WHEEL_DIGESTS = {
    "grpcio-1.75.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.whl":
        "36764a4ad9dc1eb891042fab51e8cdf7cc014ad82cee807c10796fb708455041",
    "kuksa_client-0.5.0-py3-none-any.whl":
        "c60404292e5ded4e0436b1c8568e9daf4981c4db94907b96f482173ed9ce2c4a",
    "protobuf-5.29.6-cp38-abi3-manylinux2014_aarch64.whl":
        "a8866b2cff111f0f863c1b3b9e7572dc7eaea23a7fae27f6fc613304046483e6",
    "typing_extensions-4.15.0-py3-none-any.whl":
        "f0fa19c6845758ab08074a0cfa8b7aecb71c999ca73d62883bc25cc018c4e548",
    "websockets-15.0.1-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl":
        "e8b56bdcdb4505c8078cb6c7157d9811a85790f2f2b3632c7d1462ab5783d215",
}
EXCLUDED_WHEEL_MEMBERS = {"grpc/_cython/_credentials/roots.pem"}
BUILDER_INPUTS = (
    "packaging/fota/build-provider-component",
    "packaging/fota/vdp_artifact.py",
    "packaging/fota/vdp_family.py",
)
SOURCE_BOUNDARY = (
    "DEPENDENCIES.json",
    "LICENSES/Apache-2.0.txt",
    "THIRD_PARTY_NOTICES.md",
    "packaging/fota/provider_main.py",
    "packaging/fota/requirements-arm64.txt",
    "packaging/fota/vehicle-data-provider",
    "providers/carla-viss-kuksa/releases",
    "providers/carla-viss-kuksa/src/carla_viss_kuksa_provider",
)
FORBIDDEN_CONTENT = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN " + b"RSA PRIVATE KEY-----",
    b"-----BEGIN " + b"EC PRIVATE KEY-----",
    b"/Users/",
    b"AKIA",
    b"api.aoscloud.io",
    b"oem.aoscloud.io",
)
CERTIFICATE_MARKER = b"-----BEGIN " + b"CERTIFICATE-----"
GRPC_EMBEDDED_PUBLIC_ROOTS = "python/site-packages/grpc/_cython/cygrpc."
FORBIDDEN_SUFFIXES = {
    ".cer", ".crt", ".csr", ".der", ".jks", ".key", ".p12", ".pem",
    ".pfx", ".pkcs12", ".token",
}
EXPECTED_PACKAGE_PREFIXES = (
    "grpcio-1.75.0.dist-info/",
    "kuksa_client-0.5.0.dist-info/",
    "protobuf-5.29.6.dist-info/",
    "typing_extensions-4.15.0.dist-info/",
    "websockets-15.0.1.dist-info/",
)


class ArtifactError(ValueError):
    """Raised when the deployable candidate boundary is violated."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    _validate_canonical_value(value)
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _validate_canonical_value(value: object) -> None:
    if isinstance(value, float):
        raise ArtifactError("canonical producer metadata must not contain floats")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ArtifactError("canonical producer metadata keys must be strings")
        for item in value.values():
            _validate_canonical_value(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _validate_canonical_value(item)
    elif value is not None and not isinstance(value, (str, int, bool)):
        raise ArtifactError("unsupported canonical producer metadata value")


def candidate_id(version: str) -> str:
    require_version(version)
    return f"aosedge-vdp-component-{version}"


def prepared_filename(version: str) -> str:
    return f"{candidate_id(version)}-linux-arm64.unsigned.tar.gz"


def manifest_filename(version: str) -> str:
    return f"{candidate_id(version)}.manifest.json"


def layer_name(version: str) -> str:
    require_version(version)
    suffix = "tar.gz" if version in DEPLOYMENT_BUNDLE_VERSIONS else "tar"
    return f"vdp-{version}-arm64.{suffix}"


def layer_media_type(version: str) -> str:
    require_version(version)
    if version in DEPLOYMENT_BUNDLE_VERSIONS:
        return COMPONENT_MEDIA_TYPE
    return LEGACY_MEDIA_TYPE


def layer_path(version: str) -> str:
    return f"vehicle-data-platform/{layer_name(version)}"


def require_version(version: str) -> None:
    if version not in vdp_family.VERSIONS:
        raise ArtifactError("unsupported VDP semantic version")


def verify_entry_gate(output: Path, wheelhouse: Path) -> list[Path]:
    if os.environ.get(WHEELHOUSE_ENVIRONMENT) != "1" or os.environ.get("PIP_NO_INDEX") != "1":
        raise ArtifactError("offline build guards are not active")
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        text=True, capture_output=True,
    ).stdout
    if status:
        raise ArtifactError("source worktree must be clean before candidate generation")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
        text=True, capture_output=True,
    ).stdout.strip()
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PRODUCT_SOURCE_REVISION, head],
        cwd=ROOT, check=False,
    )
    if ancestry.returncode != 0:
        raise ArtifactError("accepted product source revision is not an ancestor")
    tree = subprocess.run(
        ["git", "rev-parse", f"{PRODUCT_SOURCE_REVISION}^{{tree}}"], cwd=ROOT,
        check=True, text=True, capture_output=True,
    ).stdout.strip()
    if tree != PRODUCT_SOURCE_TREE:
        raise ArtifactError("accepted product source tree mismatch")
    unchanged = subprocess.run(
        ["git", "diff", "--quiet", PRODUCT_SOURCE_REVISION, "--", *SOURCE_BOUNDARY],
        cwd=ROOT, check=False,
    )
    if unchanged.returncode != 0:
        raise ArtifactError("accepted VDP runtime inputs changed after source integration")
    free_root = output.parent
    while not free_root.exists():
        if free_root.parent == free_root:
            raise ArtifactError("candidate output has no existing filesystem parent")
        free_root = free_root.parent
    if shutil.disk_usage(free_root).free < MINIMUM_FREE_BYTES:
        raise ArtifactError("VDP candidate filesystem has less than 55 GiB free")
    return validate_wheelhouse(wheelhouse)


def validate_wheelhouse(wheelhouse: Path) -> list[Path]:
    if not wheelhouse.is_dir() or wheelhouse.is_symlink():
        raise ArtifactError("local ARM64 wheelhouse is missing or unsafe")
    wheels = sorted(wheelhouse.glob("*.whl"))
    if [wheel.name for wheel in wheels] != sorted(WHEEL_DIGESTS):
        raise ArtifactError("wheelhouse file set does not match the five-file allowlist")
    for wheel in wheels:
        if wheel.is_symlink() or not wheel.is_file():
            raise ArtifactError("wheelhouse contains an unsafe file")
        if sha256_file(wheel) != WHEEL_DIGESTS[wheel.name]:
            raise ArtifactError(f"wheel digest mismatch: {wheel.name}")
    return wheels


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ArtifactError(f"unsafe archive path: {name!r}")
    return path


def extract_wheels(wheels: list[Path], destination: Path) -> None:
    observed: set[PurePosixPath] = set()
    excluded: set[str] = set()
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            for member in sorted(archive.infolist(), key=lambda item: item.filename):
                if member.filename in EXCLUDED_WHEEL_MEMBERS:
                    excluded.add(member.filename)
                    continue
                relative = _safe_member(member.filename.rstrip("/"))
                mode = (member.external_attr >> 16) & 0xFFFF
                if stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ArtifactError(f"wheel contains a link or special file: {member.filename}")
                if member.is_dir():
                    continue
                if relative in observed:
                    raise ArtifactError(f"wheel path collision: {relative}")
                observed.add(relative)
                target = destination.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
    if excluded != EXCLUDED_WHEEL_MEMBERS:
        raise ArtifactError("expected redundant gRPC public trust bundle is absent")


def _source_payload(version: str) -> dict[str, bytes]:
    archive, _ = vdp_family.compose(version, PRODUCT_SOURCE_REVISION)
    files = vdp_family._members(archive)
    files.pop("prebuild.json")
    return files


def _input_records(
    payload: dict[str, bytes], wheels: list[Path], dependency_lock: bytes
) -> list[dict[str, object]]:
    records = [
        {"byteLength": len(content), "path": f"payload/{path}", "sha256": sha256_bytes(content)}
        for path, content in sorted(payload.items())
    ]
    records.extend(
        {
            "byteLength": (ROOT / path).stat().st_size,
            "path": path,
            "sha256": sha256_file(ROOT / path),
        }
        for path in BUILDER_INPUTS
    )
    records.append(
        {
            "byteLength": len(dependency_lock),
            "path": "payload/dependency-lock/requirements-arm64.txt",
            "sha256": sha256_bytes(dependency_lock),
        }
    )
    records.extend(
        {"byteLength": wheel.stat().st_size, "path": f"wheelhouse/{wheel.name}", "sha256": sha256_file(wheel)}
        for wheel in wheels
    )
    return sorted(records, key=lambda item: str(item["path"]))


def _runtime_packages(wheels: list[Path]) -> list[dict[str, object]]:
    runtime = json.loads((ROOT / "DEPENDENCIES.json").read_text(encoding="utf-8"))["runtime"]
    by_digest = {item.get("artifactSha256"): item for item in runtime}
    packages = []
    for index, wheel in enumerate(wheels, start=1):
        digest = sha256_file(wheel)
        dependency = by_digest.get(digest)
        if dependency is None:
            raise ArtifactError(f"wheel is absent from dependency inventory: {wheel.name}")
        packages.append(
            {
                "SPDXID": f"SPDXRef-Package-{index}",
                "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
                "copyrightText": "NOASSERTION",
                "downloadLocation": dependency["source"],
                "filesAnalyzed": False,
                "licenseConcluded": dependency["license"],
                "licenseDeclared": dependency["license"],
                "name": dependency["name"],
                "versionInfo": dependency["displayVersion"],
            }
        )
    return packages


def _write_payload(root: Path, version: str, wheels: list[Path]) -> tuple[list[dict[str, object]], dict[str, object]]:
    source_payload = _source_payload(version)
    for name, content in source_payload.items():
        target = root.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    site_packages = root / "python/site-packages"
    site_packages.mkdir(parents=True)
    extract_wheels(wheels, site_packages)
    dependency_lock = (ROOT / "packaging/fota/requirements-arm64.txt").read_bytes()
    lock = root / "dependency-lock/requirements-arm64.txt"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(dependency_lock)
    inputs = _input_records(source_payload, wheels, dependency_lock)
    capability = json.loads(source_payload["config/capability-manifest.json"])
    provenance = {
        "$comment": "SPDX-FileCopyrightText: 2026 maninblack; SPDX-License-Identifier: Apache-2.0",
        "architecture": "arm64",
        "buildInputs": inputs,
        "buildType": "aosedge-vdp-reproducible-component-v1",
        "componentType": COMPONENT_TYPE,
        "factoryImageRawSha256": FACTORY_RAW_SHA256,
        "factoryImageVersion": FACTORY_VERSION,
        "os": "linux",
        "runtimeInterface": 1,
        "schemaVersion": 1,
        "semanticVersion": version,
        "sourceRevision": PRODUCT_SOURCE_REVISION,
        "sourceTree": PRODUCT_SOURCE_TREE,
        "wheelNormalization": {
            "embeddedPublicTrust": "grpcio-extension-inert-explicit-kuksa-ca-required",
            "excludedMembers": sorted(EXCLUDED_WHEEL_MEMBERS),
            "fileMode": "0644",
        },
    }
    provenance_path = root / "provenance/provenance.json"
    provenance_path.parent.mkdir(parents=True)
    provenance_path.write_bytes(canonical_json(provenance))
    sbom = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": "2026-08-30T13:03:52Z",
            "creators": ["Person: maninblack"],
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": (
            "https://github.com/alexmaninblack/aos-vehicle-platform/"
            f"sbom/vehicle-data-platform/{version}/{PRODUCT_SOURCE_REVISION}"
        ),
        "name": f"aosedge-vdp-component-{version}-linux-arm64",
        "packages": _runtime_packages(wheels),
        "spdxVersion": "SPDX-2.3",
    }
    sbom_path = root / "sbom/spdx.json"
    sbom_path.parent.mkdir(parents=True)
    sbom_path.write_bytes(canonical_json(sbom))
    for path in root.rglob("*"):
        if path.is_dir():
            path.chmod(0o755)
        elif path == root / "bin/vehicle-data-provider":
            path.chmod(0o755)
        else:
            path.chmod(0o644)
    return inputs, capability


def _populate_ustar(archive: tarfile.TarFile, root: Path) -> None:
    paths = sorted(
        root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
    )
    for path in paths:
        relative = path.relative_to(root).as_posix()
        info = tarfile.TarInfo(relative + ("/" if path.is_dir() else ""))
        info.uid = info.gid = info.mtime = 0
        info.uname = info.gname = "root"
        if path.is_dir():
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            archive.addfile(info)
        else:
            info.type = tarfile.REGTYPE
            info.mode = (
                0o755 if relative == "bin/vehicle-data-provider" else 0o644
            )
            info.size = path.stat().st_size
            with path.open("rb") as stream:
                archive.addfile(info, stream)


def _create_ustar(root: Path, output: Path) -> None:
    if output.name.endswith(".tar.gz"):
        buffer = io.BytesIO()
        with tarfile.open(
            fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive:
            _populate_ustar(archive, root)
        with output.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                compressed.write(buffer.getvalue())
        return

    with tarfile.open(output, "w", format=tarfile.USTAR_FORMAT) as archive:
        _populate_ustar(archive, root)


def envelope_configuration(version: str) -> dict[str, object]:
    item: dict[str, object] = {
        "identity": {
            "codename": COMPONENT_TYPE,
            "description": f"AosEdge Vehicle Data Platform {version}",
            "title": "Vehicle Data Platform",
            "type": "component",
        },
        "images": [
            {
                "archInfo": {"architecture": "arm64"},
                "mediaType": layer_media_type(version),
                "osInfo": {"os": "linux"},
                "path": layer_name(version),
            }
        ],
        "sourceFolder": "vehicle-data-platform",
        "version": version,
    }
    if version in DEPLOYMENT_BUNDLE_VERSIONS:
        item["configuration"] = {
            "runtimes": [{"codename": COMPONENT_TYPE, "type": "runtime"}]
        }

    return {
        "$comment": "SPDX-FileCopyrightText: 2026 maninblack; SPDX-License-Identifier: Apache-2.0",
        "items": [item],
        "publisher": {"author": "maninblack"},
        "schemaVersion": 2,
    }


def _create_envelope(version: str, layer: Path, output: Path) -> bytes:
    config = canonical_json(envelope_configuration(version))
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in (("config.yaml", config), (layer_path(version), layer.read_bytes())):
            info = tarfile.TarInfo(name)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = "root"
            info.mode = 0o644
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    with output.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
            compressed.write(buffer.getvalue())
    return config


def _contract_delta(version: str, capability: dict[str, object]) -> dict[str, object]:
    predecessor = {
        "1.0.0": None,
        "1.0.14": "1.0.0",
        "1.0.15": "1.0.14",
        "2.0.0": "1.0.15",
        "3.0.0": "2.0.0",
    }[version]
    prior_paths: set[str] = set()
    prior_capabilities: set[str] = set()
    if predecessor is not None:
        prior = json.loads(
            (ROOT / f"providers/carla-viss-kuksa/releases/{predecessor}/capability-manifest.json")
            .read_text(encoding="utf-8")
        )
        prior_paths = set(prior["readPaths"])
        prior_capabilities = set(prior["capabilities"])
    added_capabilities = sorted(set(capability["capabilities"]) - prior_capabilities)
    added_paths = sorted(set(capability["readPaths"]) - prior_paths)
    return {
        "addedCapabilities": added_capabilities,
        "addedReadPaths": added_paths,
        "advisoryEndpointIds": sorted(item["id"] for item in capability["advisoryEndpoints"]),
        "predecessor": predecessor,
        "strictAdditiveSuperset": bool(added_capabilities or added_paths),
        "versionOnlySuccessor": (
            predecessor is not None and not added_capabilities and not added_paths
        ),
    }


def producer_manifest(
    version: str,
    artifact: Path,
    layer: Path,
    inputs: list[dict[str, object]],
    capability: dict[str, object],
    provenance_sha256: str,
    sbom_sha256: str,
) -> dict[str, object]:
    return {
        "$comment": "SPDX-FileCopyrightText: 2026 maninblack; SPDX-License-Identifier: Apache-2.0",
        "artifactKind": "AOS_COMPONENT_FOTA_UNSIGNED",
        "buildInputs": inputs,
        "candidateId": candidate_id(version),
        "compatibility": {
            "componentRuntime": "systemd-slot-component",
            "componentType": COMPONENT_TYPE,
            "factoryImageRawSha256": FACTORY_RAW_SHA256,
            "factoryImageVersion": FACTORY_VERSION,
            "providerSlotAtFactory": "EMPTY",
            "runtimeInterface": 1,
        },
        "contractDelta": _contract_delta(version, capability),
        "functionalOutputs": {
            "advisoryEndpoints": capability["advisoryEndpoints"],
            "kuksaPublishedPaths": capability["readPaths"],
        },
        "licenses": {
            "concluded": ["Apache-2.0", "BSD-3-Clause", "PSF-2.0"],
            "noticePath": "THIRD_PARTY_NOTICES.md",
            "spdxLicensePath": "licenses/Apache-2.0.txt",
        },
        "permissions": {
            "dynamicProviderAuthorization": False,
            "linuxCapabilities": [],
            "providerAuthority": "TRUSTED_OEM_PLATFORM_INTEGRATION",
            "serviceCredentialReuse": False,
        },
        "preparedArtifact": {
            "byteLength": artifact.stat().st_size,
            "fileName": prepared_filename(version),
            "sha256": sha256_file(artifact),
        },
        "product": {"componentId": "vehicle-data-platform", "name": "AosEdge Vehicle Data Platform"},
        "provenance": {"path": "provenance/provenance.json", "sha256": provenance_sha256},
        "qualificationEvidence": [
            *[f"UT-VDP-{index:03d}" for index in range(1, 9)],
            "OFFLINE_DETERMINISTIC_DOUBLE_BUILD",
            "LIVE_VISS_KUKSA_AB_QUALIFICATION_DEFERRED",
        ],
        "resourceEnvelope": {
            "applicationStateStore": False,
            "cpuQuota": None,
            "logStore": False,
            "memoryQuotaBytes": None,
            "telemetryPersistence": False,
        },
        "sbom": {"format": "SPDX-2.3", "path": "sbom/spdx.json", "sha256": sbom_sha256},
        "schemaVersion": 1,
        "semanticVersion": version,
        "signingState": "UNSIGNED",
        "source": {
            "repository": "aos-vehicle-platform",
            "revision": PRODUCT_SOURCE_REVISION,
            "tree": PRODUCT_SOURCE_TREE,
        },
        "target": {"architecture": "arm64", "os": "linux"},
        "transport": {
            "layer": {
                "byteLength": layer.stat().st_size,
                "mediaType": layer_media_type(version),
                "path": layer_path(version),
                "sha256": sha256_file(layer),
            }
        },
    }


def build(output: Path, version: str, wheelhouse: Path) -> None:
    require_version(version)
    if output.exists() or output.is_symlink():
        raise ArtifactError(f"output already exists: {output}")
    wheels = verify_entry_gate(output, wheelhouse)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        temporary_root = Path(temporary)
        payload = temporary_root / "payload"
        payload.mkdir()
        inputs, capability = _write_payload(payload, version, wheels)
        candidate = temporary_root / "candidate"
        candidate.mkdir()
        layer = candidate / layer_name(version)
        _create_ustar(payload, layer)
        artifact = candidate / prepared_filename(version)
        config = _create_envelope(version, layer, artifact)
        layer_members = _member_map(layer)
        provenance_sha = sha256_bytes(layer_members["provenance/provenance.json"][1])
        sbom_sha = sha256_bytes(layer_members["sbom/spdx.json"][1])
        manifest = producer_manifest(
            version, artifact, layer, inputs, capability, provenance_sha, sbom_sha
        )
        (candidate / manifest_filename(version)).write_bytes(canonical_json(manifest))
        summary = {
            "$comment": "SPDX-FileCopyrightText: 2026 maninblack; SPDX-License-Identifier: Apache-2.0",
            "artifact": manifest["preparedArtifact"],
            "configSha256": sha256_bytes(config),
            "layer": manifest["transport"]["layer"],
            "manifest": {
                "byteLength": len(canonical_json(manifest)),
                "fileName": manifest_filename(version),
                "sha256": sha256_bytes(canonical_json(manifest)),
            },
            "schemaVersion": 1,
        }
        (candidate / "candidate.json").write_bytes(canonical_json(summary))
        validate(candidate, version, candidate / manifest_filename(version))
        os.replace(candidate, output)


def _member_map(path: Path, mode: str = "r:*") -> dict[str, tuple[tarfile.TarInfo, bytes]]:
    observed: dict[str, tuple[tarfile.TarInfo, bytes]] = {}
    with tarfile.open(path, mode) as archive:
        for member in archive:
            name = member.name.rstrip("/")
            _safe_member(name)
            if name in observed or not (member.isfile() or member.isdir()):
                raise ArtifactError(f"unsafe or duplicate archive member: {name}")
            content = b""
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise ArtifactError(f"archive member cannot be read: {name}")
                content = stream.read()
            observed[name] = member, content
    return observed


def _validate_archive_metadata(
    members: dict[str, tuple[tarfile.TarInfo, bytes]], *, scan_content: bool = True
) -> None:
    for name, (member, content) in members.items():
        if member.uid != 0 or member.gid != 0 or member.mtime != 0:
            raise ArtifactError(f"non-deterministic archive metadata: {name}")
        mode = stat.S_IMODE(member.mode)
        expected = 0o755 if member.isdir() or name == "bin/vehicle-data-provider" else 0o644
        if mode != expected:
            raise ArtifactError(f"unsafe archive mode: {name}")
        if member.isfile() and scan_content:
            if PurePosixPath(name).suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ArtifactError(f"credential or certificate file in payload: {name}")
            if any(marker in content for marker in FORBIDDEN_CONTENT):
                raise ArtifactError(f"forbidden content in payload: {name}")
            if CERTIFICATE_MARKER in content and not name.startswith(
                GRPC_EMBEDDED_PUBLIC_ROOTS
            ):
                raise ArtifactError(f"certificate material in payload: {name}")
            if content.startswith(b"\x7fELF"):
                if len(content) < 20 or content[4] != 2 or content[5] != 1:
                    raise ArtifactError(f"ELF ABI mismatch: {name}")
                if int.from_bytes(content[18:20], "little") != 183:
                    raise ArtifactError(f"ELF is not AArch64: {name}")


def _canonical_document(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or path.read_bytes() != canonical_json(value):
        raise ArtifactError(f"metadata is not canonical RFC8785 JSON: {path.name}")
    return value


def _validate_manifest_strings(value: object) -> None:
    if isinstance(value, str):
        if value.startswith("/") or "latest" in value.lower() or re.search(r"[A-Za-z]:\\", value):
            raise ArtifactError("producer manifest contains a local path or mutable identity")
    elif isinstance(value, dict):
        for item in value.values():
            _validate_manifest_strings(item)
    elif isinstance(value, list):
        for item in value:
            _validate_manifest_strings(item)


def validate(root: Path, version: str, manifest_path: Path) -> dict[str, object]:
    require_version(version)
    if not root.is_dir() or root.is_symlink():
        raise ArtifactError("VDP candidate root is missing or unsafe")
    artifact = root / prepared_filename(version)
    layer = root / layer_name(version)
    summary_path = root / "candidate.json"
    for path in (artifact, layer, summary_path, manifest_path):
        if not path.is_file() or path.is_symlink():
            raise ArtifactError(f"candidate file is missing or unsafe: {path.name}")
    manifest = _canonical_document(manifest_path)
    _validate_manifest_strings(manifest)
    summary = _canonical_document(summary_path)
    try:
        with gzip.open(artifact, "rb") as stream:
            envelope_bytes = stream.read()
    except OSError as error:
        raise ArtifactError("prepared artifact compression is invalid") from error
    envelope = _member_map_bytes(envelope_bytes)
    if set(envelope) != {"config.yaml", layer_path(version)}:
        raise ArtifactError("unsigned envelope layout mismatch")
    # The nested layer is validated member-by-member below. Do not apply a
    # byte-substring policy to its complete tar representation here.
    _validate_archive_metadata(envelope, scan_content=False)
    if envelope["config.yaml"][1] != canonical_json(envelope_configuration(version)):
        raise ArtifactError("unsigned envelope configuration mismatch")
    if envelope[layer_path(version)][1] != layer.read_bytes():
        raise ArtifactError("unsigned envelope layer differs from candidate layer")
    members = _member_map(layer)
    _validate_archive_metadata(members)
    required = {
        "bin/vehicle-data-provider", "component.json", "config/capability-manifest.json",
        "config/provider.json", "DEPENDENCIES.json", "THIRD_PARTY_NOTICES.md",
        "licenses/Apache-2.0.txt", "dependency-lock/requirements-arm64.txt",
        "provenance/provenance.json", "sbom/spdx.json", "python/provider_main.py",
        "python/carla_viss_kuksa_provider/vdp_release_profile.py",
    }
    if not required.issubset(members) or "prebuild.json" in members:
        raise ArtifactError("deployable layer layout is incomplete or contains prebuild metadata")
    release_modules = {
        name for name in members
        if name.startswith("python/carla_viss_kuksa_provider/releases/v")
    }
    expected_release = {
        "python/carla_viss_kuksa_provider/releases/" + vdp_family.PROFILE_MODULE[version]
    }
    if release_modules != expected_release:
        raise ArtifactError("deployable layer contains another VDP release profile")
    advisory = "python/carla_viss_kuksa_provider/advisory.py"
    if (advisory in members) != (version == "3.0.0"):
        raise ArtifactError("advisory implementation does not match the selected release")
    for prefix in EXPECTED_PACKAGE_PREFIXES:
        if not any(name.startswith(f"python/site-packages/{prefix}") for name in members):
            raise ArtifactError(f"runtime package is missing: {prefix}")
    component = json.loads(members["component.json"][1])
    capability = json.loads(members["config/capability-manifest.json"][1])
    provider = json.loads(members["config/provider.json"][1])
    accepted_capability = (
        ROOT / f"providers/carla-viss-kuksa/releases/{version}/capability-manifest.json"
    ).read_bytes()
    accepted_provider = (
        ROOT / f"providers/carla-viss-kuksa/releases/{version}/provider.json"
    ).read_bytes()
    if members["config/capability-manifest.json"][1] != accepted_capability:
        raise ArtifactError("accepted capability manifest bytes changed")
    if members["config/provider.json"][1] != accepted_provider:
        raise ArtifactError("accepted provider profile bytes changed")
    capability_sha = sha256_bytes(accepted_capability)
    if (
        component.get("semanticVersion") != version
        or component.get("architecture") != "arm64"
        or component.get("componentType") != COMPONENT_TYPE
        or component.get("capabilityManifestSha256") != capability_sha
        or provider.get("capabilityManifestSha256") != capability_sha
        or capability.get("semanticVersion") != version
    ):
        raise ArtifactError("VDP component identity or manifest binding mismatch")
    provenance = json.loads(members["provenance/provenance.json"][1])
    sbom = json.loads(members["sbom/spdx.json"][1])
    if (
        provenance.get("sourceRevision") != PRODUCT_SOURCE_REVISION
        or provenance.get("sourceTree") != PRODUCT_SOURCE_TREE
        or provenance.get("factoryImageVersion") != FACTORY_VERSION
        or provenance.get("factoryImageRawSha256") != FACTORY_RAW_SHA256
        or provenance.get("semanticVersion") != version
    ):
        raise ArtifactError("artifact provenance binding mismatch")
    dependency_lock = members["dependency-lock/requirements-arm64.txt"][1]
    accepted_dependency_lock = (
        ROOT / "packaging/fota/requirements-arm64.txt"
    ).read_bytes()
    if dependency_lock != accepted_dependency_lock:
        raise ArtifactError("embedded ARM64 dependency lock differs from accepted bytes")
    lock_records = [
        record
        for record in provenance.get("buildInputs", [])
        if isinstance(record, dict)
        and record.get("path") == "payload/dependency-lock/requirements-arm64.txt"
    ]
    expected_lock_record = {
        "byteLength": len(dependency_lock),
        "path": "payload/dependency-lock/requirements-arm64.txt",
        "sha256": sha256_bytes(dependency_lock),
    }
    if lock_records != [expected_lock_record]:
        raise ArtifactError("embedded ARM64 dependency lock provenance is incomplete")
    if sbom.get("spdxVersion") != "SPDX-2.3" or len(sbom.get("packages", [])) != 5:
        raise ArtifactError("artifact SBOM package inventory mismatch")
    expected_manifest = producer_manifest(
        version, artifact, layer, provenance["buildInputs"], capability,
        sha256_bytes(members["provenance/provenance.json"][1]),
        sha256_bytes(members["sbom/spdx.json"][1]),
    )
    if manifest != expected_manifest:
        raise ArtifactError("producer manifest does not bind the exact candidate")
    manifest_bytes = canonical_json(manifest)
    expected_summary = {
        "$comment": "SPDX-FileCopyrightText: 2026 maninblack; SPDX-License-Identifier: Apache-2.0",
        "artifact": manifest["preparedArtifact"],
        "configSha256": sha256_bytes(envelope["config.yaml"][1]),
        "layer": manifest["transport"]["layer"],
        "manifest": {
            "byteLength": len(manifest_bytes),
            "fileName": manifest_filename(version),
            "sha256": sha256_bytes(manifest_bytes),
        },
        "schemaVersion": 1,
    }
    if summary != expected_summary:
        raise ArtifactError("candidate summary mismatch")
    return manifest


def _member_map_bytes(value: bytes) -> dict[str, tuple[tarfile.TarInfo, bytes]]:
    observed: dict[str, tuple[tarfile.TarInfo, bytes]] = {}
    with tarfile.open(fileobj=io.BytesIO(value), mode="r:") as archive:
        for member in archive:
            name = member.name.rstrip("/")
            _safe_member(name)
            if name in observed or not (member.isfile() or member.isdir()):
                raise ArtifactError(f"unsafe or duplicate archive member: {name}")
            content = b""
            if member.isfile():
                stream = archive.extractfile(member)
                if stream is None:
                    raise ArtifactError(f"archive member cannot be read: {name}")
                content = stream.read()
            observed[name] = member, content
    return observed


def validate_family(manifests: dict[str, dict[str, object]]) -> None:
    if set(manifests) != set(vdp_family.VERSIONS):
        raise ArtifactError("exactly the VDP v1-v3 manifest family is required")
    paths = {
        version: set(manifest["functionalOutputs"]["kuksaPublishedPaths"])
        for version, manifest in manifests.items()
    }
    if not paths["1.0.0"] == paths["1.0.14"] == paths["1.0.15"]:
        raise ArtifactError("VDP v1 patch releases changed functional paths")
    if not paths["1.0.15"] < paths["2.0.0"] < paths["3.0.0"]:
        raise ArtifactError("VDP read-path family is not a strict additive superset")
    for version in ("1.0.0", "1.0.14", "1.0.15"):
        if manifests[version]["functionalOutputs"]["advisoryEndpoints"]:
            raise ArtifactError("VDP v1 exposes an advisory endpoint")
    if manifests["2.0.0"]["functionalOutputs"]["advisoryEndpoints"]:
        raise ArtifactError("VDP v2 exposes an advisory endpoint")
    if len(manifests["3.0.0"]["functionalOutputs"]["advisoryEndpoints"]) != 2:
        raise ArtifactError("VDP v3 advisory endpoint inventory mismatch")


def stage(root: Path, version: str, manifest_path: Path) -> Path:
    manifest = validate(root, version, manifest_path)
    canonical_manifest = CANONICAL_MANIFEST_ROOT / manifest_filename(version)
    if not canonical_manifest.is_file() or canonical_manifest.is_symlink():
        raise ArtifactError("version-controlled producer manifest is missing or unsafe")
    if manifest_path.read_bytes() != canonical_manifest.read_bytes():
        raise ArtifactError(
            "producer manifest bytes differ from the version-controlled canonical manifest"
        )
    digest = manifest["preparedArtifact"]["sha256"]
    store = CONTENT_STORE_ROOT / digest
    if store.exists() or store.is_symlink():
        if not store.is_dir() or store.is_symlink():
            raise ArtifactError("content-addressed stage target is unsafe")
        expected = {prepared_filename(version), manifest_filename(version)}
        if {path.name for path in store.iterdir()} != expected:
            raise ArtifactError("existing content-addressed candidate is not exact")
        if sha256_file(store / prepared_filename(version)) != digest:
            raise ArtifactError("existing staged artifact digest mismatch")
        if (store / manifest_filename(version)).read_bytes() != manifest_path.read_bytes():
            raise ArtifactError("existing staged producer manifest mismatch")
        return store
    store.parent.mkdir(parents=True, exist_ok=True)
    temporary = store.with_name(store.name + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise ArtifactError("staging partial target already exists")
    temporary.mkdir()
    shutil.copyfile(root / prepared_filename(version), temporary / prepared_filename(version))
    shutil.copyfile(canonical_manifest, temporary / manifest_filename(version))
    os.replace(temporary, store)
    return store
