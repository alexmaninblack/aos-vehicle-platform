# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Strict server-side DTOs; this module grants no resource or source authority."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from uuid import UUID

MAX_RESULT=65536
MAX_REQUEST=4096
MODEL_PROFILE='vision-pilot-fp32-v1'
PREPROCESSING_PROFILE='carla-forward-720p-fov50-v1'
KINDS=('perception','context','assessment','calibration')
BINDING=('componentEpoch','sourceId','sourceEpoch','cameraId','calibrationId')
FRAME=('frame','simulationTimeNs','sensorSimulationTimeNs','sha256')
PRODUCER=('epoch','sequence','serviceVersion')
MODEL_VIEW=[[struct.unpack('f',struct.pack('f',x))[0] for x in row] for row in (
    (.00209514907,-.000941721466,-9.24906396),(.00662758637,-.000352940531,-3.33396502),(.000120077371,-.00411343505,1.))]
CALIBRATION_ORIGIN=dict(repository='https://github.com/autowarefoundation/vision_pilot',revision='e7e5c614832f175f1f9f10a0d0c0df2559ff2c38',
    path='VisionPilot/scripts/find_homography_C_matrix.py',sha256='8998abb376ef213bb0c826b4836e983a5102b06ae8f10932b933c970b3b5b9af')


class Invalid(ValueError):pass


def require(ok,code):
    if not ok:raise Invalid(code)


def fields(value,names):
    require(type(value) is dict and set(value)==set(names),'FIELDS_INVALID')
    return value


def integer(value,minimum=0,maximum=2**63-1):
    require(type(value) is int and minimum<=value<=maximum,'INTEGER_INVALID')
    return value


def number(value,minimum=-float('inf'),maximum=float('inf')):
    require(type(value) in (int,float) and math.isfinite(value) and minimum<=value<=maximum,'NUMBER_INVALID')
    return value


def boolean(value):require(type(value) is bool,'BOOLEAN_INVALID');return value


def identity(value):
    require(type(value) is str,'IDENTITY_INVALID')
    try:require(str(UUID(value))==value,'IDENTITY_INVALID')
    except (ValueError,AttributeError):raise Invalid('IDENTITY_INVALID') from None
    return value


def label(value):
    require(type(value) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value) is not None,'LABEL_INVALID')
    return value


def version(value):
    require(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)',value) is not None,'VERSION_INVALID')
    return value


def binding(value):
    fields(value,BINDING)
    for name in BINDING[:3]:identity(value[name])
    require(value['cameraId']=='front','CAMERA_INVALID');label(value['calibrationId'])
    return value


def frame(value):
    fields(value,FRAME);integer(value['frame']);integer(value['simulationTimeNs']);integer(value['sensorSimulationTimeNs'])
    require(abs(value['simulationTimeNs']-value['sensorSimulationTimeNs'])<=75000000,'SENSOR_WORLD_MISMATCH')
    require(type(value['sha256']) is str and re.fullmatch('[a-f0-9]{64}',value['sha256']) is not None,'DIGEST_INVALID')
    return value


def frames(value):
    require(type(value) is list and len(value)==2,'PAIR_INVALID')
    a,b=map(frame,value)
    require(a['frame']<b['frame'] and 80000000<=b['simulationTimeNs']-a['simulationTimeNs']<=120000000,'PAIR_CADENCE_INVALID')
    require(a['sensorSimulationTimeNs']<b['sensorSimulationTimeNs'],'SENSOR_TIME_REGRESSION')
    return value


def producer(value):
    fields(value,PRODUCER);identity(value['epoch']);integer(value['sequence'],1);version(value['serviceVersion']);return value


def timings(value):
    require(type(value) is dict and 1<=len(value)<=12,'TIMINGS_INVALID')
    for key,item in value.items():label(key);number(item,0,60000)


def vector(value,size,minimum=-float('inf'),maximum=float('inf')):
    require(type(value) is list and len(value)==size,'VECTOR_INVALID')
    for v in value:number(v,minimum,maximum)
    return value


def _nulls(value,names):require(all(value[name] is None for name in names),'INVALID_VALUE_NOT_NULL')


