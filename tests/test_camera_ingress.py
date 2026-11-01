# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Offline bounded MJPEG/IPC contract tests; never opens a network socket."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'camera-access/src'))
from aos_camera_access import CameraError,CameraAccess
from aos_camera_access.core import SourceBinding
from aos_camera_access import ingress,ipc

SOURCE='00000000-0000-0000-0000-000000000001'
EPOCH='00000000-0000-0000-0000-000000000002'
COMPONENT='00000000-0000-0000-0000-000000000003'
JPEG=b'\xff\xd8\xff\xc0'+struct.pack('!HBHHB',8,8,720,1280,3)+b'\xff\xd9'


def binding():return dict(sourceId=SOURCE,sourceEpoch=EPOCH,cameraId='front',calibrationId='a'*64,assignmentGeneration=7)
def metadata(frame=10):
    return dict(schemaVersion=1,profile='front-rgb-jpeg-720p-v1',sourceId=SOURCE,sourceEpoch=EPOCH,
        cameraId='front',calibrationId='a'*64,frame=frame,simulationTimeNs=frame*50_000_000,
        sensorSimulationTimeNs=frame*50_000_000,clock='CARLA_WORLD_SNAPSHOT_FRAME_MATCH',
        encoding='JPEG',width=1280,height=720,payloadBytes=len(JPEG),sha256=hashlib.sha256(JPEG).hexdigest())
def start(b=None):
    return ('HTTP/1.1 200 OK\r\nContent-Type: '+ingress.CONTENT_TYPE+'\r\nCache-Control: no-store\r\nConnection: close\r\nX-Aos-Camera-Binding: '+json.dumps(b or binding(),separators=(',',':'))+'\r\n\r\n').encode()
def part(m=None,p=JPEG):
    return ingress.BOUNDARY+('Content-Type: image/jpeg\r\nContent-Length: '+str(len(p))+'\r\nX-Aos-Camera-Metadata: '+json.dumps(m or metadata(),separators=(',',':'))+'\r\n\r\n').encode()+p+b'\r\n'
def reader(raw,clock=lambda:0):return ingress.Multipart(io.BytesIO(raw),lambda seconds:None,clock)


class IngressTests(unittest.TestCase):
    def test_valid_fragment_without_pixel_decode_and_original_sensor_time(self):
        r=reader(start()+part());r.begin(ingress.Selection(SOURCE,7));m,p=r.frame()
        self.assertEqual((m,p),(metadata(),JPEG))

    def test_http_redirect_query_and_unsupported_framing_fail_closed(self):
        for raw in (start().replace(b'200 OK',b'302 Found'),
                start().replace(b'boundary=aos-front-v1',b'boundary=other'),
                start().replace(b'Connection: close',b'Transfer-Encoding: chunked'),
                start().replace(b'Cache-Control: no-store',b'Cache-Control: no-store\r\nCache-Control: no-store'),
                start().replace(b'\r\n',b'\n')):
            with self.subTest(raw=raw[:25]),self.assertRaises(CameraError):reader(raw).begin(ingress.Selection(SOURCE,7))

    def test_foreign_source_generation_epoch_and_calibration_denied(self):
        for key,value in (('sourceId',EPOCH),('assignmentGeneration',8),('sourceEpoch','bad'),('calibrationId','bad'),('cameraId','rear')):
            b=binding();b[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):reader(start(b)).begin(ingress.Selection(SOURCE,7))

    def test_duplicate_json_bool_generation_and_nonfinite_fail(self):
        for b in (b'{"x":1,"x":2}',b'{"x":NaN}',b'[]',b' ' *4097):
            with self.assertRaises(CameraError):ingress.document(b)
        b=binding();b['assignmentGeneration']=True
        with self.assertRaises(CameraError):reader(start(b)).begin(ingress.Selection(SOURCE,1))

    def test_header_limits_truncation_and_single_deadline(self):
        for raw in (b'A'*4097+b'\r\n',start()[:-3]):
            with self.assertRaises(CameraError):reader(raw).begin(ingress.Selection(SOURCE,7))
        times=iter((0,0,0,3))
        with self.assertRaisesRegex(CameraError,'DEADLINE'):
            reader(start(),lambda:next(times)).begin(ingress.Selection(SOURCE,7))

    def test_malformed_part_is_rejected_before_ipc_delivery(self):
        for wire in (part().replace(('Content-Length: '+str(len(JPEG))).encode(),b'Content-Length: 4194305'),
                part()[:-4],part().replace(b'image/jpeg',b'application/octet-stream'),
                part().replace(b'Content-Length:',b'Content-Length: 3\r\nContent-Length:'),
                part().replace(b'--aos-front-v1',b'--foreign'),
                part(metadata()|dict(sourceEpoch=SOURCE)),part(metadata()|dict(sha256='b'*64)),
                part(metadata()|dict(sensorSimulationTimeNs=9999999999))):
            r=reader(start()+wire);r.begin(ingress.Selection(SOURCE,7))
            with self.subTest(wire=wire[:55]),self.assertRaises(CameraError):r.frame()

    def test_actual_core_pair_and_disconnect_on_eof(self):
        camera=CameraAccess();operations=[]
        def exchange(request,payload=b''):
            operations.append(request['operation'])
            if request['operation']=='hello':return dict(schemaVersion=1,componentEpoch=COMPONENT,state='OEM_HELLO')
            result=ipc.producer(camera,request,payload,COMPONENT)
            if request['operation']=='frame' and request['metadata']['frame']==12:
                pair=camera.take_pair();self.assertEqual([v.info.frame for v in pair],[10,12])
                self.assertEqual(pair[0].jpeg,JPEG)
            return result
        with self.assertRaises(CameraError):
            ingress.forward(reader(start()+part()+part(metadata(12))),ingress.Selection(SOURCE,7),lambda:False,exchange)
        self.assertEqual(operations,['hello','select','frame','frame','disconnect'])
        self.assertEqual(camera.status()['deliveryState'],'UNAVAILABLE')

    def test_component_restart_never_silently_reselects_old_upstream(self):
        operations=[]
        def exchange(request,payload=b''):
            operations.append(request['operation'])
            if request['operation']=='hello':return dict(schemaVersion=1,componentEpoch=COMPONENT,state='OEM_HELLO')
            if request['operation']=='select':return dict(schemaVersion=1,componentEpoch=COMPONENT,state='ACCEPTED')
            raise CameraError('IPC_COMPONENT_EPOCH_MISMATCH')
        with self.assertRaisesRegex(CameraError,'EPOCH'):
            ingress.forward(reader(start()+part()),ingress.Selection(SOURCE,7),lambda:False,exchange)
        self.assertEqual(operations,['hello','select','frame','disconnect'])

    def test_trickled_headers_and_body_share_one_absolute_deadline(self):
        class Trickle:
            def __init__(self,raw):self.raw=io.BytesIO(raw);self.now=0
            def read(self,size):self.now+=.4;return self.raw.read(min(size,1))
        wire=Trickle(start());r=ingress.Multipart(wire,lambda seconds:None,lambda:wire.now)
        with self.assertRaisesRegex(CameraError,'DEADLINE'):r.begin(ingress.Selection(SOURCE,7))
        r=reader(start()+part());r.begin(ingress.Selection(SOURCE,7))
        wire=Trickle(b'');r.clock=lambda:wire.now
        # Even a prebuffered body is checked against the same end time.
        end=r.clock()+2;wire.now=3
        with self.assertRaisesRegex(CameraError,'DEADLINE'):r.exact(1,end)


if __name__=='__main__':unittest.main()
