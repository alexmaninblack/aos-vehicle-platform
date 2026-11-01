# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Offline IPC/target fixtures; these are not a native Aos authorization proof."""
import io
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace
import unittest
import tarfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'camera-access/src'))
from aos_camera_access import CameraAccess,CameraError
from aos_camera_access import ipc
from aos_camera_access.daemon import peer,validate_identity
from aos_camera_access.vision_image import select


class Stream:
    def __init__(self, data=b''):
        self.input=io.BytesIO(data);self.output=io.BytesIO()
    def settimeout(self, value):
        assert 0<value<=ipc.DEADLINE_SECONDS
    def recv(self, size):return self.input.read(min(size,3))
    def send(self, value):return self.output.write(value[:3])


class NativeContractTests(unittest.TestCase):
    def test_daemon_rejects_foreign_identity_groups_capabilities_and_privilege(self):
        status='NoNewPrivs:\t1\n'+''.join(k+':\t0\n' for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
        with patch('aos_camera_access.daemon.pwd.getpwnam',return_value=SimpleNamespace(pw_uid=500)), \
             patch('aos_camera_access.daemon.grp.getgrnam',return_value=SimpleNamespace(gr_gid=501)), \
             patch('aos_camera_access.daemon.os.getuid',return_value=500) as uid, \
             patch('aos_camera_access.daemon.os.geteuid',return_value=500), \
             patch('aos_camera_access.daemon.os.getgid',return_value=501), \
             patch('aos_camera_access.daemon.os.getegid',return_value=501), \
             patch('aos_camera_access.daemon.os.getgroups',return_value=[501]) as groups, \
             patch('aos_camera_access.daemon.Path.read_text',return_value=status) as proc:
            self.assertEqual((500,501),validate_identity())
            groups.return_value=[501,777]
            with self.assertRaisesRegex(CameraError,'GROUPS'):validate_identity()
            groups.return_value=[501];uid.return_value=0
            with self.assertRaisesRegex(CameraError,'IDENTITY'):validate_identity()
            uid.return_value=500
            for bad in (status.replace('NoNewPrivs:\t1','NoNewPrivs:\t0'),status.replace('CapEff:\t0','CapEff:\t1')):
                proc.return_value=bad
                with self.assertRaises(CameraError):validate_identity()

    def test_partial_reads_and_writes_use_the_same_deadline(self):
        value={'schemaVersion':1,'operation':'status'}
        wire=ipc.header(value);stream=Stream(wire)
        self.assertEqual(value,ipc.receive(stream,time.monotonic()+2))
        ipc.write(stream,(wire,b'jpeg'),time.monotonic()+2)
        self.assertEqual(wire+b'jpeg',stream.output.getvalue())

    def test_deadline_header_size_duplicates_nonfinite_and_schema_fail(self):
        raws=[b'{"schemaVersion":1,"operation":"pair","operation":"select"}',
              b'{"schemaVersion":true}',b'{"schemaVersion":1,"x":NaN}',b'[]',b'invalid']
        for raw in raws:
            with self.subTest(raw=raw),self.assertRaises(CameraError):
                ipc.receive(Stream(struct.pack('!I',len(raw))+raw),time.monotonic()+2)
        with self.assertRaisesRegex(CameraError,'LIMIT'):
            ipc.receive(Stream(struct.pack('!I',4097)),time.monotonic()+2)
        with self.assertRaisesRegex(CameraError,'DEADLINE'):
            ipc.receive(Stream(ipc.header({'schemaVersion':1})),time.monotonic()-1)

    def test_reader_cannot_select_feed_or_disconnect(self):
        camera=CameraAccess()
        for operation in ('select','frame','disconnect','health','hello','set-camera','motion'):
            with self.assertRaisesRegex(CameraError,'DENIED'):
                ipc.reader(camera,{'schemaVersion':1,'operation':operation},'epoch')
        with self.assertRaisesRegex(CameraError,'FIELDS'):
            ipc.reader(camera,{'schemaVersion':1,'operation':'pair','binding':{}},'epoch')
        raw=ipc.reader(camera,{'schemaVersion':1,'operation':'pair'},'epoch')[0]
        value=ipc.receive(Stream(raw),time.monotonic()+2)
        self.assertEqual('NO_PAIR',value['state'])
        self.assertEqual('UNAVAILABLE',value['status']['deliveryState'])

    def test_old_component_session_and_oversized_body_are_rejected(self):
        camera=CameraAccess()
        with self.assertRaisesRegex(CameraError,'EPOCH'):
            ipc.producer(camera,{'schemaVersion':1,'operation':'disconnect','componentEpoch':'old'},b'','new')
        for size in (True,0,4194305,-1,'100'):
            with self.assertRaisesRegex(CameraError,'SIZE'):
                ipc.producer_size({'operation':'frame','metadata':{'payloadBytes':size}})

    def test_native_peer_is_kernel_observed_not_caller_named(self):
        # Linux-only getsockopt is exercised with kernel-identity fixtures on
        # the development Mac; real SO_PEERCRED remains a separate M4 gate.
        patcher=patch('aos_camera_access.daemon.socket.SO_PEERCRED',17,create=True)
        patcher.start();self.addCleanup(patcher.stop)
        class Peer:
            def getsockopt(self,*_):return struct.pack('3i',123,1001,1001)
        self.assertEqual((123,1001,1001),peer(Peer(),False,500))
        with self.assertRaisesRegex(CameraError,'OEM_PEER'):
            peer(Peer(),True,500)
        class Root:
            def getsockopt(self,*_):return struct.pack('3i',123,0,0)
        self.assertEqual((123,0,0),peer(Root(),True,500))
        with self.assertRaisesRegex(CameraError,'READER_PEER'):
            peer(Root(),False,500)

    def test_component_target_and_read_resource_are_separate(self):
        p=json.loads((ROOT/'contracts/camera-access/native-profile.json').read_bytes())
        self.assertEqual('camera-access',p['component'])
        recipe=(ROOT/'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/aos-camera-access-platform_0.1.0.bb').read_text()
        shipped=next(line for line in recipe.splitlines() if line.startswith('FILES:${PN}'))
        self.assertIn('${systemd_system_unitdir}/aos-camera-access-selftest@.service',shipped)
        self.assertEqual('aos-camera-access.service',p['unit'])
        self.assertNotIn('vehicle-data-provider',p['workingDirectory'])
        self.assertEqual(['status','pair'],p['readerOperations'])
        self.assertEqual(['bind','ro','nosuid','nodev','noexec'],p['mountOptions'])
        self.assertNotIn('/oem/',p['resourceSource'])
        self.assertEqual(1,p['sharedCount'])

    def test_vision_selection_does_not_mutate_main_or_share_its_target(self):
        folder=ROOT/'meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files'
        sm=json.loads((folder/'sm.cfg').read_bytes());before=json.dumps(sm,sort_keys=True)
        native=json.loads((ROOT/'contracts/camera-access/native-profile.json').read_bytes())
        resources=json.loads((folder/'resources.cfg').read_bytes())
        selected,grants=select(sm,resources,native)
        self.assertEqual(before,json.dumps(sm,sort_keys=True))
        target=next(x for x in selected['runtimes'] if x['plugin']=='systemd-slot-component')
        self.assertEqual('camera-access',target['type'])
        self.assertEqual('camera-access-v1',target['config']['componentProfile'])
        self.assertEqual(250,target['config']['safeStopReadTimeoutMilliseconds'])
        self.assertEqual(1,len(grants))
        self.assertEqual('/run/aos-camera-access/read',grants[0]['mounts'][0]['source'])
        self.assertEqual(['aos-camera-read'],grants[0]['groups'])
        sm['runtimes'][-1]['type']='aos-vision-vm-1.0.0-main-qemuarm64-vehicle-data-provider'
        vision,_=select(sm,resources,native)
        self.assertEqual('aos-vision-vm-1.0.0-main-qemuarm64-camera-access',vision['runtimes'][-1]['type'])
        with self.assertRaises(CameraError):select(selected,grants,native)
        with self.assertRaises(CameraError):select(sm,[{'name':'unreviewed'}],native)

    def test_bootstrap_is_disabled_nonroot_and_has_no_network_or_vdp_credential(self):
        folder=ROOT/'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform'
        unit=(folder/'files/aos-camera-access.service').read_text()
        for setting in ('User=aos-camera-access','Group=aos-camera-read','RestrictAddressFamilies=AF_UNIX',
                        'ProtectSystem=strict','CapabilityBoundingSet=','AmbientCapabilities=','Restart=no'):
            self.assertIn(setting,unit)
        for setting in ('LoadCredential=','kuksa','vehicle-data-provider','WantedBy='):
            self.assertNotIn(setting,unit)
        self.assertIn('SYSTEMD_AUTO_ENABLE:${PN} = "disable"',next(folder.glob('*.bb')).read_text())

    def test_payload_is_deterministic_distinct_and_has_no_credentials_or_models(self):
        spec=importlib.util.spec_from_file_location('camera_payload',ROOT/'tools/build_camera_access_payload.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        raw=module.payload('0.1.0');self.assertEqual(raw,module.payload('0.1.0'))
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            self.assertEqual(['bin/camera-access','component.json','config/camera.json'],archive.getnames())
            metadata=json.load(archive.extractfile('component.json'))
            self.assertEqual('camera-access',metadata['component'])
            self.assertEqual('bin/camera-access',metadata['entrypoint'])
            self.assertEqual('config/camera.json',metadata['configuration'])
            from aos_camera_access.__main__ import CONFIG
            config=json.load(archive.extractfile('config/camera.json'));config.pop('$comment')
            self.assertEqual(CONFIG,config)
        with self.assertRaises(ValueError):module.payload('../0.1')


if __name__=='__main__':unittest.main()