def perception(value):
    fields(value,('schemaVersion','kind','binding','frames','producer','modelProfile','preprocessingProfile','models','timingsMs'))
    common(value,'perception');frames(value['frames']);producer(value['producer'])
    require(value['modelProfile']==MODEL_PROFILE and value['preprocessingProfile']==PREPROCESSING_PROFILE,'MODEL_PROFILE_INCOMPATIBLE')
    models=fields(value['models'],('autodrive','autosteer','autospeed'))
    ad=fields(models['autodrive'],('valid','distanceNormalized','curvatureRaw','presenceProbability'))
    if boolean(ad['valid']):number(ad['distanceNormalized'],0,1);number(ad['curvatureRaw']);number(ad['presenceProbability'],0,1)
    else:_nulls(ad,('distanceNormalized','curvatureRaw','presenceProbability'))
    steer=fields(models['autosteer'],('valid','xp','confidence'))
    # Upstream forwards the raw AutoSteer h_vector (SiLU height/mask), not a
    # sigmoid probability. Preserve finite values and the upstream >=.5 mask.
    if boolean(steer['valid']):vector(steer['xp'],64);vector(steer['confidence'],64)
    else:_nulls(steer,('xp','confidence'))
    speed=fields(models['autospeed'],('valid','detections'))
    if boolean(speed['valid']):
        require(type(speed['detections']) is list and len(speed['detections'])<=128,'DETECTION_LIMIT')
        for row in speed['detections']:
            fields(row,('box','score','classId','probabilities'));box=vector(row['box'],4)
            require(box[2]>box[0] and box[3]>box[1],'BOX_INVALID')
            number(row['score'],0,1);integer(row['classId'],0,3);scores=vector(row['probabilities'],4,0,1)
            require(abs(row['score']-max(scores))<=1e-6 and scores[row['classId']]>=max(scores)-1e-6,'CLASS_SCORE_MISMATCH')
    else:_nulls(speed,('detections',))
    timings(value['timingsMs']);return value


def common(value,kind):
    require(type(value.get('schemaVersion')) is int and value['schemaVersion']==1 and value.get('kind')==kind,'SCHEMA_INVALID')
    binding(value['binding'])


def context(value):
    fields(value,('schemaVersion','kind','binding','frame','dynamics','vehicleProfile','calibration'));common(value,'context');frame(value['frame'])
    calibration_context(value['calibration'],value['binding']['calibrationId'])
    d=fields(value['dynamics'],('available','speedMps','simulationTimeNs'))
    if boolean(d['available']):
        number(d['speedMps'],0,120);integer(d['simulationTimeNs'])
        require(d['simulationTimeNs']==value['frame']['simulationTimeNs'],'CONTEXT_FRAME_TIME_MISMATCH')
    else:_nulls(d,('speedMps','simulationTimeNs'))
    p=fields(value['vehicleProfile'],('id','available','frontAxleToCogM','speedLimitMps'))
    if boolean(p['available']):label(p['id']);number(p['frontAxleToCogM'],.1,10);number(p['speedLimitMps'],.1,120)
    else:_nulls(p,('id','frontAxleToCogM','speedLimitMps'))
    return value


def gateway_context(value,component_epoch):
    """Add only the native epoch supplied by the trusted Source projection."""
    fields(value,('schemaVersion','kind','binding','frame','dynamics','vehicleProfile','calibration'))
    require(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['kind']=='gateway-context','SCHEMA_INVALID')
    fields(value['binding'],BINDING[1:]);identity(component_epoch)
    result=dict(value,kind='context',binding=dict(value['binding'],componentEpoch=component_epoch))
    return context(result)


def matrix(value):
    require(type(value) is list and len(value)==3 and all(type(row) is list and len(row)==3 for row in value),'CALIBRATION_SHAPE_INVALID')
    for row in value:
        for item in row:number(item)
    a,b,c=value;det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
    require(abs(det)>1e-12,'CALIBRATION_SINGULAR');return value


def multiply(a,b):return [[sum(a[i][n]*b[n][k] for n in range(3)) for k in range(3)] for i in range(3)]


def resized_mapping(raw_to_model):
    return multiply(multiply(MODEL_VIEW,raw_to_model),[[1.25,0.,0.],[0.,1.25,80.],[0.,0.,1.]])


