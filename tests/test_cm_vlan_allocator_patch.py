# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Keep the production recipe bound to the natively tested VLAN correction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager'
NAME = '0008-allocate-valid-unused-vlan-ids.patch'


class VlanAllocatorPatchTest(unittest.TestCase):
    def test_recipe_and_exact_base(self):
        recipe = (RECIPE / 'aos-communicationmanager_git.bbappend').read_text()
        patch = (RECIPE / 'files' / NAME).read_text()
        self.assertEqual(recipe.count('file://' + NAME), 1)
        self.assertIn('Base: aos_core_cpp 9d613a46df3c7f550062e2f19ae3406c57715694', patch)

    def test_boundaries_collision_and_no_persistence_on_exhaustion(self):
        patch = (RECIPE / 'files' / NAME).read_text()
        additions = '\n'.join(line[1:] for line in patch.splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        for text in ('cMaxVlanID           = 4094;', 'RandInt(cMaxVlanID + 1)',
                     'vlanID == 0 || vlanID > cMaxVlanID', 'std::any_of',
                     'if (inUse)', 'VlanBoundarySkipsReservedAndAcceptsMaximum',
                     'VlanBoundaryAcceptsMinimum', 'VlanBoundaryExhaustionDoesNotPersistNetwork',
                     'VlanBoundarySkipsCollision', 'AddNetwork(_)).Times(0)'):
            self.assertIn(text, additions)


if __name__ == '__main__':
    unittest.main()
