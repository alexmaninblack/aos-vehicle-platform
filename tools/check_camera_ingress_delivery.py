#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Accepted permanent-delivery source gate; frozen earlier gates stay frozen."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE='99501be'
FILES={
 'qualification/vision-ingress-1.conf',
 'meta-aos-vehicle-platform/recipes-aos-fota/aos-rootfs/aos-rootfs-vision.bb',
 'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/aos-camera-access-platform_0.1.0.bb',
 'meta-aos-vehicle-platform/recipes-security/refpolicy/refpolicy-aos_git.bbappend',
 *('meta-aos-vehicle-platform/recipes-security/refpolicy/files/camera_ingress.'+x for x in ('te','fc','if')),
 'tools/camera_ingress_compile_worker.py','tools/check_camera_ingress_delivery.py',
 'tests/test_camera_ingress_delivery.py','camera-access/README.md'}


def main():
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'--'],cwd=ROOT,text=True).splitlines()
    changed+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    assert set(changed)<=FILES,'PERMANENT_INGRESS_SOURCE_SCOPE_CHANGED'
    for name,args in (
        ('camera-unit',['-m','unittest','discover','-s','tests','-p','test_camera*.py']),
        ('repository-policy',['tools/quality_gate.py']),('retained-telemetry',['tools/validate_contract.py']),
        ('retained-factory',['tools/validate_r6_1_layer.py']),('retained-mainline',['tools/validate_aoscore_mainline.py'])):
        subprocess.run([sys.executable,'-B',*args],cwd=ROOT,check=True)
    print(json.dumps(dict(outcome='PASS_PERMANENT_INGRESS_SOURCE_ONLY',imageBuilt=False,nativeUpdate='NOT_RUN')))


if __name__=='__main__':main()
