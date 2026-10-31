#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Compile only the Camera launcher/policy with the preserved recipe toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','sm-work','policy-work','scratch','evidence'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    assert os.uname().sysname=='Linux' and os.uname().machine=='aarch64'
    assert all(x.is_absolute() and not x.is_symlink() for x in (a.source,a.sm_work,a.policy_work,a.scratch,a.evidence))
    assert not a.evidence.exists(),'PRIMITIVE_ATTEMPT_EXISTS'
    a.evidence.mkdir(mode=0o700,parents=True)
    env=dict(os.environ)
    values={s.split('=',1)[0].removeprefix('export '):shlex.split(s)[1].split('=',1)[1]
            for s in (a.sm_work/'temp/run.do_compile').read_text().splitlines()
            if s.startswith(('export PATH=','export CC='))}
    env['PATH']=values['PATH']
    files=a.source/'meta-aos-vehicle-platform/recipes-security/refpolicy/files'
    launcher=a.source/'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/files/aos-camera-access-launcher.c'
    def run(args,output=None,cwd=None):
        r=subprocess.run(args,cwd=cwd,env=env,capture_output=True,timeout=60)
        assert r.returncode==0,(r.stdout+r.stderr).decode()[-3000:]
        if output:output.write_bytes(r.stdout)
        return r.stdout.decode()
    with tempfile.TemporaryDirectory(prefix='camera-primitives-',dir=a.scratch) as temporary:
        scratch=Path(temporary)
        print('CAMERA_LAUNCHER_COMPILE_STARTED',flush=True)
        run([*shlex.split(values['CC']),'-Wall','-Wextra','-Werror',str(launcher),'-o',str(a.evidence/'aos-camera-access-launcher')])
        policy=a.policy_work/'refpolicy'
        flags=['NAME=aos','TYPE=mcs','DISTRO=debian','UBAC=n','UNK_PERMS=allow','DIRECT_INITRC=y','SYSTEMD=y',
               'MONOLITHIC=n','CUSTOM_BUILDOPT=','MLS_SENS=0','MLS_CATS=1024','MCS_CATS=1024',
               'tc_usrbindir='+str(a.policy_work/'recipe-sysroot-native/usr/bin'),'OUTPUT_POLICY=33']
        print('CAMERA_POLICY_COMPILE_STARTED',flush=True)
        dry=run(['make','-n','-W','policy/modules/services/vehicle_data_provider.te',*flags,'tmp/vehicle_data_provider.mod'],cwd=policy)
        line=next(s for s in dry.splitlines() if s.startswith('m4 '))
        args=shlex.split(line);args=args[:args.index('>')]
        i=args.index('policy/modules/services/vehicle_data_provider.te');args[i]=str(files/'camera_access.te')
        run(args,scratch/'camera_access.tmp',policy)
        native=a.policy_work/'recipe-sysroot-native/usr/bin'
        run([str(native/'checkmodule'),'-M','-m',str(scratch/'camera_access.tmp'),'-o',str(scratch/'camera_access.mod')])
        # Context files need the same recipe's m4 support definitions, not a
        # hand-written expansion or a change to the preserved policy source.
        fcargs=args[:args.index('tmp/generated_definitions.conf')]
        fcargs += [str(files/'camera_access.fc')]
        run(fcargs,scratch/'camera_access.fc',policy)
        run([str(native/'semodule_package'),'-o',str(a.evidence/'camera_access.pp'),
             '-m',str(scratch/'camera_access.mod'),'-f',str(scratch/'camera_access.fc')])
    result=dict(outcome='PASS_TARGETED_PRIMITIVE_COMPILE',imageBuilt=False,m4Security='NOT_RUN',
                files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                       for p in sorted(a.evidence.iterdir())})
    (a.evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
