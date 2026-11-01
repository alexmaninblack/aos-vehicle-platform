# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Synthetic exchange contracts only; native resource permissions are separate."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
for parent in ('camera-access/src','camera-access/shared'):sys.path.insert(0,str(ROOT/parent))
from aos_vision_exchange.core import Exchange
from vision_common import protocol as p


def uid(n):return str(UUID(int=n))
def binding():return dict(componentEpoch=uid(1),sourceId=uid(2),sourceEpoch=uid(3),cameraId='front',calibrationId='unit-calibration')
def frame(n):return dict(frame=n,simulationTimeNs=n*100000000,sensorSimulationTimeNs=n*100000000,sha256='a'*64)
def raw(n=2,seq=1):
    return dict(schemaVersion=1,kind='perception',binding=binding(),frames=[frame(n-1),frame(n)],producer=dict(epoch=uid(4),sequence=seq,serviceVersion='0.1.0'),
        modelProfile=p.MODEL_PROFILE,preprocessingProfile=p.PREPROCESSING_PROFILE,
        models=dict(autodrive=dict(valid=False,distanceNormalized=None,curvatureRaw=None,presenceProbability=None),
            autosteer=dict(valid=False,xp=None,confidence=None),autospeed=dict(valid=False,detections=None)),timingsMs=dict(total=1.))


