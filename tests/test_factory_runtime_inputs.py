# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class FactoryRuntimeInputsTests(unittest.TestCase):
    def test_packaged_config_preserves_runtime_and_contains_no_live_inputs(self):
        recipe = (ROOT / "meta-aos-vehicle-platform/recipes-core/images/aos-image-vm.bbappend").read_text()
        body = textwrap.dedent(recipe.split("python aos_demo_runtime_inputs() {\n", 1)[1].rsplit("}", 1)[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "etc/aos/sm.cfg"
            path.parent.mkdir(parents=True)
            original = dict(runtimes=[dict(plugin="systemd-slot-component", config=dict(type="preserved", layoutVersion=1))], untouched=True)
            path.write_text(json.dumps(original))
            exec(body, {"d": SimpleNamespace(getVar=lambda key: str(root))})
            first = path.read_bytes()
            config = json.loads(first)
            self.assertTrue(config["untouched"])
            runtime = config["runtimes"][0]["config"]
            self.assertEqual("preserved", runtime["type"])
            self.assertEqual("standard", runtime["safeStopFreshnessProfile"])
            self.assertTrue(runtime["demoLocalSourceInputs"])
            self.assertTrue((root / "usr/share/aos-vehicle-platform/demo-runtime-inputs-v1").is_file())
            self.assertFalse((root / "var").exists())
            self.assertFalse((root / "run").exists())
            dropin = (root / "etc/systemd/system/aos-vehicle-data-provider.service.d/50-democtl-source.conf").read_text()
            self.assertIn("LoadCredential=viss-selected-source.json:/var/aos/", dropin)
            self.assertNotIn("ExecStart", dropin)
            self.assertNotIn("private-key", dropin)
            exec(body, {"d": SimpleNamespace(getVar=lambda key: str(root))})
            self.assertEqual(first, path.read_bytes())
