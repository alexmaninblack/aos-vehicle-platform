# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Fixed internal OEM ingress entry. No URL, key path or user configuration."""
import grp
import errno
import os
from pathlib import Path
import pwd
import signal
import stat
import struct
import threading

from . import ingress
from .core import require,uuid

CREDENTIALS=Path('/run/credentials/aos-camera-ingress.service')
NAMES={'camera-ca','camera-certificate','camera-private-key','camera-selection'}


def credential_access(info,uid,acl,directory=False):
    """systemd 255 root-owned ACL projection, or its owner-only fallback.

    Compare the complete Linux ACL, not just its group-class mask. Root's
    read-only ACL grant for this one UID must never be mistaken for group read.
    """
    permission=5 if directory else 4
    mode=stat.S_IMODE(info.st_mode)
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and (directory or info.st_nlink==1),'INGRESS_CREDENTIAL_UNSAFE')
    if info.st_uid==uid and mode==permission*64 and acl is None:return
    require(info.st_uid==0 and info.st_gid==0 and mode==permission*64+permission*8
        and type(acl) is bytes and len(acl)==44 and struct.unpack('<I',acl[:4])[0]==2,'INGRESS_CREDENTIAL_UNSAFE')
    actual=sorted(struct.iter_unpack('<HHI',acl[4:]));undefined=2**32-1
    expected=sorted(((1,permission,undefined),(2,permission,uid),(4,0,undefined),(16,permission,undefined),(32,0,undefined)))
    require(actual==expected,'INGRESS_CREDENTIAL_ACL_UNSAFE')


def acl(path):
    try:return os.getxattr(path,'system.posix_acl_access')
    except OSError as error:
        require(error.errno in (errno.ENODATA,getattr(errno,'ENOATTR',-1)),'INGRESS_CREDENTIAL_ACL_UNOBSERVABLE')
        return None


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
    mounts=[v.split() for v in Path('/proc/self/mountinfo').read_text().splitlines()]
    selected=[v for v in mounts if v[4]==str(CREDENTIALS)]
    require(len(selected)==1 and 'ro' in selected[0][5].split(',')
        and selected[0][selected[0].index('-')+1] in ('tmpfs','ramfs'),'INGRESS_CREDENTIAL_MOUNT_UNSAFE')
    credential_access(CREDENTIALS.lstat(),os.getuid(),acl(CREDENTIALS),directory=True)
    for name in NAMES:
        info=(CREDENTIALS/name).lstat()
        require(0<info.st_size<16384,'INGRESS_CREDENTIAL_UNSAFE')
        credential_access(info,os.getuid(),acl(CREDENTIALS/name))
    selected=ingress.document((CREDENTIALS/'camera-selection').read_bytes())
    require(set(selected)=={'schemaVersion','sourceId','assignmentGeneration','unitId','nodeId','scope'}
        and type(selected['schemaVersion']) is int and selected['schemaVersion']==1
        and selected['scope']=='VISION_CAMERA_READ' and uuid(selected['unitId']) and uuid(selected['nodeId']),
        'INGRESS_SELECTION_INVALID')
    return ingress.Selection(selected['sourceId'],selected['assignmentGeneration'])


def main():
    stopped=threading.Event()
    for name in (signal.SIGTERM,signal.SIGINT):signal.signal(name,lambda *_:stopped.set())
    stage='IDENTITY'
    try:
        identity();stage='CREDENTIALS';selected=credentials();stage='TLS_CONTEXT'
        context=ingress.tls_context(str(CREDENTIALS/'camera-ca'),str(CREDENTIALS/'camera-certificate'),str(CREDENTIALS/'camera-private-key'))
        # Bounded reconnect uses a fresh authenticated stream/epoch, never
        # reselects the old stream after native Camera component restart.
        while not stopped.is_set():
            try:ingress.connect(context,selected,stopped.is_set)
            except (OSError,ValueError):
                if not stopped.is_set():print('CAMERA_INGRESS_SESSION_UNAVAILABLE',flush=True)
            if stopped.wait(.5):break
        return 0
    except (OSError,ValueError,KeyError) as error:
        # Fixed stages/reason codes only, never library messages or material.
        from .core import CameraError
        reason=str(error) if isinstance(error,CameraError) else type(error).__name__
        print('CAMERA_INGRESS_START_REJECTED_'+stage+'_'+reason,flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
