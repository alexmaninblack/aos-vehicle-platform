# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Rehydrate existing Test VISS unit declarations before native SM startup.

No enrollment, credentials generation, source gate, service restart or Cloud
access. Only previously recorded public bindings and guest-local files are used.
"""
import hashlib
import json
import os
import re
import ssl
import stat
import subprocess
from pathlib import Path
from uuid import UUID

INPUTS=Path('/var/aos/workdirs/sm/runtimes/systemd-slot-component/demo-inputs')
STORE=Path('/var/aos/iam/vehicle-state')
MACHINE=Path('/etc/machine-id')
SYSTEMD=Path('/run/systemd/system')
OWNER=0

def safe(path):
    for item in (path,)+tuple(path.parents):
        if item.is_symlink():raise ValueError('UNSAFE_PATH')
        if item.exists():
            info=item.stat()
            if info.st_uid!=OWNER or info.st_mode & 0o022:raise ValueError('UNSAFE_PATH')
def regular(path,mode):
    safe(path)
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or stat.S_IMODE(info.st_mode)!=mode or not 0<info.st_size<16384:
        raise ValueError('UNSAFE_FILE')

def command(args):
    r=subprocess.run(args,capture_output=True,text=True,timeout=10)
    if r.returncode:raise ValueError('COMMAND_FAILED')
    return r.stdout

def write(path,text):
    safe(path)
    if path.exists():
        regular(path,0o644)
        if path.read_text()!=text:raise ValueError('PROJECTION_CONFLICT')
        return False
    # Validate parent ownership/type without manufacturing an enrollment.
    safe(path.parent)
    path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.new')
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o644)
    with os.fdopen(fd,'w') as stream:
        stream.write(text);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    return True

def restore():
    role=INPUTS/'role'
    if not role.exists() and not role.is_symlink():return 'NOT_ENROLLED'
    regular(role,0o644)
    if role.read_text()!='test\n':return 'NOT_APPLICABLE'
    selected_path=INPUTS/'selected.json'
    if not selected_path.exists() and not selected_path.is_symlink():return 'NOT_ENROLLED'
    regular(selected_path,0o644)
    envelope=json.loads(selected_path.read_text());selected=envelope['selectedSource']
    # Legacy/unassigned input is not an invitation to invent strict credentials.
    if selected is None:return 'NOT_ENROLLED'
    if not isinstance(selected,dict) or not selected.get('clientCertificateSha256'):raise ValueError('INCOMPLETE_ENROLLMENT')
    if envelope.get('schemaVersion')!=2 or envelope.get('viss')!=dict(uri='wss://10.0.0.1:6443',tlsServerName='127.0.0.1'):
        raise ValueError('SOURCE_BINDING_MISMATCH')
    binding_path=INPUTS/'viss-update-binding';regular(binding_path,0o644)
    binding=json.loads(binding_path.read_text())
    unit=str(UUID(selected['unitId']));node=str(UUID(selected['nodeId']))
    machine=MACHINE.read_text().strip()
    if (binding.get('schemaVersion')!=1 or unit!=selected['unitId'] or node!=selected['nodeId'] or not re.fullmatch('[0-9a-f]{32}',machine)
        or selected.get('role')!='SELECTED_PLATFORM_UNIT' or binding.get('role')!='PLATFORM_UPDATE_RUNTIME'
        or binding.get('unitId')!=unit or binding.get('nodeId')!=machine
        or type(selected.get('assignmentGeneration')) is not int or not 1<=selected['assignmentGeneration']<2**63
        or binding.get('assignmentGeneration')!=selected['assignmentGeneration']):
        raise ValueError('IDENTITY_MISMATCH')
    regular(INPUTS/'viss-update-ca',0o644)
    for name,public in [('selected-platform-unit',selected),('platform-update-runtime',binding)]:
        cert=STORE/name/'client.pem';key=STORE/name/'client-key.pem'
        regular(cert,0o600);regular(key,0o600)
        digest=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
        if digest!=public.get('clientCertificateSha256'):raise ValueError('ENROLLMENT_MISMATCH')
        san=command(['openssl','x509','-in',str(cert),'-noout','-ext','subjectAltName']).splitlines()
        expected='URI:urn:aosedge:demo:viss-client:v1:'+name+':'+unit+':'+node
        if len(san)!=2 or san[1].strip()!=expected:raise ValueError('CERTIFICATE_IDENTITY_MISMATCH')
        if command(['openssl','x509','-in',str(cert),'-pubkey','-noout'])!=command(['openssl','pkey','-in',str(key),'-pubout']):
            raise ValueError('KEY_MISMATCH')
    # Same declarations as the already qualified explicit trust-restore path.
    texts={
      'aos-sm.service': '[Service]\nLoadCredential=viss-update-certificate:'+str(STORE/'platform-update-runtime/client.pem')+'\nLoadCredential=viss-update-private-key:'+str(STORE/'platform-update-runtime/client-key.pem')+'\n',
      'aos-vehicle-data-provider.service': '[Service]\nLoadCredential=viss-client-cert.pem:'+str(STORE/'selected-platform-unit/client.pem')+'\nLoadCredential=viss-client-key.pem:'+str(STORE/'selected-platform-unit/client-key.pem')+'\nLoadCredential=viss-server-ca.pem:'+str(INPUTS/'viss-update-ca')+'\nLoadCredential=viss-selected-source.json:'+str(INPUTS/'selected.json')+'\n'}
    # Preflight both destinations before writing either one.
    for name,text in texts.items():
        path=SYSTEMD/(name+'.d')/'85-democtl-viss-mtls.conf'
        if path.exists() or path.is_symlink():
            regular(path,0o644)
            if path.read_text()!=text:raise ValueError('PROJECTION_CONFLICT')
    changed=False
    for name,text in texts.items():changed=write(SYSTEMD/(name+'.d')/'85-democtl-viss-mtls.conf',text) or changed
    if changed:command(['systemctl','daemon-reload'])
    return 'RESTORED' if changed else 'UNCHANGED'

if __name__=='__main__':
    try:print('VISS_BOOT_PROJECTION_'+restore(),flush=True)
    except Exception as error:
        reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z_]{1,60}',str(error)) else 'FAILED'
        print('VISS_BOOT_PROJECTION_'+reason,flush=True)
        raise SystemExit(1)
