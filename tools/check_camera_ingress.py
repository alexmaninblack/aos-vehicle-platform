#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Authorized ingress source packet; never widens the frozen foundation gate."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
BASE='a80082e278f13d18915b5b5c3da6332c4fd647fd'
FILES={'camera-access/src/aos_camera_access/__main__.py',
    'camera-access/src/aos_camera_access/ingress.py','camera-access/src/aos_camera_access/ingress_main.py',
    'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/files/aos-camera-ingress-launcher.c',
    'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/files/aos-camera-ingress.service',
    'tests/camera_ingress_probe.te','tests/test_camera_ingress.py','tests/test_camera_ingress_entry.py',
    'tools/camera_ingress_compile_worker.py','tools/check_camera_ingress.py','camera-access/README.md'}


def main():
    start=time.monotonic();phases=[]
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'--'],cwd=ROOT,text=True).splitlines()
    changed+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    assert set(changed)<=FILES,'INGRESS_SOURCE_SCOPE_CHANGED'
    for name,args in (
        ('camera-unit',['-m','unittest','discover','-s','tests','-p','test_camera*.py']),
        ('repository-policy',['tools/quality_gate.py']),('retained-telemetry',['tools/validate_contract.py']),
        ('retained-factory',['tools/validate_r6_1_layer.py']),('retained-mainline',['tools/validate_aoscore_mainline.py'])):
        done=subprocess.run([sys.executable,'-B',*args],cwd=ROOT)
        phases.append(dict(stage=name,exit=done.returncode));assert done.returncode==0,'INGRESS_LOCAL_GATE_FAILED'
    print(json.dumps(dict(outcome='PASS_INGRESS_SOURCE_ONLY',phases=phases,seconds=round(time.monotonic()-start,2),
        nativeIngress='NOT_RUN',nativeAosLiveFrames='NOT_RUN',permanentImage='NOT_BUILT')))


if __name__=='__main__':main()
