#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Build-time fixed Vision model metadata, never credentials/identity editing."""
import json
from pathlib import Path
import sys

path=Path(sys.argv[1]);value=json.loads(path.read_bytes());node=value['nodeInfo']
assert type(node) is dict and node.get('maxDmips',node.get('maxDMIPS'))==10000
assert not any(key.lower()=='cpuinfopath' for key in node),'VISION_CPUINFO_OVERRIDE_ALREADY_PRESENT'
node['cpuInfoPath']='/run/aos-vision-cpuinfo'
path.write_text(json.dumps(value,indent=4)+'\n')
