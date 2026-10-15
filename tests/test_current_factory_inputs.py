# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Current Factory inputs stay intact when superseded attempts are retired."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CurrentFactoryInputsTests(unittest.TestCase):
    def test_current_factory_inheritance_remains_complete(self):
        for suffix, parent in ((41, 40), (40, 39)):
            text = (ROOT / f"qualification/factory-{suffix}.conf").read_text()
            self.assertIn(f"require factory-{parent}.conf", text)
            self.assertIn(f'"6.1.1-maninblack.{suffix}"', text)
        base = (ROOT / "qualification/factory-39.conf").read_text()
        self.assertIn('BB_NO_NETWORK = "1"', base)
        self.assertIn('BB_FETCH_PREMIRRORONLY = "1"', base)

    def test_retained_helper_configs_are_not_mistaken_for_unused_history(self):
        for suffix in (31, 33):
            self.assertTrue((ROOT / f"qualification/factory-{suffix}.conf").is_file())

    def test_superseded_attempts_are_not_active_tree_inputs(self):
        for suffix in (29, 30, 32, 34, 35, 36, 37, 38):
            self.assertFalse((ROOT / f"qualification/factory-{suffix}.conf").exists())
