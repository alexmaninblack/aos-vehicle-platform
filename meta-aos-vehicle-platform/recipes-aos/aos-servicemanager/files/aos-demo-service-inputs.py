# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: MIT

"""Fixed engineering projection of public inputs; not a container launcher."""

import hashlib
import json
import os
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STORE = Path("/var/aos/workdirs/sm/runtimes/systemd-slot-component")
PUBLIC = Path("/run/aos-demo-service-inputs")
CERTIFICATE = Path("/var/lib/aos-kuksa-tls/server.pem")
OWNER = 0
FILESYSTEM_ROOT = Path("/")
IAM_CONFIG = Path("/etc/aos/iam.cfg")
MACHINE_ID = Path("/etc/machine-id")
STARTUP = Path("/run/democtl-service-inputs")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def safe_path(path):
    if not path.is_relative_to(FILESYSTEM_ROOT):
        raise ValueError("SERVICE_INPUT_PATH_OUTSIDE_ROOT")
    for part in (path,) + tuple(path.parents):
        if part.is_symlink():
            raise ValueError("SERVICE_INPUT_SYMLINK")
        if part.exists():
            info = part.stat()
            if info.st_uid != OWNER or info.st_mode & 0o022:
                raise ValueError("SERVICE_INPUT_OWNER_OR_MODE")
        if part == FILESYSTEM_ROOT:
            break


def read_public(path, limit=1048576):
    safe_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise ValueError("SERVICE_INPUT_FILE_UNSAFE")
    return path.read_bytes()


