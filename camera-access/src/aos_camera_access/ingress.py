# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Bounded authenticated Gateway input; Camera core/apps receive no TLS key.

Importing this module opens no file, socket, device or process. The executable
owner supplies systemd credentials; the endpoint is never operator-configurable.
"""
from dataclasses import dataclass
import json
import socket
import ssl
import time

from .core import SourceBinding, validate, require, integer, uuid, MAX_JPEG_BYTES
from . import ipc

PATH='/vision/v1/camera/front.mjpeg'
BOUNDARY=b'--aos-front-v1\r\n'
CONTENT_TYPE='multipart/x-mixed-replace; boundary=aos-front-v1'
OEM='/run/aos-camera-access/oem/producer.sock'
DEADLINE=2


def document(raw):
    require(type(raw) is bytes and 0<len(raw)<=4096,'INGRESS_METADATA_LIMIT')
    try:
        value=json.loads(raw,object_pairs_hook=ipc.unique,
            parse_constant=lambda _:require(False,'INGRESS_NUMBER_INVALID'))
    except (ValueError,UnicodeError,RecursionError):
        require(False,'INGRESS_METADATA_INVALID')
    require(type(value) is dict,'INGRESS_METADATA_INVALID')
    return value


@dataclass(frozen=True)
class Selection:
    source_id: str
    generation: int

    def __post_init__(self):
        require(uuid(self.source_id),'INGRESS_SOURCE_INVALID')
        require(integer(self.generation) and self.generation>0,'INGRESS_GENERATION_INVALID')


class Multipart:
    """One part deadline covers all its headers/body, not each individual read."""
    def __init__(self,stream,set_timeout,clock=time.monotonic):
        self.stream=stream;self.set_timeout=set_timeout;self.clock=clock;self.pending=bytearray()

    def timeout(self,end):
        left=end-self.clock();require(left>0,'INGRESS_DEADLINE')
        self.set_timeout(left)

    def line(self,end):
        # The live stream is unbuffered: every recv uses the remaining absolute
        # deadline. Buffered readline/read(size) could reset its timeout for each
        # tiny fragment internally and let a slow sender hold the part forever.
        while True:
            newline=self.pending.find(b'\n')
            if newline>=0:
                raw=bytes(self.pending[:newline+1]);del self.pending[:newline+1]
                require(len(raw)<=4096 and raw.endswith(b'\r\n'),'INGRESS_LINE_INVALID')
                self.timeout(end);return raw
            require(len(self.pending)<4096,'INGRESS_LINE_INVALID')
            self.timeout(end);chunk=self.stream.read(min(1024,4096-len(self.pending)))
            require(bool(chunk),'INGRESS_TRUNCATED');self.pending.extend(chunk)

    def exact(self,size,end):
        out=bytearray()
        if self.pending:
            take=min(size,len(self.pending));out.extend(self.pending[:take]);del self.pending[:take]
        while len(out)<size:
            self.timeout(end);part=self.stream.read(min(65536,size-len(out)))
            require(bool(part),'INGRESS_TRUNCATED');out.extend(part)
        self.timeout(end);return bytes(out)

    def headers(self,end):
        fields={};total=0
        for _ in range(16):
            raw=self.line(end);total+=len(raw)
            require(total<=8192,'INGRESS_HEADERS_LIMIT')
            if raw==b'\r\n':return fields
            require(b':' in raw and raw[:1] not in (b' ',b'\t'),'INGRESS_HEADER_INVALID')
            name,value=raw[:-2].split(b':',1)
            try:name=name.decode('ascii').lower();value=value.strip(b' ').decode('ascii')
            except UnicodeError:require(False,'INGRESS_HEADER_INVALID')
            require(name and all(c.islower() or c.isdigit() or c=='-' for c in name)
                and all(32<=ord(c)<127 for c in value) and name not in fields,'INGRESS_HEADER_INVALID')
            fields[name]=value
        require(False,'INGRESS_HEADERS_LIMIT')

    def begin(self,selection):
        end=self.clock()+DEADLINE
        require(self.line(end)==b'HTTP/1.1 200 OK\r\n','INGRESS_HTTP_REJECTED')
        fields=self.headers(end)
        require(fields.get('content-type')==CONTENT_TYPE and fields.get('connection')=='close'
            and fields.get('cache-control')=='no-store'
            and set(fields)=={'content-type','connection','cache-control','x-aos-camera-binding'},'INGRESS_RESPONSE_INVALID')
        value=document(fields['x-aos-camera-binding'].encode('ascii'))
        require(set(value)=={'sourceId','sourceEpoch','cameraId','calibrationId','assignmentGeneration'},'INGRESS_BINDING_INVALID')
        require(value['sourceId']==selection.source_id and type(value['assignmentGeneration']) is int
            and value['assignmentGeneration']==selection.generation,'INGRESS_SELECTION_MISMATCH')
        self.binding=SourceBinding(value['sourceId'],value['sourceEpoch'],value['calibrationId'],value['cameraId'])
        return self.binding

    def frame(self):
        require(hasattr(self,'binding'),'INGRESS_NOT_BOUND')
        end=self.clock()+DEADLINE
        require(self.line(end)==BOUNDARY,'INGRESS_BOUNDARY_INVALID')
        fields=self.headers(end)
        require(set(fields)=={'content-type','content-length','x-aos-camera-metadata'}
            and fields['content-type']=='image/jpeg','INGRESS_PART_INVALID')
        length=fields['content-length']
        require(length.isascii() and length.isdecimal() and len(length)<=7
            and str(int(length))==length and 0<int(length)<=MAX_JPEG_BYTES,'INGRESS_FRAME_LIMIT')
        metadata=document(fields['x-aos-camera-metadata'].encode('ascii'))
        require(type(metadata.get('payloadBytes')) is int and metadata['payloadBytes']==int(length),'INGRESS_LENGTH_MISMATCH')
        jpeg=self.exact(int(length),end)
        require(self.exact(2,end)==b'\r\n','INGRESS_PART_END_INVALID')
        validate(metadata,jpeg,self.binding)
        return metadata,jpeg


def oem(request,payload=b''):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(DEADLINE);connection.connect(OEM)
        end=time.monotonic()+DEADLINE
        ipc.write(connection,(ipc.header(request),payload),end)
        return ipc.receive(connection,end)


def forward(reader,selection,stopped,exchange=oem):
    """Caller owns authenticated TLS. Local hello is not upstream authority."""
    binding=reader.begin(selection)
    hello=exchange(dict(schemaVersion=1,operation='hello'))
    require(set(hello)=={'schemaVersion','componentEpoch','state'} and hello['schemaVersion']==1
        and hello['state']=='OEM_HELLO','INGRESS_OEM_HELLO_INVALID')
    epoch=hello['componentEpoch'];require(uuid(epoch),'INGRESS_COMPONENT_EPOCH_INVALID')
    def send(operation,**fields):
        payload=fields.pop('payload',b'')
        value=exchange(dict(schemaVersion=1,componentEpoch=epoch,operation=operation,**fields),payload)
        require(value.get('schemaVersion')==1 and value.get('componentEpoch')==epoch
            and value.get('state')=='ACCEPTED','INGRESS_OEM_REJECTED')
    try:
        send('select',binding=dict(sourceId=binding.source_id,sourceEpoch=binding.source_epoch,
            cameraId=binding.camera_id,calibrationId=binding.calibration_id))
        while not stopped():
            metadata,jpeg=reader.frame();send('frame',metadata=metadata,payload=jpeg)
    finally:
        # Never keep pixels alive after EOF/timeout/invalid media. A restarted
        # daemon rejects this old component epoch; a fresh TLS session is needed.
        try:send('disconnect')
        except (ValueError,OSError):pass


def connect(context,selection,stopped,create_connection=socket.create_connection):
    """Fixed enrolled Source endpoint; no proxy, redirect or input URL."""
    with create_connection(('10.0.0.1',6443),timeout=DEADLINE) as tcp:
        with context.wrap_socket(tcp,server_hostname='127.0.0.1') as tls:
            tls.settimeout(DEADLINE)
            tls.sendall(('GET '+PATH+' HTTP/1.1\r\nHost: 127.0.0.1:6443\r\nConnection: close\r\n\r\n').encode('ascii'))
            with tls.makefile('rb',buffering=0) as stream:forward(Multipart(stream,tls.settimeout),selection,stopped)


def tls_context(ca,certificate,key):
    context=ssl.create_default_context(cafile=ca)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate,key)
    return context
