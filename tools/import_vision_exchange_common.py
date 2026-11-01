#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Explicit immutable service-common fan-in, never a mutable runtime sibling."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--revision',required=True);p.add_argument('--refresh-owned',action='store_true');a=p.parse_args()
    assert subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip()==a.revision
    assert not subprocess.check_output(['git','-C',str(a.source),'status','--porcelain'],text=True),'SERVICE_SOURCE_DIRTY'
    root=Path(__file__).resolve().parents[1];target=root/'camera-access/shared/vision_common'
    receipt=root/'contracts/camera-access/vision-exchange-source.json'
    if target.exists():
        assert a.refresh_owned and receipt.is_file(),'SHARED_IMPORT_EXISTS_RECONCILE'
        previous=json.loads(receipt.read_bytes())
        assert {p.name for p in target.iterdir()}=={'__init__.py','protocol.py','ipc.py'},'UNOWNED_SHARED_INPUT'
        for row in previous['files']:assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],'SHARED_INPUT_CHANGED'
    else:target.mkdir(parents=True)
    files=[]
    for name in ('__init__.py','protocol.py','ipc.py'):
        raw=subprocess.check_output(['git','-C',str(a.source),'show',a.revision+':common/vision_common/'+name])
        assert b'SPDX-License-Identifier: Apache-2.0' in raw
        path=target/name;path.write_bytes(raw);files.append(dict(path=str(path.relative_to(root)),sha256=hashlib.sha256(raw).hexdigest()))
    value={'$comment':'SPDX-FileCopyrightText: 2026 maninblack; SPDX-License-Identifier: Apache-2.0',
        'schemaVersion':1,'repository':'https://github.com/alexmaninblack/vision-pilot-services','revision':a.revision,
        'scope':'Strict typed DTO/framing only; no model, Cloud, credentials or runtime sibling', 'files':files}
    (root/'contracts/camera-access/vision-exchange-source.json').write_text(json.dumps(value,indent=2)+'\n')
    print('VISION_EXCHANGE_COMMON_PINNED')


if __name__=='__main__':main()
