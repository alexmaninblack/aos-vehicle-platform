#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Targeted launcher and transient policy compile; never runs BitBake/image."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

PROJECT=Path('/home/yocto/r61-build/factory42-475dc7c1ef3ac303')


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--native-policy',action='store_true',help='Compile the accepted permanent native-store policy, not the old proof fixture')
    a=p.parse_args();assert os.uname().machine=='aarch64'
    assert a.input.is_relative_to(PROJECT/'.tmp') and not a.input.is_symlink()
    assert a.evidence.parent==PROJECT and not a.evidence.exists();a.evidence.mkdir(mode=0o700)
    work=PROJECT/'yocto/build-main/tmp/work'
    sm=work/'cortexa57-aos-linux/aos-servicemanager/git'
    policy_work=work/'qemuarm64-aos-linux/refpolicy-aos/2_20220106+git'
    values={s.split('=',1)[0].removeprefix('export '):shlex.split(s)[1].split('=',1)[1]
        for s in (sm/'temp/run.do_compile').read_text().splitlines() if s.startswith(('export PATH=','export CC='))}
    env=dict(os.environ,PATH=values['PATH'])
    def run(args,cwd=None):return subprocess.run(args,cwd=cwd,env=env,check=True,capture_output=True,timeout=60).stdout
    with tempfile.TemporaryDirectory(prefix='ingress-compile-',dir=PROJECT/'.tmp') as temporary:
        scratch=Path(temporary)
        run([*shlex.split(values['CC']),'-Wall','-Wextra','-Werror',str(a.input/'aos-camera-ingress-launcher.c'),'-o',str(a.evidence/'aos-camera-ingress-launcher')])
        policy=policy_work/'refpolicy'
        flags=['NAME=aos','TYPE=mcs','DISTRO=debian','UBAC=n','UNK_PERMS=allow','DIRECT_INITRC=y','SYSTEMD=y',
            'MONOLITHIC=n','CUSTOM_BUILDOPT=','MLS_SENS=0','MLS_CATS=1024','MCS_CATS=1024',
            'tc_usrbindir='+str(policy_work/'recipe-sysroot-native/usr/bin'),'OUTPUT_POLICY=33']
        dry=run(['make','-n','-W','policy/modules/services/vehicle_data_provider.te',*flags,'tmp/vehicle_data_provider.mod'],policy).decode()
        args=shlex.split(next(v for v in dry.splitlines() if v.startswith('m4 ')));args=args[:args.index('>')]
        name='camera_ingress' if a.native_policy else 'camera_ingress_probe'
        args[args.index('policy/modules/services/vehicle_data_provider.te')]=str(a.input/(name+'.te'))
        (scratch/(name+'.tmp')).write_bytes(run(args,policy))
        tools=policy_work/'recipe-sysroot-native/usr/bin'
        run([str(tools/'checkmodule'),'-M','-m',str(scratch/(name+'.tmp')),'-o',str(scratch/(name+'.mod'))])
        run([str(tools/'semodule_package'),'-o',str(a.evidence/(name+'.pp')),'-m',str(scratch/(name+'.mod'))])
    result=dict(outcome='PASS_TARGETED_INGRESS_PRIMITIVES',imageBuilt=False,
        inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.input.iterdir() if p.is_file()},
        files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in a.evidence.iterdir() if p.is_file()})
    (a.evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
