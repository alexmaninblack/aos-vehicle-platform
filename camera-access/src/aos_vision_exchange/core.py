# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Bounded typed exchange. Kernel resource/peer checks are the daemon's gate.

No sockets, TLS keys, model/Cloud/control calls or file I/O here. The owner
injects only the authenticated selected Gateway context/result operations.
"""
from collections import OrderedDict
import copy
import time
from uuid import uuid4
from vision_common import protocol as p

ROLES={'perception-publish':('status','publish'),'perception-read':('status','latest'),
    'context-read':('status','context'),'assessment-publish':('status','publish')}


class Exchange:
    def __init__(self,source_id,component_epoch,context_fetch,result_publish,clock=time.monotonic,epoch=None):
        p.identity(source_id);p.identity(component_epoch)
        self.source=source_id;self.component=component_epoch;self.fetch=context_fetch;self.post=result_publish
        self.clock=clock;self.epoch=epoch or str(uuid4());p.identity(self.epoch);self.active=True
        self.contexts=OrderedDict();self.raw=None;self.interpreted=None;self.raw_at=0.;self.interpreted_at=0.
        self.marks={};self.binding=None;self.replaced=0;self.rejected=0

    def close(self):
        self.active=False;self.raw=None;self.interpreted=None;self.contexts.clear()

    def expire(self):
        now=self.clock()
        if now-self.raw_at>1:self.raw=None
        if now-self.interpreted_at>1:self.interpreted=None
        for key,(_,at) in list(self.contexts.items()):
            if now-at>1:del self.contexts[key]

    def response(self,state,reason):
        return dict(schemaVersion=1,exchangeEpoch=self.epoch,state=state,reason=reason)

    def context(self,binding,frame):
        p.binding(binding);p.frame(frame)
        p.require(binding['sourceId']==self.source and binding['componentEpoch']==self.component,'NATIVE_SELECTION_MISMATCH')
        key=p.digest(dict(binding=binding,frame=frame))
        if key in self.contexts:return self.contexts[key][0]
        wire=self.fetch(binding['sourceId'],binding['sourceEpoch'],frame['frame'])
        if wire is None:return None
        value=p.gateway_context(wire,self.component)
        p.require(value['binding']==binding and value['frame']==frame,'AUTHENTICATED_CAPTURE_MISMATCH')
        self.contexts[key]=(copy.deepcopy(value),self.clock())
        while len(self.contexts)>128:self.contexts.popitem(last=False)
        return value

    def mark(self,kind,value):
        """Last semantic identity plus capture high-water survives display expiry."""
        producer=value['producer'];current=value['frames'][-1];digest=p.digest(value);previous=self.marks.get(kind)
        if previous:
            old,old_digest=previous
            if producer['epoch']==old['epoch']:
                if producer['sequence']==old['sequence']:
                    p.require(digest==old_digest,'PRODUCER_IDENTITY_CONFLICT');return False
                p.require(producer['sequence']>old['sequence'],'PRODUCER_REPLAY')
            if value['binding']==old['binding']:
                p.require(current['frame']>old['frame'] and current['simulationTimeNs']>old['time'],'CAPTURE_REPLAY')
        return True

    def remember(self,kind,value):
        producer=value['producer'];frame=value['frames'][-1]
        self.marks[kind]=(dict(producer,binding=copy.deepcopy(value['binding']),frame=frame['frame'],time=frame['simulationTimeNs']),p.digest(value))

    def request(self,role,request,value=None):
        self.expire();p.require(self.active,'EXCHANGE_DETACHED')
        p.require(role in ROLES,'RESOURCE_ROLE_INVALID');p.require(type(request) is dict,'FIELDS_INVALID')
        operation=request.get('operation');p.require(operation in ROLES[role],'RESOURCE_OPERATION_DENIED')
        base=('schemaVersion','operation')
        captured=operation=='status' and ('binding' in request or 'frames' in request)
        wanted=(base+('binding','frames') if captured else base) if operation=='status' else base+('exchangeEpoch',)+{
            'publish':('payloadBytes',),'latest':('afterEpoch','afterSequence'),'context':('binding','frame')}[operation]
        p.fields(request,wanted);p.require(type(request['schemaVersion']) is int and request['schemaVersion']==1,'SCHEMA_INVALID')
        if operation=='status':
            if not captured:return self.response('STATUS','READY'),None
            p.require(role=='perception-publish','RESOURCE_OPERATION_DENIED');p.binding(request['binding']);p.frames(request['frames'])
            rows=[self.context(request['binding'],frame) for frame in request['frames']]
            available=all(row is not None and row['calibration']['available'] for row in rows)
            if available:
                a,b=[row['calibration'] for row in rows];p.require(a['profile']==b['profile'],'CALIBRATION_PROFILE_MISMATCH')
                calibration=dict(available=True,reason='CURRENT',profile=a['profile'],rawToModel=[a['rawToModel'],b['rawToModel']],resizedToVehicle=[a['resizedToVehicle'],b['resizedToVehicle']])
            else:calibration=dict(available=False,reason='CALIBRATION_UNAVAILABLE',profile=None,rawToModel=None,resizedToVehicle=None)
            value=dict(schemaVersion=1,kind='calibration',binding=request['binding'],frames=request['frames'],calibration=calibration)
            p.calibration(value);p.dumps(value,p.MAX_REQUEST)
            return self.response('CALIBRATION','CURRENT' if available else 'CALIBRATION_UNAVAILABLE'),value
        p.require(request['exchangeEpoch']==self.epoch,'EXCHANGE_EPOCH_MISMATCH')
        if operation=='latest':
            if request['afterEpoch'] is None:p.require(request['afterSequence']==0,'CURSOR_INVALID')
            else:p.identity(request['afterEpoch']);p.integer(request['afterSequence'],1)
            if self.raw is None:return self.response('UNAVAILABLE','PERCEPTION_UNAVAILABLE'),None
            cursor=self.raw['producer']
            if request['afterEpoch']==cursor['epoch'] and request['afterSequence']>=cursor['sequence']:
                return self.response('UNCHANGED','NO_NEW_RESULT'),None
            return self.response('RESULT','CURRENT'),copy.deepcopy(self.raw)
        if operation=='context':
            context=self.context(request['binding'],request['frame'])
            return (self.response('CONTEXT','CURRENT'),context) if context else (self.response('UNAVAILABLE','CONTEXT_UNAVAILABLE'),None)
        p.integer(request['payloadBytes'],1,p.MAX_RESULT);p.require(len(p.dumps(value))==request['payloadBytes'],'PAYLOAD_LENGTH_MISMATCH')
        kind='perception' if role=='perception-publish' else 'assessment';p.validate(value);p.require(value['kind']==kind,'RESOURCE_KIND_DENIED')
        # Never retimestamp/revive an idempotent duplicate after expiry.
        if not self.mark(kind,value):return self.response('ACCEPTED','IDEMPOTENT'),None
        contexts=[self.context(value['binding'],frame) for frame in value['frames']]
        p.require(all(row is not None for row in contexts),'CONTEXT_CAPTURE_UNAVAILABLE')
        if (kind=='perception' and any(v['valid'] for v in value['models'].values())) or (kind=='assessment' and any(value[key]['valid'] for key in ('lead','path','plan'))):
            p.require(all(row['calibration']['available'] for row in contexts),'CALIBRATION_UNAVAILABLE')
        if kind=='perception':
            if self.raw is not None:self.replaced+=1
            if self.binding!=value['binding']:self.interpreted=None
            self.binding=copy.deepcopy(value['binding']);self.raw=copy.deepcopy(value);self.raw_at=self.clock()
        else:
            p.require(self.raw is not None and self.raw['binding']==value['binding'] and self.raw['frames']==value['frames'],'ASSESSMENT_INPUT_UNAVAILABLE')
            expected=dict(self.raw['producer'],modelProfile=self.raw['modelProfile'],preprocessingProfile=self.raw['preprocessingProfile'])
            p.require(value['input']==expected,'ASSESSMENT_INPUT_MISMATCH')
            p.require(self.post(copy.deepcopy(value)) is True,'GATEWAY_RESULT_UNCONFIRMED')
            self.interpreted=copy.deepcopy(value);self.interpreted_at=self.clock()
        self.remember(kind,value);return self.response('ACCEPTED','CURRENT'),None
