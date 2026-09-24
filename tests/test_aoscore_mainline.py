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

    def test_reference_compares_after_all_patches_to_same_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recipes = root / 'recipes'
            recipe = recipes / 'aos-communicationmanager'
            files = recipe / 'files'
            files.mkdir(parents=True)
            (recipe / 'aos-communicationmanager_git.bbappend').write_text(
                'file://first.patch;patchdir=../service-update-deps/aos_core_lib_cpp\n'
                'file://second.patch;patchdir=../service-update-deps/aos_core_lib_cpp\n')
            for name, before, after in (('first', 'base', 'middle'), ('second', 'middle', 'final')):
                (files / (name + '.patch')).write_text(
                    f'Base: aos_core_lib_cpp {gate.LIB}\n\n'
                    'diff --git a/value b/value\n--- a/value\n+++ b/value\n'
                    f'@@ -1 +1 @@\n-{before}\n+{after}\n')
            reference = root / 'reference/lib'
            reference.mkdir(parents=True)
            (reference / 'value').write_text('final\n')

            def export(_source, _revision, target):
                target.mkdir(parents=True)
                (target / 'value').write_text('base\n')

            with patch.object(gate, 'validate_pins'), patch.object(gate, 'RECIPES', recipes), \
                    patch.object(gate, 'MANAGERS', ('aos-communicationmanager',)), \
                    patch.object(gate, 'export', side_effect=export):
                gate.reconstruct(root, root, root / 'output', reference.parent)


if __name__ == '__main__':
    unittest.main()