def same_homography(a,b):
    left=[v for row in a for v in row];right=[v for row in b for v in row];pivot=max(range(9),key=lambda i:abs(right[i]))
    require(abs(left[pivot])>1e-12 and abs(right[pivot])>1e-12,'CALIBRATION_MAP_INCOMPATIBLE')
    scale=left[pivot]/right[pivot]
    require(max(abs(l-scale*r) for l,r in zip(left,right))<=1e-6*max(1.,max(map(abs,left))),'CALIBRATION_MAP_INCOMPATIBLE')


def calibration_profile(envelope,expected_id):
    fields(envelope,('id','document'));require(type(envelope['document']) is str,'CALIBRATION_DOCUMENT_INVALID')
    raw=envelope['document'].encode('utf-8');require(0<len(raw)<=2048,'CALIBRATION_DOCUMENT_LIMIT')
    require(envelope['id']==expected_id==hashlib.sha256(raw).hexdigest(),'CALIBRATION_DIGEST_MISMATCH')
    value=loads(raw,2048);fields(value,('schemaVersion','profile','scope','camera','modelViewToVehicle','projection','origin'))
    require(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['profile']==PREPROCESSING_PROFILE
        and value['scope']=='PLANAR_REFERENCE_ONLY','CALIBRATION_PROFILE_INVALID')
    camera=fields(value['camera'],('width','height','horizontalFovDegrees','mountTranslationMetres','mountRotationDegrees'))
    require(type(camera['width']) is int and camera['width']==1280 and type(camera['height']) is int and camera['height']==720,'CALIBRATION_CAMERA_INVALID')
    number(camera['horizontalFovDegrees']);vector(camera['mountTranslationMetres'],3);vector(camera['mountRotationDegrees'],3)
    require(camera['horizontalFovDegrees']==50 and all(abs(a-b)<1e-5 for a,b in zip(camera['mountTranslationMetres'],[1.6,0,1.5]))
        and all(abs(v)<1e-5 for v in camera['mountRotationDegrees']),'CALIBRATION_MOUNT_INCOMPATIBLE')
    matrix(value['modelViewToVehicle']);require(value['modelViewToVehicle']==MODEL_VIEW,'MODEL_VIEW_INCOMPATIBLE')
    require(value['origin']==CALIBRATION_ORIGIN,'MODEL_VIEW_PROVENANCE_INVALID')
    projection=fields(value['projection'],('algorithm','coordinates','maximumPlaneResidualMetres','maximumNormalAngleDegrees','referenceDistancesMetres'))
    number(projection['maximumPlaneResidualMetres']);number(projection['maximumNormalAngleDegrees']);vector(projection['referenceDistancesMetres'],4)
    require(projection==dict(algorithm='CARLA_PINHOLE_LOCAL_PLANAR_V1',coordinates='forward-metres-left-positive',maximumPlaneResidualMetres=.02,
        maximumNormalAngleDegrees=.5,referenceDistancesMetres=[15,30,75,150]),'CALIBRATION_PROJECTION_INCOMPATIBLE')
    return value


def calibration_context(value,expected_id,pair=False):
    fields(value,('available','reason','profile','rawToModel','resizedToVehicle'));label(value['reason'])
    if boolean(value['available']):
        require(value['reason']=='CURRENT','CALIBRATION_REASON_INVALID');calibration_profile(value['profile'],expected_id)
        if pair:
            for name in ('rawToModel','resizedToVehicle'):
                require(type(value[name]) is list and len(value[name])==2,'CALIBRATION_PAIR_INVALID')
                for item in value[name]:matrix(item)
            for raw,resized in zip(value['rawToModel'],value['resizedToVehicle']):same_homography(resized,resized_mapping(raw))
        else:
            matrix(value['rawToModel']);matrix(value['resizedToVehicle']);same_homography(value['resizedToVehicle'],resized_mapping(value['rawToModel']))
    else:_nulls(value,('profile','rawToModel','resizedToVehicle'));require(value['reason']!='CURRENT','CALIBRATION_REASON_INVALID')
    return value


