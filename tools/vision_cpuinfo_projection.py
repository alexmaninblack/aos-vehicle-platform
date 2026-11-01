#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Public topology projection for the pinned Core ARM cpuinfo parser.

Preserve the actual processor records; add only package/core/thread fields
derived from matching Linux online CPUs and sysfs topology. No quota formula,
VM resource, DMIPS capacity, identity or Core source is changed.
"""
import os
import ctypes
from pathlib import Path
import re
import stat
import sys
import tempfile


def require(ok,code):
    if not ok:raise ValueError(code)


def cpu_set(value):
    require(type(value) is str and re.fullmatch(r'[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*',value) is not None,'CPU_ONLINE_FORMAT_INVALID')
    result=set()
    for part in value.split(','):
        bounds=list(map(int,part.split('-')));first=bounds[0];last=bounds[-1]
        require(0<=first<=last<64,'CPU_ONLINE_RANGE_INVALID')
        selected=set(range(first,last+1));require(not result&selected,'CPU_ONLINE_DUPLICATE');result|=selected
    return result


def project(raw,online,topology):
    require(type(raw) is str and 0<len(raw)<1024*1024 and len(online)==4 and set(topology)==online,'VISION_FOUR_CPU_PROFILE_REQUIRED')
    records=[];seen=set();packages={}
    for cpu,(package,core) in topology.items():
        require(type(package) is int and type(core) is int and 0<=package<64 and 0<=core<64,'CPU_TOPOLOGY_UNAVAILABLE')
        packages.setdefault(package,[]).append((cpu,core))
    for block in raw.strip().split('\n\n'):
        lines=[row for row in block.splitlines() if row.strip()];processor=[row.split(':',1)[1].strip() for row in lines if ':' in row and row.split(':',1)[0].strip()=='processor']
        require(len(processor)==1 and processor[0].isdigit(),'CPU_PROCESSOR_RECORD_INVALID');cpu=int(processor[0])
        require(cpu in online and cpu not in seen,'CPU_PROCESSOR_SET_CHANGED');seen.add(cpu)
        package,_=topology[cpu];members=packages[package]
        kept=[row for row in lines if ':' not in row or row.split(':',1)[0].strip().lower() not in ('physical id','cpu cores','siblings')]
        kept+=['physical id\t: '+str(package),'cpu cores\t: '+str(len({core for _,core in members})),'siblings\t: '+str(len(members))]
        records.append((cpu,'\n'.join(kept)))
    require(seen==online,'CPU_PROCESSOR_SET_CHANGED')
    cores=sum(len({core for _,core in members}) for members in packages.values())
    require(cores==4,'VISION_FOUR_DISTINCT_CORES_REQUIRED')
    return '\n\n'.join(record for _,record in sorted(records))+'\n\n',dict(packages=len(packages),cores=cores,threads=len(online),online=sorted(online))


def current():
    require(sys.platform=='linux' and os.uname().machine=='aarch64','LINUX_ARM64_REQUIRED')
    online=cpu_set(Path('/sys/devices/system/cpu/online').read_text().strip())
    require(os.cpu_count()==len(online)==4 and set(os.sched_getaffinity(0))==online,'VISION_CPU_AFFINITY_CHANGED')
    topology={}
    for cpu in online:
        root=Path('/sys/devices/system/cpu')/('cpu'+str(cpu))/'topology'
        topology[cpu]=(int((root/'physical_package_id').read_text()),int((root/'core_id').read_text()))
    return project(Path('/proc/cpuinfo').read_text(),online,topology)


def write_profile(path=Path('/run/aos-vision-cpuinfo')):
    """Existing IAM ExecStartPre owner projects actual facts, never a daemon.

    The full real CPU records are retained, as in the native transient proof.
    A shortened synthetic cpuinfo is not equivalent for this pinned parser.
    Only a regular root-owned derived file on /run is replaced atomically.
    """
    require(os.getuid()==os.geteuid()==0 and path.is_absolute() and path.is_relative_to('/run')
        and not any(p.is_symlink() for p in (path,*path.parents)),'CPU_PROFILE_OUTPUT_UNSAFE')
    text,facts=current();require(facts['packages']==1,'VISION_CPU_PACKAGE_PROFILE_CHANGED')
    before=path.lstat() if path.exists() else None
    if before:require(stat.S_ISREG(before.st_mode) and before.st_uid==0 and before.st_nlink==1 and not before.st_mode&0o022,'CPU_PROFILE_OUTPUT_UNSAFE')
    descriptor,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent);temporary=Path(name)
    try:
        with os.fdopen(descriptor,'w') as stream:stream.write(text);stream.flush();os.fchmod(stream.fileno(),0o644)
        library=ctypes.CDLL('libselinux.so.1',use_errno=True)
        library.getfilecon.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p)];library.getfilecon.restype=ctypes.c_int
        library.setfilecon.argtypes=[ctypes.c_char_p,ctypes.c_void_p];library.setfilecon.restype=ctypes.c_int
        library.freecon.argtypes=[ctypes.c_void_p];library.freecon.restype=None
        context=ctypes.c_void_p();require(library.getfilecon(b'/proc/cpuinfo',ctypes.byref(context))>0,'CPU_PROFILE_REFERENCE_LABEL_UNAVAILABLE')
        try:require(library.setfilecon(os.fsencode(temporary),context)==0,'CPU_PROFILE_LABEL_REJECTED')
        finally:library.freecon(context)
        require((before is None and not path.exists() and not path.is_symlink()) or (before is not None and path.lstat()==before),'CPU_PROFILE_OUTPUT_OWNER_CHANGED')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


if __name__=='__main__':
    if sys.argv[1:]==['--write-profile']:write_profile()
    else:
        require(len(sys.argv)==1,'CPU_PROJECTION_ARGUMENTS_INVALID');text,_=current();print(text,end='')