def read_document(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("SERVICE_INPUT_DUPLICATE_FIELD")
            result[key] = value
        return result
    value = json.loads(read_public(path), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("SERVICE_INPUT_OBJECT_REQUIRED")
    return value


def provider_process():
    result = subprocess.run(["systemctl", "show", "aos-vehicle-data-provider",
        "--property=MainPID,ActiveState,Result,ExecMainStatus"], capture_output=True, text=True, timeout=5, check=True)
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    pid = values.get("MainPID", "0")
    if (values.get("ActiveState") != "active" or values.get("Result") != "success"
            or values.get("ExecMainStatus") != "0" or not pid.isdigit() or int(pid) <= 0):
        raise ValueError("SERVICE_INPUT_PROVIDER_NOT_RUNNING")
    return pid, (Path("/proc") / pid / "cmdline").read_bytes().split(b"\0")


def native_identity():
    identifier = read_document(IAM_CONFIG).get("identifier", {})
    if (identifier.get("plugin") != "fileidentifier"
            or identifier.get("params", {}).get("systemIDPath") != str(MACHINE_ID)):
        raise ValueError("SERVICE_INPUT_NATIVE_IDENTIFIER_UNSUPPORTED")
    uid = read_public(MACHINE_ID, 256).decode("ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", uid):
        raise ValueError("SERVICE_INPUT_NATIVE_IDENTITY_INVALID")
    return uid


def snapshot(request, *, require_process=True):
    uid = request.get("nativeSystemUid")
    if (request.get("role") != "test" or not isinstance(uid, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", uid)
            or uid != request.get("vehicle", {}).get("systemUid")):
        raise ValueError("SERVICE_INPUT_NATIVE_IDENTITY_MISMATCH")
    if read_public(STORE / "demo-inputs/role", 16) != b"test\n":
        raise ValueError("SERVICE_INPUT_ROLE_MISMATCH")
    transaction = STORE / "state/transaction.json"
    if transaction.exists() or transaction.is_symlink():
        raise ValueError("SERVICE_INPUT_COMPONENT_TRANSACTION_ACTIVE")
    installed = read_document(STORE / "state/installed.json")
    if installed.get("schemaVersion") != 1 or installed.get("slot") not in ("a", "b"):
        raise ValueError("SERVICE_INPUT_COMMIT_INVALID")
    active = STORE / "active"
    if not active.is_symlink() or os.readlink(active) != "slots/" + installed["slot"]:
        raise ValueError("SERVICE_INPUT_ACTIVE_COMMIT_MISMATCH")
    slot = STORE / "slots" / installed["slot"]
    slot_record = read_document(slot / ".aos-instance.json")
    for field in ("schemaVersion", "slot", "Version", "ManifestDigest", "ItemId", "SubjectId", "Instance", "RuntimeId", "Preinstalled"):
        if field not in installed or slot_record.get(field) != installed[field]:
            raise ValueError("SERVICE_INPUT_SLOT_RECORD_MISMATCH")
    metadata = read_document(slot / "component.json")
    provider = read_document(slot / "config/provider.json")
    capability_path = slot / "config/capability-manifest.json"
    capability = read_document(capability_path)
    version = installed["Version"]
    if (not isinstance(version, str) or len(version) > 32 or not VERSION.fullmatch(version)
            or metadata.get("version") != version or provider.get("semanticVersion") != version
            or capability.get("semanticVersion") != version
            or provider.get("capabilityManifestSha256") != hashlib.sha256(read_public(capability_path)).hexdigest()):
        raise ValueError("SERVICE_INPUT_CAPABILITY_MISMATCH")
    compatibility = capability.get("contracts", {}).get("vdpCompatibility", {})
    contract_version, contract_sha = compatibility.get("contractVersion"), compatibility.get("sha256")
    if (compatibility.get("contractId") != "aosedge-demo-vdp-compatibility"
            or not isinstance(contract_version, str) or len(contract_version) > 32
            or not VERSION.fullmatch(contract_version) or not isinstance(contract_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", contract_sha)):
        raise ValueError("SERVICE_INPUT_VDP_CONTRACT_INVALID")
    pid = None
    if require_process:
        pid, argv = provider_process()
        if not any(argv[i:i + 2] == [b"--config", str(slot / "config/provider.json").encode()] for i in range(len(argv))):
            raise ValueError("SERVICE_INPUT_PROCESS_SLOT_MISMATCH")
    public = dict(schemaVersion=2, unitSystemUid=uid, unitRole="validation",
        vdpContractVersion=contract_version, vdpContractSha256=contract_sha)
    return dict(metadata=public, installed=installed, pid=pid, capability=provider["capabilityManifestSha256"])


def trust():
    raw = read_public(CERTIFICATE, 32768)
    if (raw.count(b"-----BEGIN CERTIFICATE-----") != 1 or b"PRIVATE KEY" in raw
            or not raw.strip().endswith(b"-----END CERTIFICATE-----")):
        raise ValueError("SERVICE_INPUT_PUBLIC_CERTIFICATE_REQUIRED")
    ssl.create_default_context(cadata=raw.decode("ascii"))
    checked = subprocess.run(["openssl", "x509", "-in", str(CERTIFICATE), "-noout", "-checkhost", "Server"],
        capture_output=True, timeout=5)
    if checked.returncode or checked.stdout.strip() != b"Hostname Server does match certificate":
        raise ValueError("SERVICE_INPUT_CERTIFICATE_HOST_MISMATCH")
    return raw


def project(request, *, cold=False):
    def observe():
        return snapshot(request, require_process=not cold)
    before = observe()
    certificate = trust()
    metadata = (json.dumps(before["metadata"], sort_keys=True, indent=2) + "\n").encode()
    contents = {"metadata.json": metadata, "kuksa-ca.pem": certificate}
    safe_path(PUBLIC)
    paths = [PUBLIC / team for team in ("brake", "tire")]
    for directory in paths:
        safe_path(directory)
        if directory.exists() and (not directory.is_dir() or set(p.name for p in directory.iterdir()) - set(contents)):
            raise ValueError("SERVICE_INPUT_DIRECTORY_CONFLICT")
        for name in contents:
            path = directory / name
            if path.exists() or path.is_symlink():
                read_public(path)
    staged = []
    changed = []
    try:
        if not PUBLIC.exists():
            PUBLIC.mkdir(mode=0o755)
            PUBLIC.chmod(0o755)
        for directory in paths:
            if not directory.exists():
                directory.mkdir(mode=0o755)
                directory.chmod(0o755)
            if stat.S_IMODE(directory.stat().st_mode) != 0o755:
                raise ValueError("SERVICE_INPUT_DIRECTORY_MODE")
            for name, content in contents.items():
                target = directory / name
                if target.exists() and target.read_bytes() == content and stat.S_IMODE(target.stat().st_mode) == 0o444:
                    continue
                descriptor, temporary = tempfile.mkstemp(prefix=".democtl-input-", dir=directory)
                staged.append((Path(temporary), target))
                with os.fdopen(descriptor, "wb") as output:
                    output.write(content)
                    os.fchmod(output.fileno(), 0o444)
                    os.fsync(output.fileno())
        if observe() != before or read_public(CERTIFICATE, 32768) != certificate:
            raise ValueError("SERVICE_INPUT_SOURCE_CHANGED")
        for temporary, target in staged:
            os.replace(temporary, target)
            changed.append(str(target.relative_to(PUBLIC)))
        for directory in paths:
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        if observe() != before:
            raise ValueError("SERVICE_INPUT_POST_WRITE_RECONCILIATION_REQUIRED")
        return dict(state="PREPARED", noOp=not changed, changed=changed,
            metadata=before["metadata"], vdpVersion=before["installed"]["Version"],
            sources={team: str(PUBLIC / team) for team in ("brake", "tire")},
            resourcesActivated=False, containerActions=False, coldStartQualified=False,
            processVerified=not cold)
    finally:
        for temporary, _ in staged:
            if temporary.exists():
                temporary.unlink()


def invalidate_projection():
    # Only reproducible public files owned by this projector. Keep directory
    # inodes stable and never touch the committed component store or recovery.
    for team in ("brake", "tire"):
        directory = PUBLIC / team
        safe_path(directory)
        if directory.exists() and (not directory.is_dir() or set(p.name for p in directory.iterdir())
                - {"metadata.json", "kuksa-ca.pem"}):
            raise ValueError("SERVICE_INPUT_DIRECTORY_CONFLICT")
        for name in ("metadata.json", "kuksa-ca.pem"):
            path = directory / name
            if path.exists() or path.is_symlink():
                read_public(path)
                path.unlink()


def startup_record(name, value):
    safe_path(STARTUP)
    if not STARTUP.is_dir():
        raise ValueError("SERVICE_INPUT_STARTUP_DIRECTORY_REQUIRED")
    target = STARTUP / name
    safe_path(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".startup-", dir=STARTUP)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, sort_keys=True)
            output.write("\n")
            os.fchmod(output.fileno(), 0o600)
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def startup(mode):
    """Existing systemd startup integration, never a container launcher.

    A transaction/incomplete component defers public data without preventing
    native SM recovery. Post-start observation is not a service restart loop.
    """
    if os.geteuid() != 0 or mode not in ("cold", "verify"):
        raise ValueError("SERVICE_INPUT_OPERATION_INVALID")
    # Factory boot has no transient democtl activation directory. Keep mount
    # source inodes stable even before the first committed compatible VDP.
    for directory, permissions in ((STARTUP, 0o700), (PUBLIC, 0o755),
                                   (PUBLIC / "brake", 0o755), (PUBLIC / "tire", 0o755)):
        safe_path(directory)
        if not directory.exists():
            directory.mkdir(mode=permissions)
        if not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) != permissions:
            raise ValueError("SERVICE_INPUT_DIRECTORY_MODE")
    value = dict(stage="DEFERRED", processVerified=False, observedMonotonicNs=time.monotonic_ns())
    try:
        uid = native_identity()
        request = dict(role="test", nativeSystemUid=uid, vehicle=dict(systemUid=uid))
        if mode == "cold":
            result = project(request, cold=True)
            value.update(stage="PREPARED", vdpVersion=result["vdpVersion"])
        else:
            deadline = time.monotonic() + 15
            while True:
                try:
                    observed = snapshot(request)
                    for team in ("brake", "tire"):
                        if read_document(PUBLIC / team / "metadata.json") != observed["metadata"]:
                            raise ValueError("SERVICE_INPUT_STARTUP_PROJECTION_MISMATCH")
                    value.update(stage="VERIFIED", processVerified=True, vdpVersion=observed["installed"]["Version"])
                    break
                except ValueError as error:
                    if str(error) != "SERVICE_INPUT_PROVIDER_NOT_RUNNING" or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        reason = str(error)
        value["reason"] = reason if re.fullmatch(r"SERVICE_INPUT_[A-Z_]+", reason) else "SERVICE_INPUT_STARTUP_UNAVAILABLE"
        if mode == "cold":
            invalidate_projection()
    startup_record(mode + ".json", value)
    print("SERVICE_INPUT_" + mode.upper() + "_" + value["stage"], flush=True)
    return value


def main(request):
    try:
        if request.get("action") != "service-runtime-prepare" or os.geteuid() != 0:
            raise ValueError("SERVICE_INPUT_OPERATION_INVALID")
        value = dict(ok=True, data=project(request))
    except Exception as error:
        reason = str(error)
        value = dict(ok=False, reason=reason if re.fullmatch(r"SERVICE_INPUT_[A-Z_]+", reason)
                     else "SERVICE_INPUT_PREPARATION_FAILED")
    print(json.dumps(value))


if __name__ == "__main__" and sys.argv[0] != "-":
    if len(sys.argv) != 2 or sys.argv[1] not in ("cold", "verify"):
        raise SystemExit("SERVICE_INPUT_OPERATION_INVALID")
    startup(sys.argv[1])
