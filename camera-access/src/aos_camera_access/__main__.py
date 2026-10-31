# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""OEM payload entry. Source availability is independent of process health."""
import argparse
import json
from pathlib import Path
import socket
import time

from . import daemon, ipc
from .core import CameraAccess, CameraError, PROFILE, require

CONFIG = {"schemaVersion": 1, "component": "camera-access", "profile": PROFILE}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--mark-unavailable", action="store_true")
    a = p.parse_args()
    try:
        require(a.config.is_file() and not a.config.is_symlink() and a.config.stat().st_size <= 4096, "CONFIG_INVALID")
        value = json.loads(a.config.read_bytes(), object_pairs_hook=ipc.unique)
        value.pop("$comment", None)
        require(value == CONFIG and type(value.get("schemaVersion")) is int, "CONFIG_PROFILE_INVALID")
        require(not (a.self_test and a.mark_unavailable), "OPERATION_INVALID")
        if a.self_test:
            require(CameraAccess().status()["deliveryState"] == "UNAVAILABLE", "SELF_TEST_FAILED")
            print("STATE=PREPARED")
            return 0
        if a.mark_unavailable:
            def exchange(request):
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    deadline = time.monotonic()+ipc.DEADLINE_SECONDS
                    connection.settimeout(ipc.DEADLINE_SECONDS)
                    connection.connect(str(daemon.OEM))
                    ipc.write(connection, (ipc.header(request),), deadline)
                    return ipc.receive(connection, deadline)
            hello = exchange(dict(schemaVersion=1, operation="hello"))
            response = exchange(dict(schemaVersion=1, operation="disconnect", componentEpoch=hello["componentEpoch"]))
            require(response["status"]["deliveryState"] == "UNAVAILABLE", "INVALIDATE_FAILED")
            print("STATE=UNAVAILABLE")
            return 0
        return daemon.main()
    except (CameraError, OSError, ValueError, TypeError, KeyError):
        print("CAMERA_ACCESS_OPERATION_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
