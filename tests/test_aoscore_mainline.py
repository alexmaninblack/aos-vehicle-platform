# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

import tempfile
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from tools import validate_aoscore_mainline as gate


class MainlinePinTests(unittest.TestCase):
    def test_coordinated_triplet_matches_inventory(self):
        gate.validate_pins()

    def test_one_old_manager_pin_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipes = root / 'recipes'
            for name in gate.MANAGERS:
                target = recipes / name
                target.mkdir(parents=True)
                recipe = gate.RECIPES / name / (name + '_git.bbappend')
                shutil.copyfile(recipe, target / recipe.name)
            shutil.copyfile(gate.ROOT / 'DEPENDENCIES.json', root / 'DEPENDENCIES.json')
            iam = recipes / 'aos-iamanager/aos-iamanager_git.bbappend'
            iam.write_text(iam.read_text().replace(gate.LIB, '60cb83535f773762c61ac5f544b31b7b88c502e3'))
            with patch.object(gate, 'ROOT', root), patch.object(gate, 'RECIPES', recipes):
                with self.assertRaises(AssertionError):
                    gate.validate_pins()

    def test_existing_proof_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'preserved'
            marker.write_text('existing evidence')
            with self.assertRaisesRegex(AssertionError, 'never overwritten'):
                gate.reconstruct(Path('/unused'), Path('/unused'), root)
            self.assertEqual(marker.read_text(), 'existing evidence')


if __name__ == '__main__':
    unittest.main()
