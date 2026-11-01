# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Fixed selected Source HTTPS adapter, no URL, proxy, redirect or control API."""
import socket
import time
from vision_common import protocol as p


class Gateway:
    def __init__(self,tls):self.tls=tls;self.deadline=None

    def exchange(self,method,path,value=None):
        end=self.deadline or time.monotonic()+2
        def timeout(connection):
            left=end-time.monotonic();p.require(left>0,'GATEWAY_DEADLINE');connection.settimeout(left)
        p.require(end>time.monotonic(),'GATEWAY_DEADLINE')
        body=b'' if value is None else p.dumps(value)
        request=(method+' '+path+' HTTP/1.1\r\nHost: 127.0.0.1:6443\r\nConnection: close\r\n'
            +('Content-Type: application/json\r\nContent-Length: '+str(len(body))+'\r\n' if body else '')+'\r\n').encode('ascii')+body
        with socket.create_connection(('10.0.0.1',6443),timeout=end-time.monotonic()) as tcp:
            timeout(tcp)
            with self.tls.wrap_socket(tcp,server_hostname='127.0.0.1') as connection:
                timeout(connection);connection.sendall(request);pending=bytearray()
                def line():
                    while b'\n' not in pending:
                        p.require(len(pending)<8192,'GATEWAY_HEADER_LIMIT');timeout(connection)
                        block=connection.recv(1);p.require(bool(block),'GATEWAY_TRUNCATED');pending.extend(block)
                    raw=bytes(pending);pending.clear();p.require(raw.endswith(b'\r\n'),'GATEWAY_HTTP_INVALID');return raw[:-2]
                status=line().split(b' ');p.require(len(status)>=3 and status[0]==b'HTTP/1.1' and status[1].isdigit(),'GATEWAY_HTTP_INVALID')
                headers={};total=0
                for _ in range(16):
                    row=line();total+=len(row);p.require(total<=8192,'GATEWAY_HEADER_LIMIT')
                    if not row:break
                    p.require(b':' in row and row[:1] not in (b' ',b'\t'),'GATEWAY_HEADER_INVALID');key,v=row.split(b':',1);key=key.lower()
                    p.require(key not in headers,'GATEWAY_HEADER_DUPLICATE');headers[key]=v.strip()
                else:raise p.Invalid('GATEWAY_HEADER_LIMIT')
                p.require(set(headers)=={b'content-type',b'content-length',b'connection',b'cache-control'}
                    and headers[b'content-type']==b'application/json' and headers[b'connection']==b'close' and headers[b'cache-control']==b'no-store','GATEWAY_RESPONSE_INVALID')
                length=headers[b'content-length'];p.require(length.isdigit() and len(length)<=5 and str(int(length)).encode()==length,'GATEWAY_LENGTH_INVALID')
                size=p.integer(int(length),1,p.MAX_REQUEST);raw=bytearray()
                while len(raw)<size:
                    timeout(connection);part=connection.recv(size-len(raw));p.require(bool(part),'GATEWAY_TRUNCATED');raw.extend(part)
                timeout(connection);return int(status[1]),p.loads(bytes(raw),p.MAX_REQUEST)

    def context(self,source,epoch,frame):
        p.identity(source);p.identity(epoch);p.integer(frame)
        status,value=self.exchange('GET','/vision/v1/context?sourceId='+source+'&sourceEpoch='+epoch+'&frame='+str(frame))
        if status in (404,409,503):return None
        p.require(status==200,'GATEWAY_CONTEXT_REJECTED');return value

    def publish(self,value):
        p.assessment(value);status,result=self.exchange('POST','/vision/v1/results',value)
        p.fields(result,('schemaVersion','state','reason'))
        p.require(type(result['schemaVersion']) is int and result['schemaVersion']==1 and result['state']=='ACCEPTED'
            and result['reason'] in ('CURRENT','IDEMPOTENT') and status in (200,202),'GATEWAY_RESULT_REJECTED');return True
