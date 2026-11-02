# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Five-resource Vision ABI is explicit and leaves Main's flags unchanged."""
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]


class VisionResourceCapacityTests(unittest.TestCase):
    def test_both_native_owners_share_the_exact_opt_in_capacity(self):
        for recipe in ('aos-servicemanager','aos-communicationmanager'):
            text=(ROOT/'meta-aos-vehicle-platform/recipes-aos'/recipe/(recipe+'_git.bbappend')).read_text()
            self.assertIn('AOS_VISION_NATIVE_SERVICES ??= "0"',text)
            lines=[line for line in text.splitlines() if 'CXXFLAGS:append' in line and 'MAX_NUM_NODE_RESOURCES' in line]
            self.assertEqual(len(lines),1)
            self.assertIn("-DAOS_CONFIG_TYPES_MAX_NUM_NODE_RESOURCES=5' if d.getVar('AOS_VISION_NATIVE_SERVICES') == '1' else ''",lines[0])
            self.assertEqual(re.findall(r'MAX_NUM_NODE_RESOURCES=(\d+)',lines[0]),['5'])

    def test_diagnostic_compile_is_isolated_offline_and_uses_the_production_generator(self):
        text=(ROOT/'tools/vision_resource_capacity_compile_worker.py').read_text()
        self.assertIn("build=owner/'build'",text)
        self.assertIn("cache['CMAKE_GENERATOR'][1]",text)
        self.assertIn("selected['FETCHCONTENT_FULLY_DISCONNECTED']='ON'",text)
        self.assertIn("selected['FETCHCONTENT_UPDATES_DISCONNECTED']='ON'",text)
        self.assertIn("dir=PROJECT/'.tmp'",text)
        self.assertNotIn("'-G','Ninja'",text)


if __name__=='__main__':unittest.main()
