#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Exact accepted Vision-services delta; do not reopen the frozen ingress gate."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
BASE='1736e189'
FILES={
 'camera-access/src/aos_camera_access/vision_image.py',
 'contracts/camera-access/native-services-profile.json',
 'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/aos-camera-access-platform_0.1.0.bb',
 'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/files/36-vision-image-storage.conf',
 'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/files/aos-vision-exchange.conf',
 'meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager/aos-communicationmanager_git.bbappend',
 'meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/aos-servicemanager_git.bbappend',
 'meta-aos-vehicle-platform/recipes-core/images/aos-image-vision.bb',
 'meta-aos-vehicle-platform/recipes-security/refpolicy/refpolicy-aos_git.bbappend',
 'qualification/vision-services-1.conf',
 *('tests/fixtures/vision-native-exchange/vision_exchange.'+x for x in ('te','fc','if')),
 'tests/test_vision_native_profile.py','tests/test_vision_resource_capacity.py',
 'tools/vision_resource_capacity_compile_worker.py','tools/check_vision_services_delivery.py'}


def main():
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'--'],cwd=ROOT,text=True).splitlines()
    changed+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    assert set(changed)<=FILES,'VISION_SERVICES_SOURCE_SCOPE_CHANGED'
    for args in (['-m','unittest','discover','-s','tests','-p','test_camera*.py'],
        ['-m','unittest','discover','-s','tests','-p','test_vision*.py'],
        ['tools/quality_gate.py'],['tools/validate_contract.py'],['tools/validate_r6_1_layer.py'],['tools/validate_aoscore_mainline.py']):
        subprocess.run([sys.executable,'-B',*args],cwd=ROOT,check=True)
    print(json.dumps(dict(outcome='PASS_VISION_SERVICES_SOURCE_ONLY',imageBuilt=False,mainProfileUnchanged=True)))


if __name__=='__main__':main()
