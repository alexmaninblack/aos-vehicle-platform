# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Retained-identity projection before SM; real certificate/key fixtures."""
import hashlib
import importlib.util
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
FILES=ROOT/'meta-aos-vehicle-platform/recipes-aos/aos-vehicle-data-provider-platform/files'
spec=importlib.util.spec_from_file_location('boot_projection',FILES/'aos-demo-viss-boot-projection.py')
boot=importlib.util.module_from_spec(spec);spec.loader.exec_module(boot)
OPENSSL='/opt/homebrew/opt/openssl@3/bin/openssl'
if not Path(OPENSSL).is_file():OPENSSL=shutil.which('openssl')
UNIT='11111111-1111-4111-8111-111111111111'
NODE='22222222-2222-4222-8222-222222222222'
MACHINE='33333333333343338333333333333333'

class PackagingTests(unittest.TestCase):
 def test_existing_bootstrap_is_the_ordering_owner(self):
  unit=(FILES/'aos-vehicle-data-provider-bootstrap.service').read_text()
  self.assertIn('Before=aos-sm.service',unit)
  self.assertIn('ExecStartPost=/usr/bin/python3 -B /usr/libexec/aos-demo-viss-boot-projection.py',unit)
  self.assertNotIn('ExecStartPre=',unit)
  recipe=(FILES.parent/'aos-vehicle-data-provider-platform_0.1.0.bb').read_text()
  self.assertIn('file://aos-demo-viss-boot-projection.py',recipe)
  self.assertIn('python3-modules',recipe)
  self.assertIn('openssl',recipe)

@unittest.skipUnless(OPENSSL,'OpenSSL is required for certificate fixtures')
class ProjectionTests(unittest.TestCase):
 def setUp(self):
  self.stack=ExitStack();self.addCleanup(self.stack.close)
  self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
  self.inputs=self.root/'inputs';self.store=self.root/'credentials';self.systemd=self.root/'systemd'
  self.inputs.mkdir();self.store.mkdir();self.machine=self.root/'machine';self.machine.write_text(MACHINE)
  for name,value in dict(INPUTS=self.inputs,STORE=self.store,SYSTEMD=self.systemd,MACHINE=self.machine).items():
   self.stack.enter_context(patch.object(boot,name,value))
  # The test user cannot own root ancestors. Only ancestry validation is
  # substituted; file modes, hardlinks, crypto and output bytes remain real.
  self.stack.enter_context(patch.object(boot,'safe'))
  self.calls=[]
  def command(args):
   self.calls.append(args)
   if args[0]=='openssl':
    return subprocess.check_output([OPENSSL,*args[1:]],text=True,stderr=subprocess.DEVNULL)
   self.assertEqual(args,['systemctl','daemon-reload']);return ''
  self.stack.enter_context(patch.object(boot,'command',side_effect=command))
  fingerprints={}
  for role in ('selected-platform-unit','platform-update-runtime'):
   directory=self.store/role;directory.mkdir()
   cert=directory/'client.pem';key=directory/'client-key.pem'
   subprocess.run([OPENSSL,'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
       '-subj','/CN=fixture','-addext','subjectAltName=URI:urn:aosedge:demo:viss-client:v1:'+role+':'+UNIT+':'+NODE,
       '-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   cert.chmod(0o600);key.chmod(0o600)
   fingerprints[role]=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
  (self.inputs/'role').write_text('test\n');(self.inputs/'viss-update-ca').write_text('public fixture')
  self.selected=dict(schemaVersion=2,viss=dict(uri='wss://10.0.0.1:6443',tlsServerName='127.0.0.1'),
    selectedSource=dict(unitId=UNIT,nodeId=NODE,role='SELECTED_PLATFORM_UNIT',assignmentGeneration=7,
      clientCertificateSha256=fingerprints['selected-platform-unit']))
  self.binding=dict(schemaVersion=1,unitId=UNIT,nodeId=MACHINE,role='PLATFORM_UPDATE_RUNTIME',assignmentGeneration=7,
    clientCertificateSha256=fingerprints['platform-update-runtime'])
  self.write_bindings()
 def write_bindings(self):
  (self.inputs/'selected.json').write_text(json.dumps(self.selected))
  (self.inputs/'viss-update-binding').write_text(json.dumps(self.binding))
 def reject(self,reason):
  with self.assertRaisesRegex(ValueError,reason):boot.restore()
  self.assertFalse(self.systemd.exists())
 def test_first_restore_repeat_preserves_private_bytes(self):
  before={p:p.read_bytes() for p in self.store.rglob('*') if p.is_file()}
  self.assertEqual(boot.restore(),'RESTORED');self.assertEqual(boot.restore(),'UNCHANGED')
  self.assertEqual(sum(c==['systemctl','daemon-reload'] for c in self.calls),1)
  self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
  self.assertEqual(len(list(self.systemd.glob('*.service.d/85-democtl-viss-mtls.conf'))),2)
  self.assertFalse(any('restart' in c or 'start' in c for c in self.calls))
 def test_empty_factory(self):
  (self.inputs/'selected.json').unlink();self.assertEqual(boot.restore(),'NOT_ENROLLED');self.assertFalse(self.systemd.exists())
 def test_production(self):
  (self.inputs/'role').write_text('production\n');self.assertEqual(boot.restore(),'NOT_APPLICABLE');self.assertFalse(self.systemd.exists())
 def test_wrong_identity(self):
  self.machine.write_text('a'*32);self.reject('IDENTITY_MISMATCH')
 def test_wrong_generation(self):
  self.binding['assignmentGeneration']=8;self.write_bindings();self.reject('IDENTITY_MISMATCH')
 def test_wrong_fingerprint(self):
  self.binding['clientCertificateSha256']='a'*64;self.write_bindings();self.reject('ENROLLMENT_MISMATCH')
 def test_wrong_route(self):
  self.selected['viss']['uri']='wss://foreign:6443';self.write_bindings();self.reject('SOURCE_BINDING_MISMATCH')
 def test_incomplete_enrollment(self):
  del self.selected['selectedSource']['clientCertificateSha256'];self.write_bindings();self.reject('INCOMPLETE_ENROLLMENT')
 def test_public_private_key_rejected(self):
  (self.store/'selected-platform-unit/client-key.pem').chmod(0o644);self.reject('UNSAFE_FILE')
 def test_hardlinked_key_rejected(self):
  os.link(self.store/'selected-platform-unit/client-key.pem',self.root/'extra-link');self.reject('UNSAFE_FILE')
 def test_foreign_key_rejected(self):
  target=self.store/'selected-platform-unit/client-key.pem';target.write_bytes((self.store/'platform-update-runtime/client-key.pem').read_bytes());self.reject('KEY_MISMATCH')
 def test_existing_projection_conflict(self):
  p=self.systemd/'aos-sm.service.d/85-democtl-viss-mtls.conf';p.parent.mkdir(parents=True);p.write_text('foreign')
  with self.assertRaisesRegex(ValueError,'PROJECTION_CONFLICT'):boot.restore()
  self.assertEqual(p.read_text(),'foreign')

if __name__=='__main__':unittest.main()
