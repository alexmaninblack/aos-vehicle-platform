# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from tools import validate_iam_pkcs11_allocator as validator


class IamPkcs11AllocatorTests(unittest.TestCase):
    def test_transform_inspection_does_not_create_in_tree_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transform = Path(directory) / "transform.py"
            transform.write_text("MODULE = {'id': 'test'}\n", encoding="utf-8")
            with patch.object(validator, "IAM_TRANSFORM", transform), \
                    patch("sys.pycache_prefix", None), patch("sys.dont_write_bytecode", False):
                self.assertEqual(validator._load_kuksa_module(), {"id": "test"})
            self.assertEqual(list(Path(directory).iterdir()), [transform])

    def test_tracked_allocator_closure_passes(self) -> None:
        validator.validate()

    def test_effective_topology_is_exactly_three_session_keys(self) -> None:
        self.assertEqual(
            validator.effective_session_keys(),
            (
                (validator.SOFTHSM_LIBRARY, "aos-kuksa", validator.FLAGS),
                (validator.SOFTHSM_LIBRARY, "aoscloud", validator.FLAGS),
                (validator.SOFTHSM_LIBRARY, "aoscore", validator.FLAGS),
            ),
        )

    def test_legacy_two_three_pair_reproduces_the_failure(self) -> None:
        with self.assertRaisesRegex(MemoryError, "allocator exhausted"):
            validator.replay_access_order(cache_capacity=2, allocator_capacity=3)

    def test_three_four_pair_passes_without_lru(self) -> None:
        self.assertEqual(
            validator.replay_access_order(cache_capacity=3, allocator_capacity=4),
            4,
        )

    def test_cache_two_allocator_four_is_not_accepted(self) -> None:
        with self.assertRaisesRegex(AssertionError, "must not invoke LRU"):
            validator.replay_access_order(cache_capacity=2, allocator_capacity=4)

    def test_mainline_source_check_requires_application_allocator_owner(self) -> None:
        with self.assertRaisesRegex(validator.ValidationError, "app-root is required"):
            validator.validate(source_root=Path('/not-read'))

    def test_obsolete_fixed_allocator_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / 'iam.bbappend'
            recipe.write_text(validator.IAM_APPEND.read_text() + '\nCXXFLAGS:append = " -DAOS_CONFIG_PKCS11_SESSIONS_PER_LIB=4"\n')
            with patch.object(validator, 'IAM_APPEND', recipe), patch.object(validator, 'ROOT', Path(directory)):
                with self.assertRaisesRegex(validator.ValidationError, 'unexpected recipe scope'):
                    validator.validate_recipe_scope()


if __name__ == "__main__":
    unittest.main()
