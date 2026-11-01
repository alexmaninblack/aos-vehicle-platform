# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Four fixed role sockets under native DAC/peer/SELinux policy. No TCP bind."""
import grp
import os
from pathlib import Path
import pwd
import signal
import socket
import stat
import struct
import threading
import time
from vision_common import ipc,protocol as p
from aos_camera_access.ingress_main import credential_access,acl
from aos_camera_access.ingress import tls_context
from .core import Exchange,ROLES
from .transport import Gateway

ROOT=Path('/run/aos-vision-exchange')
CREDENTIALS=Path('/run/credentials/aos-vision-exchange.service')
USER='aos-vision-exchange'
NAMES={'vision-ca','vision-certificate','vision-private-key','vision-selection'}


def identity():
    uid=pwd.getpwnam(USER).pw_uid;gid=grp.getgrnam(USER).gr_gid
    p.require(uid>0 and gid>0 and os.getuid()==os.geteuid()==uid and os.getgid()==os.getegid()==gid,'EXCHANGE_IDENTITY_INVALID')
    roles={grp.getgrnam('aos-vision-'+role).gr_gid for role in ROLES}
    p.require(set(os.getgroups())<=roles|{gid},'EXCHANGE_GROUPS_INVALID')
    values=dict(row.split(':',1) for row in Path('/proc/self/status').read_text().splitlines() if ':' in row)
    p.require(values['NoNewPrivs'].strip()=='1' and all(int(values[k].strip(),16)==0 for k in
        ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')),'EXCHANGE_PRIVILEGE_INVALID')
    label=Path('/proc/self/attr/current').read_text().strip().split(':')
    p.require(len(label)>=4 and label[2]=='vision_exchange_t','EXCHANGE_DOMAIN_INVALID');return uid


def credentials():
    p.require(os.environ.get('CREDENTIALS_DIRECTORY')==str(CREDENTIALS),'EXCHANGE_CREDENTIAL_OWNER_INVALID')
    p.require(not any(path.is_symlink() for path in (CREDENTIALS,*CREDENTIALS.parents))
        and {path.name for path in CREDENTIALS.iterdir()}==NAMES,'EXCHANGE_CREDENTIAL_SET_INVALID')
    mounts=[v.split() for v in Path('/proc/self/mountinfo').read_text().splitlines()]
    selected=[v for v in mounts if v[4]==str(CREDENTIALS)]
    p.require(len(selected)==1 and 'ro' in selected[0][5].split(',')
        and selected[0][selected[0].index('-')+1] in ('tmpfs','ramfs'),'EXCHANGE_CREDENTIAL_MOUNT_UNSAFE')
    credential_access(CREDENTIALS.lstat(),os.getuid(),acl(CREDENTIALS),directory=True)
    for name in NAMES:
        path=CREDENTIALS/name;info=path.lstat();p.require(0<info.st_size<16384,'EXCHANGE_CREDENTIAL_UNSAFE')
        credential_access(info,os.getuid(),acl(path))
    selected=p.loads((CREDENTIALS/'vision-selection').read_bytes(),p.MAX_REQUEST)
    p.fields(selected,('schemaVersion','sourceId','assignmentGeneration','unitId','nodeId','componentEpoch','scopes'))
    p.require(type(selected['schemaVersion']) is int and selected['schemaVersion']==1
        and selected['scopes']==['vision-context-read','vision-assessment-publish'],'EXCHANGE_SELECTION_INVALID')
    for key in ('sourceId','unitId','nodeId','componentEpoch'):p.identity(selected[key])
    p.integer(selected['assignmentGeneration'],1);return selected


class Server:
    def __init__(self,exchange,gateway,uid):
        self.exchange=exchange;self.gateway=gateway;self.uid=uid;self.stop=threading.Event();self.lock=threading.Lock()

    def serve(self,listener,role):
        while not self.stop.is_set():
            try:connection,_=listener.accept()
            except socket.timeout:continue
            with connection:
                deadline=time.monotonic()+2
                try:
                    pid,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    p.require(pid>0 and uid not in (0,self.uid),'EXCHANGE_PEER_DENIED')
                    request=ipc.receive(connection,deadline,p.MAX_REQUEST);value=None
                    # Framing does not authorize operation or role. Check both
                    # before accepting the independently bounded DTO body.
                    p.require(type(request) is dict and request.get('operation') in ROLES[role],'RESOURCE_OPERATION_DENIED')
                    if request['operation']=='publish':
                        p.integer(request.get('payloadBytes'),1,p.MAX_RESULT);value=ipc.receive(connection,deadline,p.MAX_RESULT)
                    p.require(self.lock.acquire(timeout=max(0,deadline-time.monotonic())),'EXCHANGE_DEADLINE')
                    try:
                        p.require(deadline>time.monotonic(),'EXCHANGE_DEADLINE');self.gateway.deadline=deadline
                        header,body=self.exchange.request(role,request,value)
                    finally:self.gateway.deadline=None;self.lock.release()
                    ipc.send(connection,header,deadline,p.MAX_REQUEST)
                    if body is not None:ipc.send(connection,body,deadline,p.MAX_RESULT if role=='perception-read' else p.MAX_REQUEST)
                except (p.Invalid,OSError,ValueError,KeyError,TypeError):
                    self.exchange.rejected+=1
                    try:ipc.send(connection,self.exchange.response('REJECTED','REQUEST_REJECTED'),deadline,p.MAX_REQUEST)
                    except (p.Invalid,OSError):pass

    def run(self):
        sockets=[];threads=[]
        try:
            for role in ROLES:
                parent=ROOT/role;info=parent.lstat();gid=grp.getgrnam('aos-vision-'+role).gr_gid
                p.require(stat.S_ISDIR(info.st_mode) and info.st_uid==self.uid and info.st_gid==gid
                    and stat.S_IMODE(info.st_mode)==0o750,'EXCHANGE_SOCKET_PARENT_INVALID')
                path=parent/'exchange.sock';p.require(not path.exists() and not path.is_symlink(),'EXCHANGE_SOCKET_CONFLICT')
                listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));os.chown(path,-1,gid);os.chmod(path,0o660)
                listener.listen(1);listener.settimeout(.2);sockets.append((listener,path))
                worker=threading.Thread(target=self.serve,args=(listener,role));worker.start();threads.append(worker)
            self.stop.wait()
        finally:
            self.stop.set()
            for worker in threads:worker.join(timeout=3)
            with self.lock:self.exchange.close()
            for listener,path in sockets:listener.close();path.unlink(missing_ok=True)


def main():
    try:
        p.require(os.uname().sysname=='Linux','LINUX_TARGET_REQUIRED');uid=identity();selected=credentials()
        context=tls_context(str(CREDENTIALS/'vision-ca'),str(CREDENTIALS/'vision-certificate'),str(CREDENTIALS/'vision-private-key'))
        gateway=Gateway(context);exchange=Exchange(selected['sourceId'],selected['componentEpoch'],gateway.context,gateway.publish)
        server=Server(exchange,gateway,uid)
        for name in (signal.SIGINT,signal.SIGTERM):signal.signal(name,lambda *_:server.stop.set())
        server.run();return 0
    except (p.Invalid,OSError,ValueError,KeyError):
        print('VISION_EXCHANGE_START_REJECTED',flush=True);return 1


if __name__=='__main__':raise SystemExit(main())
