# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
