# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Fixed internal OEM ingress entry. No URL, key path or user configuration."""
import grp
import os
from pathlib import Path
import pwd
import signal
import stat
import threading

from . import ingress
from .core import require,uuid

CREDENTIALS=Path('/run/credentials/aos-camera-ingress.service')
NAMES={'camera-ca','camera-certificate','camera-private-key','camera-selection'}


def identity():
    user=pwd.getpwnam('aos-camera-access');group=grp.getgrnam('aos-camera-read')
    require(user.pw_uid>0 and group.gr_gid>0 and os.getuid()==os.geteuid()==user.pw_uid
        and os.getgid()==os.getegid()==group.gr_gid,'INGRESS_IDENTITY_INVALID')
    values=dict(v.split(':',1) for v in Path('/proc/self/status').read_text().splitlines() if ':' in v)
    require(values['NoNewPrivs'].strip()=='1' and all(int(values[k].strip(),16)==0 for k in
        ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')),'INGRESS_PRIVILEGE_INVALID')
    context=Path('/proc/self/attr/current').read_text().strip().split(':')
    require(len(context)>=4 and context[2]=='camera_ingress_t','INGRESS_DOMAIN_INVALID')


def credentials():
    require(os.environ.get('CREDENTIALS_DIRECTORY')==str(CREDENTIALS),'INGRESS_CREDENTIAL_OWNER_INVALID')
    require(not any(p.is_symlink() for p in (CREDENTIALS,*CREDENTIALS.parents))
        and {p.name for p in CREDENTIALS.iterdir()}==NAMES,'INGRESS_CREDENTIAL_SET_INVALID')
    for name in NAMES:
        info=(CREDENTIALS/name).lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and 0<info.st_size<16384
            and info.st_uid in (0,os.getuid()) and not info.st_mode&0o077,'INGRESS_CREDENTIAL_UNSAFE')
    selected=ingress.document((CREDENTIALS/'camera-selection').read_bytes())
    require(set(selected)=={'schemaVersion','sourceId','assignmentGeneration','unitId','nodeId','scope'}
        and type(selected['schemaVersion']) is int and selected['schemaVersion']==1
        and selected['scope']=='VISION_CAMERA_READ' and uuid(selected['unitId']) and uuid(selected['nodeId']),
        'INGRESS_SELECTION_INVALID')
    return ingress.Selection(selected['sourceId'],selected['assignmentGeneration'])


def main():
    stopped=threading.Event()
    for name in (signal.SIGTERM,signal.SIGINT):signal.signal(name,lambda *_:stopped.set())
    try:
        identity();selected=credentials()
        context=ingress.tls_context(str(CREDENTIALS/'camera-ca'),str(CREDENTIALS/'camera-certificate'),str(CREDENTIALS/'camera-private-key'))
        # Bounded reconnect uses a fresh authenticated stream/epoch, never
        # reselects the old stream after native Camera component restart.
        while not stopped.is_set():
            try:ingress.connect(context,selected,stopped.is_set)
            except (OSError,ValueError):
                if not stopped.is_set():print('CAMERA_INGRESS_SESSION_UNAVAILABLE',flush=True)
            if stopped.wait(.5):break
        return 0
    except (OSError,ValueError,KeyError):
        print('CAMERA_INGRESS_START_REJECTED',flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
