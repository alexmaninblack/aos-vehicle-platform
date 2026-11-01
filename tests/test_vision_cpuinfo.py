# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import runpy
import unittest

MODULE=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/vision_cpuinfo_projection.py'))


class TopologyTests(unittest.TestCase):
    def test_packaged_projection_uses_actual_records_not_synthetic_topology(self):
        root=Path(__file__).resolve().parents[1]
        path=root/'meta-aos-vehicle-platform/recipes-aos/aos-iamanager/files/35-vision-cpuinfo.conf'
        self.assertIn('--write-profile',path.read_text())
        self.assertFalse((path.parent/'vision-cpuinfo').exists())

    def test_arm_processor_records_and_actual_package_topology_are_preserved(self):
        raw='\n\n'.join('processor\t: '+str(i)+'\nCPU architecture: 8\nCPU part: 0xd07' for i in range(4))
        text,facts=MODULE['project'](raw,set(range(4)),{i:(0,i) for i in range(4)})
        self.assertEqual(facts,dict(packages=1,cores=4,threads=4,online=[0,1,2,3]))
        self.assertEqual(text.count('cpu cores\t: 4'),4);self.assertEqual(text.count('CPU part: 0xd07'),4)
        self.assertEqual(MODULE['project'](text,set(range(4)),{i:(0,i) for i in range(4)})[0],text)
        _,facts=MODULE['project'](raw,set(range(4)),{i:(i,0) for i in range(4)})
        self.assertEqual((facts['packages'],facts['cores']),(4,4))

    def test_missing_unknown_offline_smt_or_duplicate_processors_fail_closed(self):
        raw='\n\n'.join('processor: '+str(i)+'\nCPU architecture: 8' for i in range(4))
        for online,topology,text in (({0,1},{i:(0,i) for i in range(2)},raw),
                (set(range(4)),{i:(-1,i) for i in range(4)},raw),
                (set(range(4)),{i:(0,0) for i in range(4)},raw),
                (set(range(4)),{i:(0,i) for i in range(4)},raw.replace('processor: 3','processor: 2'))):
            with self.assertRaises(ValueError):MODULE['project'](text,online,topology)
        self.assertEqual(MODULE['cpu_set']('0-3'),{0,1,2,3})
        for value in ('0-3,2','0-65','3-0','0,',''):
            with self.assertRaises(ValueError):MODULE['cpu_set'](value)


if __name__=='__main__':unittest.main()