def calibration(value):
    fields(value,('schemaVersion','kind','binding','frames','calibration'));common(value,'calibration');frames(value['frames'])
    calibration_context(value['calibration'],value['binding']['calibrationId'],pair=True);return value


def assessment(value):
    fields(value,('schemaVersion','kind','binding','frames','producer','input','state','reason','deltaSimulationNs','lead','path','plan','timingsMs'))
    common(value,'assessment');frames(value['frames']);producer(value['producer'])
    source=fields(value['input'],('epoch','sequence','serviceVersion','modelProfile','preprocessingProfile'))
    producer({k:source[k] for k in PRODUCER})
    require(source['modelProfile']==MODEL_PROFILE and source['preprocessingProfile']==PREPROCESSING_PROFILE,'INPUT_PROFILE_INCOMPATIBLE')
    require(value['state'] in ('WARMING','AVAILABLE','UNAVAILABLE','INCOMPATIBLE'),'STATE_INVALID');label(value['reason'])
    if value['deltaSimulationNs'] is not None:integer(value['deltaSimulationNs'],1,1000000000)
    lead=fields(value['lead'],('valid','present','distanceMetres','relativeSpeedMps','distanceStddevMetres'))
    boolean(lead['valid'])
    if not lead['valid']:_nulls(lead,('present','distanceMetres','relativeSpeedMps','distanceStddevMetres'))
    elif boolean(lead['present']):number(lead['distanceMetres'],0,150);number(lead['relativeSpeedMps'],-120,120);number(lead['distanceStddevMetres'],0,150)
    else:_nulls(lead,('distanceMetres','relativeSpeedMps','distanceStddevMetres'))
    path=fields(value['path'],('valid','points','crossTrackMetres','yawRadians','curvaturePerMetre'))
    if boolean(path['valid']):
        require(type(path['points']) is list and 1<=len(path['points'])<=64,'PATH_LIMIT')
        for point in path['points']:vector(point,2)
        number(path['crossTrackMetres']);number(path['yawRadians'],-math.pi,math.pi);number(path['curvaturePerMetre'])
    else:_nulls(path,('points','crossTrackMetres','yawRadians','curvaturePerMetre'))
    plan=fields(value['plan'],('valid','accelerationMps2','steeringRadians'))
    if boolean(plan['valid']):
        require(value['state']=='AVAILABLE' and lead['valid'] and path['valid'],'PLAN_INPUT_INVALID')
        number(plan['accelerationMps2']);require(type(plan['steeringRadians']) is list and 1<=len(plan['steeringRadians'])<=64,'PLAN_LIMIT')
        for angle in plan['steeringRadians']:number(angle,-math.pi/2,math.pi/2)
    else:_nulls(plan,('accelerationMps2','steeringRadians'))
    if value['state']!='AVAILABLE':require(not lead['valid'] and not path['valid'] and not plan['valid'],'UNAVAILABLE_HAS_VALID_ESTIMATE')
    timings(value['timingsMs']);return value


def validate(value):
    require(type(value) is dict and value.get('kind') in KINDS,'KIND_INVALID')
    return {'perception':perception,'context':context,'assessment':assessment,'calibration':calibration}[value['kind']](value)


def unique(rows):
    out={}
    for key,value in rows:require(key not in out,'DUPLICATE_FIELD');out[key]=value
    return out


def loads(raw,maximum=MAX_RESULT):
    require(type(raw) is bytes and 0<len(raw)<=maximum,'MESSAGE_LIMIT')
    try:return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('NONFINITE_NUMBER')))
    except (UnicodeError,json.JSONDecodeError,RecursionError,OverflowError) as error:raise Invalid('JSON_INVALID') from error


def dumps(value,maximum=MAX_RESULT):
    try:raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
    except (ValueError,TypeError,RecursionError) as error:raise Invalid('JSON_INVALID') from error
    require(0<len(raw)<=maximum,'MESSAGE_LIMIT');return raw


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def load_profile(root):
    record=json.loads((Path(root)/'dependencies/integration-contract.json').read_bytes())
    raw=(Path(root)/record['projectionPath']).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==record['projectionSha256'],'CONTRACT_CHANGED')
    return json.loads(raw)
