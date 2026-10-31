# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Native OEM camera daemon: separate read and OEM sockets, no network listener."""
import grp
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import stat
import struct
import threading
import time
from uuid import uuid4

from .core import CameraAccess, CameraError, require
from . import ipc

ROOT = Path("/run/aos-camera-access")
READ = ROOT / "read/camera.sock"
OEM = ROOT / "oem/producer.sock"
USER = "aos-camera-access"
GROUP = "aos-camera-read"


def validate_identity():
    uid = pwd.getpwnam(USER).pw_uid
    gid = grp.getgrnam(GROUP).gr_gid
    require(uid != 0 and gid != 0 and os.getuid() == os.geteuid() == uid
            and os.getgid() == os.getegid() == gid, "DAEMON_IDENTITY_INVALID")
    require(all(g == gid for g in os.getgroups()), "DAEMON_GROUPS_INVALID")
    status = Path("/proc/self/status").read_text()
    values = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    require(values["NoNewPrivs"].strip() == "1", "DAEMON_PRIVILEGE_INVALID")
    require(all(int(values[k].strip(), 16) == 0 for k in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")), "DAEMON_CAPABILITIES_PRESENT")
    return uid, gid


def peer(connection, producer_side, daemon_uid):
    pid, uid, gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    if producer_side:
        require(uid in (0, daemon_uid), "OEM_PEER_DENIED")
    else:
        # The kernel checks named-resource group access to this socket before
        # accept. A read-only bind alone is not an authorization decision.
        require(pid > 0 and uid not in (0, daemon_uid), "READER_PEER_DENIED")
    return pid, uid, gid


def listener(path, mode, uid, gid):
    parent = path.parent
    check = parent.lstat()
    require(stat.S_ISDIR(check.st_mode) and check.st_uid == uid and check.st_gid == gid and not check.st_mode & 0o007, "SOCKET_PARENT_INVALID")
    require(not path.exists() and not path.is_symlink(), "SOCKET_OWNER_CONFLICT")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connection.bind(str(path))
    os.chmod(path, mode)
    connection.listen(1)
    connection.settimeout(.2)
    return connection


class Server:
    def __init__(self):
        self.camera = CameraAccess()
        self.epoch = str(uuid4())
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def serve(self, source, producer_side, uid):
        # One fixed worker per socket bounds in-flight frame/pair references.
        while not self.stop.is_set():
            try:
                connection, _ = source.accept()
            except socket.timeout:
                continue
            with connection:
                deadline = time.monotonic()+ipc.DEADLINE_SECONDS
                try:
                    peer(connection, producer_side, uid)
                    request = ipc.receive(connection, deadline)
                    if producer_side:
                        if request == {"schemaVersion": 1, "operation": "hello"}:
                            response = dict(schemaVersion=1, componentEpoch=self.epoch, state="OEM_HELLO")
                        else:
                            payload = ipc.exact(connection, ipc.producer_size(request), deadline)
                            with self.lock:
                                response = ipc.producer(self.camera, request, payload, self.epoch)
                        chunks = (ipc.header(response),)
                    else:
                        with self.lock:
                            chunks = ipc.reader(self.camera, request, self.epoch)
                    ipc.write(connection, chunks, deadline)
                except (CameraError, OSError, ValueError, TypeError, KeyError):
                    # No raw request, peer identity, exception or pixel data in logs.
                    pass

    def run(self):
        require(os.uname().sysname == "Linux", "LINUX_TARGET_REQUIRED")
        uid, gid = validate_identity()
        sockets = []
        threads = []
        try:
            for path, mode, producer_side in ((READ, 0o660, False), (OEM, 0o600, True)):
                source = listener(path, mode, uid, gid)
                sockets.append((source, path))
                thread = threading.Thread(target=self.serve, args=(source, producer_side, uid))
                thread.start();threads.append(thread)
            target = os.environ.get("NOTIFY_SOCKET")
            if target:
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as notify:
                    notify.connect("\0"+target[1:] if target.startswith("@") else target)
                    notify.sendall(b"READY=1\nSTATUS=Camera Access ready; source availability is separate")
            self.stop.wait()
        finally:
            self.stop.set()
            for thread in threads:
                thread.join(timeout=ipc.DEADLINE_SECONDS+1)
            self.camera.disconnect()
            for source, path in sockets:
                source.close()
                if path.is_socket():path.unlink()


def main():
    server = Server()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_:server.stop.set())
    try:
        server.run()
        return 0
    except (CameraError, OSError, KeyError):
        print("CAMERA_ACCESS_START_FAILED", flush=True)
        return 1


if __name__ == "__main__":raise SystemExit(main())
