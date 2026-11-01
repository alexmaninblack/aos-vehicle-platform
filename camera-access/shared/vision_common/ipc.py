# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Bounded local Unix framing; native resource permissions are not bypassed."""
import socket
import struct
import time
from .protocol import dumps,loads,require,MAX_RESULT,MAX_REQUEST


def exact(connection,size,deadline):
    result=bytearray()
    while len(result)<size:
        left=deadline-time.monotonic();require(left>0,'IPC_DEADLINE');connection.settimeout(left)
        part=connection.recv(min(size-len(result),65536));require(bool(part),'IPC_TRUNCATED');result.extend(part)
    return bytes(result)


def receive(connection,deadline,maximum=MAX_RESULT):
    size=struct.unpack('!I',exact(connection,4,deadline))[0];require(0<size<=maximum,'IPC_LENGTH_INVALID')
    return loads(exact(connection,size,deadline),maximum)


def send(connection,value,deadline,maximum=MAX_RESULT):
    raw=dumps(value,maximum);raw=struct.pack('!I',len(raw))+raw;view=memoryview(raw)
    while view:
        left=deadline-time.monotonic();require(left>0,'IPC_DEADLINE');connection.settimeout(left)
        count=connection.send(view[:65536]);require(count>0,'IPC_TRUNCATED');view=view[count:]


def exchange(path,value):
    deadline=time.monotonic()+2
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(2);connection.connect(str(path));send(connection,value,deadline)
        return receive(connection,deadline)