def calibrated_profile():
    value=dict(schemaVersion=1,profile=p.PREPROCESSING_PROFILE,scope='PLANAR_REFERENCE_ONLY',
        camera=dict(width=1280,height=720,horizontalFovDegrees=50.,mountTranslationMetres=[1.6,0.,1.5],mountRotationDegrees=[0.,0.,0.]),
        modelViewToVehicle=p.MODEL_VIEW,origin=p.CALIBRATION_ORIGIN,
        projection=dict(algorithm='CARLA_PINHOLE_LOCAL_PLANAR_V1',coordinates='forward-metres-left-positive',
            maximumPlaneResidualMetres=.02,maximumNormalAngleDegrees=.5,referenceDistancesMetres=[15,30,75,150]))
    document=json.dumps(value,separators=(',',':'))
    return dict(id=hashlib.sha256(document.encode()).hexdigest(),document=document)


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        self.now=1.;self.posts=[];self.known=True
        self.broker=Exchange(uid(2),uid(1),self.context,self.publish,clock=lambda:self.now,epoch=uid(8))
    def context(self,source,epoch,n):
        if not self.known:return None
        return dict(schemaVersion=1,kind='gateway-context',binding={k:v for k,v in binding().items() if k!='componentEpoch'},frame=frame(n),
            dynamics=dict(available=False,speedMps=None,simulationTimeNs=None),vehicleProfile=dict(id=None,available=False,frontAxleToCogM=None,speedLimitMps=None),
            calibration=dict(available=False,reason='PLANE_UNAVAILABLE',profile=None,rawToModel=None,resizedToVehicle=None))
    def publish(self,value):self.posts.append(value);return True
    def send(self,kind,value):
        return self.broker.request(kind+'-publish',dict(schemaVersion=1,operation='publish',exchangeEpoch=uid(8),payloadBytes=len(p.dumps(value))),value)
    def latest(self,**extra):
        return self.broker.request('perception-read',dict(schemaVersion=1,operation='latest',exchangeEpoch=uid(8),afterEpoch=None,afterSequence=0,**extra))

    def test_latest_replace_not_fifo_and_expire_does_not_retimestamp_duplicate(self):
        first=raw();self.send('perception',first);self.assertEqual(self.latest()[1],first)
        self.now+=1.1;self.assertEqual(self.latest()[0]['state'],'UNAVAILABLE')
        self.assertEqual(self.send('perception',first)[0]['reason'],'IDEMPOTENT');self.assertIsNone(self.latest()[1])
        self.send('perception',raw(4,2));self.send('perception',raw(6,3));self.assertEqual(self.latest()[1]['producer']['sequence'],3)
        self.assertEqual(self.broker.replaced,1)

    def test_replay_conflict_kind_role_unknown_fields_denied(self):
        self.send('perception',raw())
        conflict=raw();conflict['timingsMs']['total']=2.
        for value in (conflict,raw(4,0),raw(2,2)):
            with self.assertRaises(p.Invalid):self.send('perception',value)
        with self.assertRaises(p.Invalid):self.send('assessment',raw())
        with self.assertRaises(p.Invalid):self.broker.request('context-read',dict(schemaVersion=1,operation='publish'))
        with self.assertRaises(p.Invalid):self.broker.request('perception-read',dict(schemaVersion=1,operation='status',url='http://invalid'))

    def test_authentic_frame_hash_binding_and_component_epoch(self):
        for key,value in (('sourceId',uid(9)),('componentEpoch',uid(9)),('sourceEpoch',uid(9))):
            row=raw();row['binding'][key]=value
            with self.assertRaises(p.Invalid):self.send('perception',row)
        row=raw();row['frames'][0]['sha256']='b'*64
        with self.assertRaises(p.Invalid):self.send('perception',row)
        self.known=False
        with self.assertRaises(p.Invalid):self.send('perception',raw())

    def test_context_cache_bounded_and_close_clears(self):
        for n in range(180):self.broker.context(binding(),frame(n))
        self.assertEqual(len(self.broker.contexts),128)
        self.send('perception',raw());self.broker.close();self.assertIsNone(self.broker.raw);self.assertFalse(self.broker.contexts)
        with self.assertRaises(p.Invalid):self.latest()

    def test_calibration_status_is_pair_bound_and_has_no_dynamics(self):
        request=dict(schemaVersion=1,operation='status',binding=binding(),frames=[frame(1),frame(2)])
        header,value=self.broker.request('perception-publish',request)
        self.assertEqual(header['state'],'CALIBRATION');self.assertFalse(value['calibration']['available'])
        p.calibration(value);self.assertNotIn('dynamics',value)
        for role in ('perception-read','context-read','assessment-publish'):
            with self.assertRaises(p.Invalid):self.broker.request(role,request)

    def test_positive_calibration_uses_each_capture_and_same_assessment_profile(self):
        profile=calibrated_profile();selected=dict(binding(),calibrationId=profile['id'])
        def context(source,epoch,n):
            value=self.context(source,epoch,n);value['binding']=dict(selected);del value['binding']['componentEpoch']
            # Deliberately different per-frame maps: using the current frame
            # twice must not satisfy the captured pair's calibration proof.
            mapping=[[1.,0.,float(n)],[0.,1.,0.],[0.,0.,1.]]
            value['calibration']=dict(available=True,reason='CURRENT',profile=profile,rawToModel=mapping,resizedToVehicle=p.resized_mapping(mapping))
            value['dynamics']=dict(available=True,speedMps=10.,simulationTimeNs=frame(n)['simulationTimeNs'])
            return value
        self.broker.fetch=context
        request=dict(schemaVersion=1,operation='status',binding=selected,frames=[frame(1),frame(2)])
        header,value=self.broker.request('perception-publish',request);p.calibration(value)
        self.assertEqual(header['reason'],'CURRENT');self.assertNotIn('dynamics',value)
        self.assertEqual(value['calibration']['rawToModel'][0][0][2],1.)
        self.assertEqual(value['calibration']['rawToModel'][1][0][2],2.)
        self.assertLessEqual(len(p.dumps(value)),4096)
        _,assessment_context=self.broker.request('context-read',dict(schemaVersion=1,operation='context',exchangeEpoch=uid(8),binding=selected,frame=frame(2)))
        self.assertEqual(assessment_context['calibration']['profile'],value['calibration']['profile'])
        self.assertEqual(assessment_context['calibration']['rawToModel'],value['calibration']['rawToModel'][1])
        self.assertEqual(assessment_context['dynamics']['speedMps'],10.)
        inference=raw();inference['binding']=selected
        inference['models']['autodrive']=dict(valid=True,distanceNormalized=.5,curvatureRaw=0.,presenceProbability=.9)
        self.assertEqual(self.send('perception',inference)[0]['state'],'ACCEPTED')

    def test_calibration_profile_tamper_and_inconsistent_fusion_map_denied(self):
        profile=calibrated_profile();selected=dict(binding(),calibrationId=profile['id'])
        for tamper in ('profile','fusion'):
            def context(source,epoch,n):
                value=self.context(source,epoch,n);value['binding']=dict(selected);del value['binding']['componentEpoch']
                mapping=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
                value['calibration']=dict(available=True,reason='CURRENT',profile=copy.deepcopy(profile),rawToModel=mapping,resizedToVehicle=p.resized_mapping(mapping))
                if tamper=='profile':value['calibration']['profile']['document']+=' '
                else:value['calibration']['resizedToVehicle']=p.MODEL_VIEW
                return value
            self.broker.fetch=context
            with self.assertRaises(p.Invalid):
                self.broker.request('perception-publish',dict(schemaVersion=1,operation='status',binding=selected,frames=[frame(1),frame(2)]))

    def test_assessment_exact_input_and_one_gateway_post(self):
        source=raw();self.send('perception',source)
        result=dict(schemaVersion=1,kind='assessment',binding=binding(),frames=source['frames'],producer=dict(epoch=uid(5),sequence=1,serviceVersion='0.1.0'),
            input=dict(source['producer'],modelProfile=p.MODEL_PROFILE,preprocessingProfile=p.PREPROCESSING_PROFILE),state='WARMING',reason='FIRST_INPUT',deltaSimulationNs=None,
            lead=dict(valid=False,present=None,distanceMetres=None,relativeSpeedMps=None,distanceStddevMetres=None),
            path=dict(valid=False,points=None,crossTrackMetres=None,yawRadians=None,curvaturePerMetre=None),
            plan=dict(valid=False,accelerationMps2=None,steeringRadians=None),timingsMs=dict(total=1.))
        bad=copy.deepcopy(result);bad['input']['sequence']=8
        with self.assertRaises(p.Invalid):self.send('assessment',bad)
        self.send('assessment',result);self.send('assessment',result);self.assertEqual(len(self.posts),1)
        self.now+=1.1;self.broker.expire();self.assertIsNone(self.broker.interpreted)


if __name__=='__main__':unittest.main()
