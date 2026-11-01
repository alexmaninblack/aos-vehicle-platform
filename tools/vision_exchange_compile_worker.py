#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Compile only fixed Vision exchange launchers/policy; no image task."""
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
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
    assert os.uname().machine=='aarch64' and a.input.is_relative_to(PROJECT/'.tmp') and not a.input.is_symlink()
    assert a.evidence.parent==PROJECT and not a.evidence.exists();a.evidence.mkdir(mode=0o700)
    work=PROJECT/'yocto/build-main/tmp/work';sm=work/'cortexa57-aos-linux/aos-servicemanager/git'
    policy_work=work/'qemuarm64-aos-linux/refpolicy-aos/2_20220106+git'
    values={s.split('=',1)[0].removeprefix('export '):shlex.split(s)[1].split('=',1)[1]
        for s in (sm/'temp/run.do_compile').read_text().splitlines() if s.startswith(('export PATH=','export CC='))}
    env=dict(os.environ,PATH=values['PATH'])
    def run(args,cwd=None):
        done=subprocess.run(args,cwd=cwd,env=env,capture_output=True,timeout=60)
        if done.returncode:raise ValueError((done.stdout+done.stderr).decode()[-3000:])
        return done.stdout
    with tempfile.TemporaryDirectory(prefix='vision-exchange-',dir=PROJECT/'.tmp') as temporary:
        scratch=Path(temporary)
        for name,flags in (('aos-vision-exchange-launcher',[]),('aos-vision-exchange-proof',['-DAOS_VISION_EXCHANGE_PROOF=1'])):
            run([*shlex.split(values['CC']),'-Wall','-Wextra','-Werror',*flags,str(a.input/'aos-vision-exchange-launcher.c'),'-o',str(a.evidence/name)])
        policy=policy_work/'refpolicy';tools=policy_work/'recipe-sysroot-native/usr/bin'
        flags=['NAME=aos','TYPE=mcs','DISTRO=debian','UBAC=n','UNK_PERMS=allow','DIRECT_INITRC=y','SYSTEMD=y',
            'MONOLITHIC=n','CUSTOM_BUILDOPT=','MLS_SENS=0','MLS_CATS=1024','MCS_CATS=1024','tc_usrbindir='+str(tools),'OUTPUT_POLICY=33']
        dry=run(['make','-n','-W','policy/modules/services/vehicle_data_provider.te',*flags,'tmp/vehicle_data_provider.mod'],policy).decode()
        args=shlex.split(next(row for row in dry.splitlines() if row.startswith('m4 ')));args=args[:args.index('>')]
        args[args.index('policy/modules/services/vehicle_data_provider.te')]=str(a.input/'vision_exchange.te')
        (scratch/'vision_exchange.tmp').write_bytes(run(args,policy))
        run([str(tools/'checkmodule'),'-M','-m',str(scratch/'vision_exchange.tmp'),'-o',str(scratch/'vision_exchange.mod')])
        run([str(tools/'semodule_package'),'-o',str(a.evidence/'vision_exchange.pp'),'-m',str(scratch/'vision_exchange.mod')])
    result=dict(outcome='PASS_VISION_EXCHANGE_TARGETED_PRIMITIVES',imageBuilt=False,nativeExecution='NOT_RUN',
        inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.input.iterdir() if p.is_file()},
        files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in a.evidence.iterdir() if p.is_file()})
    (a.evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
