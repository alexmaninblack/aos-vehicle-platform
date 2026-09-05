# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

import ast
import json
import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "meta-aos-vehicle-platform/recipes-support/vss/files/vdp_vss_schema.py"
SCHEMA = runpy.run_path(str(SOURCE))


def baseline():
    tree = {}
    for name in SCHEMA["BASE_PATHS"] + SCHEMA["WHEEL_PATHS"]:
        current = tree
        parts = name.split(".")
        for part in parts[:-1]:
            current = current.setdefault(part, dict(type="branch", children={}))["children"]
        current[parts[-1]] = dict(type="sensor", datatype="uint8" if name.endswith("PedalPosition") else "float", description="preserve")
    tree["Vehicle"]["children"]["Unrelated"] = dict(type="attribute", datatype="string", default="preserve")
    return tree


class VdpSchemaTests(unittest.TestCase):
    def test_release_paths_match_source_v1_v2_v3_exactly(self):
        paths = []
        for version, addition in ((1, "BASE_PATHS"), (2, "WHEEL_PATHS"), (3, "SLIP_PATHS")):
            paths.extend(SCHEMA[addition])
            tree = ast.parse((ROOT / ("providers/carla-viss-kuksa/src/carla_viss_kuksa_provider/releases/v%d.py" % version)).read_text())
            actual = [node.args[0].value for node in ast.walk(tree) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name) and node.func.id == "SignalSpec"]
            self.assertEqual(set(paths), set(actual))
            self.assertEqual((7, 15, 23)[version - 1], len(actual))

    def test_only_eight_leaves_added_and_base_preserved(self):
        original = baseline()
        saved = json.dumps(original, sort_keys=True)
        result = SCHEMA["supplement"](original)
        self.assertEqual(saved, json.dumps(original, sort_keys=True))
        del result["Vehicle"]["children"]["CarlaSimulation"]
        self.assertEqual(original, result)

    def test_deterministic_repeat_and_original_file_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vss.json"
            path.write_text(json.dumps(baseline()))
            path.chmod(0o644)
            SCHEMA["transform"](path)
            first = path.read_bytes()
            SCHEMA["transform"](path)
            self.assertEqual(first, path.read_bytes())
            self.assertEqual(0o644, path.stat().st_mode & 0o777)

    def test_missing_v1_or_v2_or_wrong_type_fails(self):
        for name in SCHEMA["BASE_PATHS"] + SCHEMA["WHEEL_PATHS"]:
            value = baseline()
            SCHEMA["lookup"](value, name)["datatype"] = "string"
            with self.assertRaisesRegex(ValueError, "type conflict"):
                SCHEMA["supplement"](value)

    def test_conflicting_custom_field_or_branch_fails(self):
        value = SCHEMA["supplement"](baseline())
        SCHEMA["lookup"](value, SCHEMA["SLIP_PATHS"][0])["datatype"] = "string"
        with self.assertRaisesRegex(ValueError, "leaf conflict"):
            SCHEMA["supplement"](value)
        value = baseline()
        value["Vehicle"]["children"]["CarlaSimulation"] = dict(type="sensor", datatype="float")
        with self.assertRaisesRegex(ValueError, "branch conflict"):
            SCHEMA["supplement"](value)

    def test_recipe_changes_packaged_schema_not_runtime_or_test_schema(self):
        recipe = SOURCE.parents[1] / "vss_5.0.bbappend"
        text = recipe.read_text()
        self.assertIn('do_install[postfuncs] += "vdp_schema_install"', text)
        self.assertIn("python vdp_schema_install()", text)
        self.assertNotIn("python do_install:append", text)
        self.assertIn('"vss/vss.json"', text)
        for forbidden in ("vss-test.json", "ExecStart", "LoadCredential", "BindReadOnlyPaths", "setenforce"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
