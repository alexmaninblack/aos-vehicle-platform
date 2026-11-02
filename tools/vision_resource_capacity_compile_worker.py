#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Isolated target compilation for the exact five-resource Vision node."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import traceback

PROJECT=Path('/home/yocto/r61-build/factory42-475dc7c1ef3ac303')


def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);a=p.parse_args()
    assert os.uname().machine=='aarch64' and a.evidence.parent==PROJECT and not a.evidence.exists()
    a.evidence.mkdir(mode=0o700);result=dict(outcome='NOT_COMPLETE',nodeResources=5,imageBuilt=False,preparedSourcesChanged=False)
    work=PROJECT/'yocto/build-main/tmp/work/cortexa57-aos-linux'
    try:
        for recipe in ('aos-servicemanager','aos-communicationmanager'):
            owner=work/recipe/'git';build=owner/'build'
            assert (build/'CMakeCache.txt').is_file(),'VISION_PRODUCTION_CMAKE_CACHE_REQUIRED'
            result.setdefault('layout',{})[recipe]=dict(cachePath=str(build/'CMakeCache.txt'))
            cache={}
            for row in (build/'CMakeCache.txt').read_text().splitlines():
                if row.startswith(('#','//')) or '=' not in row or ':' not in row.split('=',1)[0]:continue
                key,value=row.split('=',1);key,kind=key.split(':',1);cache[key]=(kind,value)
            source=Path(cache['CMAKE_HOME_DIRECTORY'][1]);result['layout'][recipe]['source']=str(source)
            assert source.is_relative_to(owner)
            exports={}
            for row in (owner/'temp/run.do_compile').read_text().splitlines():
                if row.startswith('export ') and '=' in row:
                    values=shlex.split(row)
                    if len(values)==2:
                        key,value=values[1].split('=',1);exports[key]=value
            selected={key:value for key,(kind,value) in cache.items() if kind=='UNINITIALIZED' or kind!='INTERNAL' and key.startswith(('AOS_','WITH_'))}
            for key in ('CMAKE_TOOLCHAIN_FILE','CMAKE_BUILD_TYPE','CMAKE_C_FLAGS','CMAKE_CXX_FLAGS','CMAKE_EXE_LINKER_FLAGS','CMAKE_SHARED_LINKER_FLAGS','CMAKE_MAKE_PROGRAM'):
                if key in cache:selected[key]=cache[key][1]
            for key in ('CMAKE_C_FLAGS','CMAKE_CXX_FLAGS'):
                value=selected.get(key,'')
                if value.startswith("'") and value.endswith("'") and len(shlex.split(value))==1:selected[key]=shlex.split(value)[0]
            selected['CMAKE_CXX_FLAGS']=selected.get('CMAKE_CXX_FLAGS','')+' -DAOS_CONFIG_TYPES_MAX_NUM_NODE_RESOURCES=5'
            selected['WITH_TEST']='OFF';selected['CMAKE_EXPORT_COMPILE_COMMANDS']='ON'
            selected['FETCHCONTENT_FULLY_DISCONNECTED']='ON';selected['FETCHCONTENT_UPDATES_DISCONNECTED']='ON'
            env=dict(os.environ,**exports)
            (a.evidence/(recipe+'-configure-input.json')).write_text(json.dumps(dict(source=str(source),selected=selected,topLevel=(source/'CMakeLists.txt').read_text()),indent=2)+'\n')
            with tempfile.TemporaryDirectory(prefix='vision-resource-capacity-',dir=PROJECT/'.tmp') as temporary:
                scratch=Path(temporary);command=['cmake','-S',str(source),'-B',str(scratch),'-G',cache['CMAKE_GENERATOR'][1],*[f'-D{key}={value}' for key,value in selected.items()]]
                for stage,args in (('configure',command),('compile',['cmake','--build',str(scratch),'--parallel','8'])):
                    with (a.evidence/(recipe+'-'+stage+'.log')).open('wb') as log:
                        done=subprocess.run(args,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1200)
                    assert done.returncode==0,recipe+'_'+stage+'_FAILED'
                expected='aos_sm_app' if recipe=='aos-servicemanager' else 'aos_cm_app'
                binaries=[p for p in scratch.rglob(expected) if p.is_file()];assert len(binaries)==1
                strip=shlex.split(exports['STRIP']);subprocess.run([*strip,str(binaries[0])],env=env,check=True,capture_output=True,timeout=20)
                target=a.evidence/expected;target.write_bytes(binaries[0].read_bytes());target.chmod(0o500)
                assert target.read_bytes()[:6]==b'\x7fELF\x02\x01' and target.read_bytes()[18:20]==b'\xb7\x00'
                commands=json.loads((scratch/'compile_commands.json').read_bytes())
                cpp=[row for row in commands if Path(row['file']).suffix in ('.cpp','.cc','.cxx')]
                assert cpp and all('-DAOS_CONFIG_TYPES_MAX_NUM_NODE_RESOURCES=5' in row['command'] for row in cpp)
                result.setdefault('files',{})[expected]=dict(bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        result['outcome']='PASS_TARGETED_FIVE_RESOURCE_NATIVE_OWNER_COMPILE'
    except Exception as error:
        result['code']=str(error) if str(error).isupper() else type(error).__name__
        result['errorFrames']=[dict(file=Path(row.filename).name,line=row.lineno) for row in traceback.extract_tb(error.__traceback__)[-3:]]
    (a.evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return 0 if result['outcome'].startswith('PASS_') else 1


if __name__=='__main__':raise SystemExit(main())
