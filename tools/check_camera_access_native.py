#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""One offline native Camera Access source gate, preserving the Main selectors."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
FOUNDATION='2b2322d237eb62a0207729ed86df785ed84e5534'
FILES={'README.md','docs/architecture.md','tests/test_camera_access_native.py','tools/check_camera_access_native.py',
       'qualification/vision-bootstrap-1.conf',
       'tools/camera_native_compile_worker.py','tools/camera_native_primitives_worker.py',
       'tools/build_camera_access_payload.py',
       'meta-aos-vehicle-platform/recipes-core/images/aos-image-vision.bb',
       'meta-aos-vehicle-platform/recipes-security/refpolicy/refpolicy-aos_git.bbappend'}
RUNTIME='meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/systemd-slot-component/'
FILES.update(RUNTIME+s for s in ('config.cpp','config.hpp','runtime.cpp','tests/runtime.cpp',
                               'providerarchive.hpp','tests/providerarchive.cpp'))
PREFIXES=('camera-access/','contracts/camera-access/',
          'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/',
          'meta-aos-vehicle-platform/recipes-security/refpolicy/files/camera_access.')


def main():
    start=time.monotonic()
    result=dict(scenario='CAMERA_ACCESS_NATIVE_SOURCE',outcome='FAIL',phases=[],
                m4NativeActivation='NOT_RUN',nativeAosResource='NOT_RUN',gatewayIngress='NOT_RUN')
    try:
        changed=subprocess.check_output(['git','diff','--name-only',FOUNDATION,'--'],cwd=ROOT,text=True).splitlines()
        changed+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
        assert all(p in FILES or p.startswith(PREFIXES) for p in changed),'NATIVE_PACKET_SCOPE_CHANGED'
        for name,args in (
            ('camera-unit-contract',['-m','unittest','discover','-s','tests','-p','test_camera_access*.py']),
            ('repository-policy',['tools/quality_gate.py']),
            ('retained-telemetry',['tools/validate_contract.py']),
            ('retained-factory-layer',['tools/validate_r6_1_layer.py']),
            ('retained-mainline',['tools/validate_aoscore_mainline.py']),
        ):
            print(json.dumps(dict(stage=name,state='STARTED')),flush=True)
            began=time.monotonic();r=subprocess.run([sys.executable,'-B',*args],cwd=ROOT,check=False)
            result['phases'].append(dict(stage=name,seconds=round(time.monotonic()-began,3),exit=r.returncode))
            assert r.returncode==0,'NATIVE_SOURCE_GATE_FAILED'
        result['outcome']='PASS_NATIVE_SOURCE_ONLY'
    except (AssertionError,OSError,subprocess.SubprocessError) as error:
        result['code']=str(error) if isinstance(error,AssertionError) else type(error).__name__
    result['seconds']=round(time.monotonic()-start,3)
    print(json.dumps(result),flush=True)
    return 0 if result['outcome']=='PASS_NATIVE_SOURCE_ONLY' else 1


if __name__=='__main__':raise SystemExit(main())
