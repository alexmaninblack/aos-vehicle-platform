# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Static contract tests; these do not claim native mount or guest qualification."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import quality_gate


ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIRECTORY = Path("meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files")
ASSET_PATH = RESOURCE_DIRECTORY / "resources-demo-services.cfg"


class ServiceRuntimeInputsTests(unittest.TestCase):
    def setUp(self):
        self.resources = json.loads((ROOT / ASSET_PATH).read_text(encoding="utf-8"))

    def test_only_exact_brake_and_tire_resources_are_declared(self):
        self.assertEqual(
            ["brake-runtime-inputs", "tire-runtime-inputs"],
            [item["name"] for item in self.resources],
        )
        for item in self.resources:
            self.assertEqual({"name", "mounts"}, set(item))
            self.assertEqual(1, len(item["mounts"]))

    def test_each_service_gets_only_its_own_nonrecursive_read_only_directory(self):
        for service, resource in zip(("brake", "tire"), self.resources):
            with self.subTest(service=service):
                self.assertEqual(
                    {
                        "destination": "/run/aosedge/platform/service-inputs",
                        "type": "bind",
                        "source": f"/run/aos-demo-service-inputs/{service}",
                        "options": ["bind", "ro", "nosuid", "nodev", "noexec"],
                    },
                    resource["mounts"][0],
                )
        sources = [Path(item["mounts"][0]["source"]) for item in self.resources]
        self.assertEqual(2, len(set(sources)))
        self.assertFalse(any(left in right.parents for left in sources for right in sources))

    def test_native_socket_authority_and_private_session_mount_contract(self):
        resources = json.loads((ROOT / RESOURCE_DIRECTORY / "resources.cfg").read_text())
        self.assertEqual(
            [
                {"name": "kuksa", "hosts": [{"ip": "10.0.0.100", "hostname": "Server"}]},
                {
                    "name": "kuksa-auth-client",
                    "sharedCount": 4,
                    "groups": ["aos-kuksa-clients"],
                    "mounts": [
                        {
                            "destination": "/run/aosedge/platform/kuksa-auth",
                            "type": "bind",
                            "source": "/run/aos-kuksa-auth-compat",
                            "options": ["rbind", "ro", "nosuid", "nodev", "noexec"],
                        },
                        {
                            "destination": "/run/aosedge/secrets/kuksa",
                            "type": "tmpfs",
                            "source": "tmpfs",
                            "options": ["rw", "nosuid", "nodev", "noexec", "mode=1777", "size=65536"],
                        },
                    ],
                },
            ],
            resources,
        )

    def test_no_token_owner_sm_extension_is_staged(self):
        recipe = (ROOT / RESOURCE_DIRECTORY.parent / "aos-servicemanager_git.bbappend").read_text()
        self.assertNotIn("kuksatokenmount", recipe)
        self.assertNotIn("0002-bind-kuksa-token", recipe)
        self.assertIn("0001-add-production-systemd-slot-component-runtime.patch", recipe)
        self.assertFalse((ROOT / RESOURCE_DIRECTORY / "kuksatokenmount.hpp").exists())

    def test_declaration_is_not_enabled_in_factory_config_or_recipes(self):
        sm_config = json.loads((ROOT / RESOURCE_DIRECTORY / "sm.cfg").read_text())
        self.assertNotIn("resourcesConfigFile", sm_config)
        layer = ROOT / "meta-aos-vehicle-platform"
        recipes = list(layer.rglob("*.bb")) + list(layer.rglob("*.bbappend"))
        for recipe in recipes:
            with self.subTest(recipe=recipe.relative_to(ROOT)):
                self.assertNotIn(ASSET_PATH.name, recipe.read_text())
                self.assertNotIn("aos-demo-service-inputs", recipe.read_text())

    def test_no_runtime_payload_or_certificate_is_packaged_with_asset(self):
        directory = ROOT / RESOURCE_DIRECTORY
        self.assertFalse((directory / "metadata.json").exists())
        self.assertFalse((directory / "kuksa-ca.pem").exists())
        serialized = json.dumps(self.resources)
        for forbidden in ("server.pem", "server.key", "token", "AOS_SECRET", "uid=", "gid=", "context="):
            self.assertNotIn(forbidden, serialized)

    def test_exact_asset_inherits_spdx_from_its_owned_contract(self):
        self.assertEqual([], quality_gate.check_spdx([ROOT / ASSET_PATH]))

    def test_spdx_exemption_rejects_misnamed_resources_and_unlicensed_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / ASSET_PATH
            asset.parent.mkdir(parents=True)
            owner = root / "docs/service-runtime-inputs.md"
            owner.parent.mkdir()
            owner.write_text((ROOT / "docs/service-runtime-inputs.md").read_text())
            asset.write_text('[{"name":"unexpected"}]\n')
            with mock.patch.object(quality_gate, "ROOT", root):
                self.assertEqual(2, len(quality_gate.check_spdx([asset])))
                asset.write_text(json.dumps(self.resources))
                owner.write_text("Unlicensed owner\n")
                self.assertEqual(2, len(quality_gate.check_spdx([asset])))


if __name__ == "__main__":
    unittest.main()
