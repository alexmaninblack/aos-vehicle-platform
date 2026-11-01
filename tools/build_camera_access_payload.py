#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Create the distinct deterministic OEM payload; no signature or publication.

Its Python interpreter comes from the explicitly selected Vision bootstrap.
The native archive/OCI/signature pipeline remains the installer owner's gate.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def payload(version):
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("CAMERA_VERSION_INVALID")
    archive = io.BytesIO()
    archive.write(b"#!/usr/bin/env python3\n")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        entries = {"__main__.py": b"from aos_camera_access.__main__ import main\nraise SystemExit(main())\n"}
        source = ROOT/"camera-access/src/aos_camera_access"
        for path in sorted(source.glob("*.py")):
            if path.name != "vision_image.py":
                entries["aos_camera_access/"+path.name] = path.read_bytes()
        if version == '0.1.2':
            pin=json.loads((ROOT/'contracts/camera-access/vision-exchange-source.json').read_bytes())
            for row in pin['files']:
                path=ROOT/row['path'];raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('EXCHANGE_COMMON_PIN_CHANGED')
                entries['vision_common/'+path.name]=raw
            for path in sorted((ROOT/'camera-access/src/aos_vision_exchange').glob('*.py')):
                entries['aos_vision_exchange/'+path.name]=path.read_bytes()
        for name, raw in sorted(entries.items()):
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            item.external_attr = 0o100644 << 16
            item.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(item, raw)
    metadata = dict(schemaVersion=1, component="camera-access", version=version, architecture="arm64", os="linux",
                    runtimeInterface=1, entrypoint="bin/camera-access", configuration="config/camera.json")
    files = {"bin/camera-access": archive.getvalue(), "config/camera.json": (ROOT/"camera-access/config/camera.json").read_bytes(),
             "component.json": (json.dumps(metadata, sort_keys=True, indent=2)+"\n").encode()}
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, raw in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.mode = 0o755 if name.startswith("bin/") else 0o644
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return result.getvalue()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raw = payload(a.version)
    with a.output.open("xb") as output:
        output.write(raw)
    print(json.dumps(dict(component="camera-access", version=a.version, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                          status="UNSIGNED_PAYLOAD_NOT_DEPLOYED")))


if __name__ == "__main__":
    main()
