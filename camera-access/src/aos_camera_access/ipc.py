# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Closed local camera IPC framing. Transport permission is enforced separately."""
import json
import struct
import time

from .core import CameraAccess, CameraError, Frame, SourceBinding, MAX_JPEG_BYTES, require

MAX_HEADER = 4096
DEADLINE_SECONDS = 2


def unique(items):
    result = {}
    for key, value in items:
        require(key not in result, "IPC_DUPLICATE_FIELD")
        result[key] = value
    return result


def header(value):
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    require(0 < len(raw) <= MAX_HEADER, "IPC_HEADER_LIMIT")
    return struct.pack("!I", len(raw)) + raw


def exact(connection, size, deadline):
    result = bytearray()
    while len(result) < size:
        left = deadline - time.monotonic()
        require(left > 0, "IPC_DEADLINE")
        connection.settimeout(left)
        part = connection.recv(min(size-len(result), 65536))
        require(part, "IPC_TRUNCATED")
        result.extend(part)
    return bytes(result)


def receive(connection, deadline):
    size = struct.unpack("!I", exact(connection, 4, deadline))[0]
    require(0 < size <= MAX_HEADER, "IPC_HEADER_LIMIT")
    try:
        value = json.loads(exact(connection, size, deadline), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(CameraError("IPC_NUMBER_INVALID")))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise CameraError("IPC_HEADER_INVALID") from error
    require(type(value) is dict and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 1, "IPC_SCHEMA_INVALID")
    return value


def write(connection, chunks, deadline):
    for chunk in chunks:
        pending = memoryview(chunk)
        while pending:
            left = deadline-time.monotonic()
            require(left > 0, "IPC_DEADLINE")
            connection.settimeout(left)
            count = connection.send(pending[:65536])
            require(count > 0, "IPC_TRUNCATED")
            pending = pending[count:]


def frame_metadata(frame: Frame):
    f = frame.info
    return dict(schemaVersion=1, profile=f.profile, sourceId=f.source_id, sourceEpoch=f.source_epoch,
                cameraId=f.camera_id, calibrationId=f.calibration_id, frame=f.frame,
                simulationTimeNs=f.simulation_time_ns, sensorSimulationTimeNs=f.sensor_simulation_time_ns,
                clock=f.clock, encoding=f.encoding, width=f.width, height=f.height,
                payloadBytes=len(frame.jpeg), sha256=f.sha256)


def reader(camera: CameraAccess, request: dict, component_epoch: str):
    require(set(request) == {"schemaVersion", "operation"}, "IPC_READER_FIELDS_INVALID")
    require(request["operation"] in ("status", "pair"), "IPC_READER_OPERATION_DENIED")
    status = camera.status()
    response = dict(schemaVersion=1, componentEpoch=component_epoch, status=status)
    if request["operation"] == "status":
        return (header(dict(response, state="STATUS")),)
    pair = camera.take_pair()
    if pair is None:
        return (header(dict(response, state="NO_PAIR")),)
    return (header(dict(response, state="PAIR", frames=[frame_metadata(f) for f in pair])),
            pair[0].jpeg, pair[1].jpeg)


def producer(camera: CameraAccess, request: dict, payload: bytes, component_epoch: str):
    require(request.get("componentEpoch") == component_epoch, "IPC_COMPONENT_EPOCH_MISMATCH")
    operation = request.get("operation")
    fields = {"schemaVersion", "componentEpoch", "operation"}
    if operation == "select":
        require(set(request) == fields | {"binding"} and not payload, "IPC_PRODUCER_FIELDS_INVALID")
        value = request["binding"]
        require(type(value) is dict and set(value) == {"sourceId", "sourceEpoch", "cameraId", "calibrationId"}, "IPC_BINDING_FIELDS_INVALID")
        camera.select(SourceBinding(value["sourceId"], value["sourceEpoch"], value["calibrationId"], value["cameraId"]))
    elif operation == "frame":
        require(set(request) == fields | {"metadata"}, "IPC_PRODUCER_FIELDS_INVALID")
        camera.admit(request["metadata"], payload)
    elif operation == "disconnect":
        require(set(request) == fields and not payload, "IPC_PRODUCER_FIELDS_INVALID")
        camera.disconnect()
    else:
        require(operation == "health" and set(request) == fields and not payload, "IPC_PRODUCER_OPERATION_DENIED")
    return dict(schemaVersion=1, componentEpoch=component_epoch, state="ACCEPTED", status=camera.status())


def producer_size(request):
    if request.get("operation") != "frame":
        return 0
    metadata = request.get("metadata")
    require(type(metadata) is dict, "IPC_FRAME_METADATA_INVALID")
    size = metadata.get("payloadBytes")
    require(type(size) is int and 0 < size <= MAX_JPEG_BYTES, "IPC_FRAME_SIZE_INVALID")
    return size
