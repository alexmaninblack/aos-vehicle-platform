# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import quality_gate


class DependencyInventoryTests(unittest.TestCase):
    def valid_inventory(self) -> dict[str, object]:
        return {
            "runtime": [
                {
                    "name": "git dependency",
                    "revision": "a" * 40,
                    "license": "Apache-2.0 & BSD-3-Clause & MPL-2.0",
                },
                {
                    "name": "archive dependency",
                    "revision": "archive-sha256:" + "b" * 64,
                    "artifactSha256": "b" * 64,
                    "license": "BSD-2-Clause & ISC",
                },
            ],
            "build": [],
            "ci": [],
        }

    def test_git_archive_and_exact_conjunctions_are_accepted(self) -> None:
        self.assertEqual([], quality_gate.validate_dependency_inventory(self.valid_inventory()))

    def test_archive_hash_mismatch_is_rejected(self) -> None:
        inventory = self.valid_inventory()
        inventory["runtime"][1]["artifactSha256"] = "c" * 64
        self.assertRegex(
            "\n".join(quality_gate.validate_dependency_inventory(inventory)),
            "archive and artifact hashes differ",
        )

    def test_malformed_pins_are_rejected(self) -> None:
        for revision in ("A" * 40, "archive-sha256:" + "z" * 64, "v1.0"):
            with self.subTest(revision=revision):
                inventory = self.valid_inventory()
                inventory["runtime"][0]["revision"] = revision
                self.assertTrue(quality_gate.validate_dependency_inventory(inventory))

    def test_or_with_parentheses_unknown_and_empty_terms_are_rejected(self) -> None:
        for expression in (
            "Apache-2.0 OR MIT",
            "Apache-2.0 WITH LLVM-exception",
            "(Apache-2.0)",
            "Apache-2.0 & Unknown",
            "Apache-2.0 & ",
        ):
            with self.subTest(expression=expression):
                inventory = self.valid_inventory()
                inventory["runtime"][0]["license"] = expression
                self.assertTrue(quality_gate.validate_dependency_inventory(inventory))

    def test_existing_single_license_semantics_remain_valid(self) -> None:
        inventory = self.valid_inventory()
        inventory["runtime"][0]["license"] = "MIT"
        self.assertEqual([], quality_gate.validate_dependency_inventory(inventory))

    def test_only_exact_structured_resources_path_inherits_owner_spdx(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = root / (
                "meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/"
                "resources.cfg"
            )
            owner = root / (
                "meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/"
                "aos-servicemanager_git.bbappend"
            )
            resources.parent.mkdir(parents=True)
            owner.parent.mkdir(parents=True, exist_ok=True)
            resources.write_text(
                '[{"name":"kuksa"},{"name":"kuksa-auth-client"}]\n',
                encoding="utf-8",
            )
            owner.write_text(
                "# SPDX-FileCopyrightText: 2026 maninblack\n"
                "# SPDX-License-Identifier: Apache-2.0\n",
                encoding="utf-8",
            )
            unrelated = root / "unrelated.json"
            unrelated.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(quality_gate, "ROOT", root):
                self.assertEqual([], quality_gate.check_spdx([resources]))
                errors = quality_gate.check_spdx([unrelated])
                self.assertEqual(2, len(errors))
                self.assertTrue(all(error.startswith("unrelated.json:") for error in errors))

    def test_resources_exemption_requires_the_exact_schema_and_licensed_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = root / (
                "meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/"
                "resources.cfg"
            )
            owner = root / (
                "meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/"
                "aos-servicemanager_git.bbappend"
            )
            resources.parent.mkdir(parents=True)
            owner.parent.mkdir(parents=True, exist_ok=True)
            resources.write_text('[{"name":"kuksa"}]\n', encoding="utf-8")
            owner.write_text("unlicensed owner\n", encoding="utf-8")
            with mock.patch.object(quality_gate, "ROOT", root):
                errors = quality_gate.check_spdx([resources])
                self.assertEqual(2, len(errors))


if __name__ == "__main__":
    unittest.main()
