# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class FactoryCMIdleStatusTests(unittest.TestCase):
    def test_final_config_enables_interval_without_changing_other_settings(self):
        recipe = (ROOT / "meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager/aos-communicationmanager_git.bbappend").read_text()
        self.assertIn('do_update_config[postfuncs] += "aos_demo_idle_full_status"', recipe)
        body = textwrap.dedent(recipe.split("python aos_demo_idle_full_status() {\n", 1)[1].split("\n}", 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "etc/aos/cm.cfg"
            path.parent.mkdir(parents=True)
            original = dict(unitStatusSendTimeout="1s", monitoring=dict(sendPeriod="5m"))
            path.write_text(json.dumps(original))
            variables = {"D": str(root), "sysconfdir": "/etc"}
            exec(body, {"d": SimpleNamespace(getVar=variables.get)})
            self.assertEqual(dict(original, idleFullStatusInterval="60s"), json.loads(path.read_text()))
            first = path.read_bytes()
            exec(body, {"d": SimpleNamespace(getVar=variables.get)})
            self.assertEqual(first, path.read_bytes())
            self.assertFalse((root / "run").exists())
            self.assertFalse((root / "var").exists())
