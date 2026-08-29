# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BBAPPEND = ROOT / (
    "meta-aos-vehicle-platform/recipes-connectivity/kuksa-databroker/"
    "kuksa-databroker_git.bbappend"
)
PATCH = BBAPPEND.parent / "files" / (
    "0002-authorization-accept-decimal-digits-in-scope-path.patch"
)
BASE_COMMIT = "570d17821edfd85915e688f7239a04eb4fc1f535"
FROZEN_SCOPE_BLOB = "263b277d155cc2b642883724b3cd1f24abb9525d"
FROZEN_SCOPE_SHA256 = (
    "d9abb22c118d63f728b12a1d06bc10c8e72848aaef07181dc5fbabf369a69e2b"
)
ALLOWED_PATHS = {
    "meta-aos-vehicle-platform/recipes-connectivity/kuksa-databroker/"
    "kuksa-databroker_git.bbappend",
    "meta-aos-vehicle-platform/recipes-connectivity/kuksa-databroker/files/"
    "0002-authorization-accept-decimal-digits-in-scope-path.patch",
    "tests/test_kuksa_databroker_scope_patch.py",
}


def changed_paths() -> set[str]:
    committed = subprocess.run(
        ["git", "diff", "--name-only", BASE_COMMIT],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    dirty = {
        entry[3:].decode("utf-8")
        for entry in status
        if entry and len(entry) >= 4
    }
    return set(committed) | dirty


class KuksaDatabrokerScopePatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bbappend = BBAPPEND.read_text(encoding="utf-8")
        self.patch = PATCH.read_text(encoding="utf-8")

    def test_bbappend_has_only_bounded_patch_wiring(self) -> None:
        expected = (
            "# SPDX-FileCopyrightText: 2026 maninblack\n"
            "# SPDX-License-Identifier: Apache-2.0\n\n"
            'FILESEXTRAPATHS:prepend := "${THISDIR}/files:"\n\n'
            "SRC_URI += "
            '"file://0002-authorization-accept-decimal-digits-in-scope-path.patch"\n\n'
            "do_compile:append() {\n"
            '    export CARGO_TARGET_AARCH64_AOS_LINUX_RUNNER="'
            "${RECIPE_SYSROOT}/lib/ld-linux-aarch64.so.1 --library-path "
            '${RECIPE_SYSROOT}/lib:${RECIPE_SYSROOT}/usr/lib"\n'
            '    bbnote "Running scoped KUKSA authorization::jwt::scope tests"\n'
            '    "${CARGO}" test ${CARGO_BUILD_FLAGS} -p databroker --lib '
            "authorization::jwt::scope -- --nocapture\n"
            "}\n"
        )
        self.assertEqual(self.bbappend, expected)
        self.assertNotRegex(
            self.bbappend,
            r"(?m)^(?:SRCREV|PV|BRANCH|DEPENDS|RDEPENDS|FILES(?=[:\s+?=])|SYSTEMD)",
        )
        self.assertNotIn("do_install", self.bbappend)
        self.assertNotIn("do_package", self.bbappend)
        self.assertNotIn("CARGO_BUILD_FLAGS:append", self.bbappend)

    def test_patch_is_bound_to_the_frozen_scope_source(self) -> None:
        self.assertIn(f"Frozen-Source-Git-Blob: {FROZEN_SCOPE_BLOB}", self.patch)
        self.assertIn(f"Frozen-Source-SHA256: {FROZEN_SCOPE_SHA256}", self.patch)
        self.assertIn(f"index {FROZEN_SCOPE_BLOB[:7]}..", self.patch)
        diffs = re.findall(r"^diff --git (.+)$", self.patch, flags=re.MULTILINE)
        self.assertEqual(
            diffs,
            [
                "a/databroker/src/authorization/jwt/scope.rs "
                "b/databroker/src/authorization/jwt/scope.rs"
            ],
        )
        self.assertEqual(
            re.findall(r"^--- (.+)$", self.patch, flags=re.MULTILINE),
            ["a/databroker/src/authorization/jwt/scope.rs"],
        )
        self.assertEqual(
            re.findall(r"^\+\+\+ (.+)$", self.patch, flags=re.MULTILINE),
            ["b/databroker/src/authorization/jwt/scope.rs"],
        )

    def test_patch_production_delta_is_exactly_two_digit_ranges(self) -> None:
        hunks = re.findall(
            r"^(@@[^\n]+@@[^\n]*\n)(.*?)(?=^@@|^-- $)",
            self.patch,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertEqual(len(hunks), 2)
        self.assertIn("-40,14 +40,14", hunks[0][0])
        self.assertIn("-277,6 +277,69", hunks[1][0])

        removed = [
            line
            for line in hunks[0][1].splitlines()
            if line.startswith("-") and not line.startswith("---")
        ]
        added = [
            line
            for line in hunks[0][1].splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        self.assertEqual(
            removed,
            [
                "-                        [A-Z][a-zA-Z0-1]*",
                "-                            [A-Z][a-zA-Z0-1]*",
            ],
        )
        self.assertEqual(
            added,
            [
                "+                        [A-Z][a-zA-Z0-9]*",
                "+                            [A-Z][a-zA-Z0-9]*",
            ],
        )
        self.assertNotIn("[a-zA-Z0-1]*", hunks[1][1])
        self.assertNotIn("[a-zA-Z0-9]*", hunks[1][1])

    def test_required_rust_behavior_cases_are_present(self) -> None:
        required = {
            "provide:Vehicle.Chassis.Axle.Row2.Wheel.Left.Speed",
            "read:Vehicle.Test.Row9.Value",
            "actuate:Vehicle.Test.Row2030.Value",
            "read:Vehicle.Test.Row0.Value read:Vehicle.Test.Row1.Value",
            "provide:Vehicle.Chassis.Axle.2Row.Wheel.Left.Speed",
            "provide:Vehicle.Chassis..Row2.Speed",
            "provide:Vehicle.Chassis.Row2-Wheel.Speed",
            "provide:Vehicle.Chassis.Row2*.Speed",
            "provide:Vehicle.Chassis.*Row2.Speed",
            "write:Vehicle.Chassis.Axle.Row2.Wheel.Left.Speed",
            "provide:",
        }
        for value in required:
            self.assertIn(value, self.patch)
        self.assertIn("test_scope_decimal_digits", self.patch)
        self.assertIn("test_scope_decimal_digits_reject_malformed_inputs", self.patch)
        self.assertIn("Err(Error::ParseError)", self.patch)
        self.assertIn('"Vehicle.*"', self.patch)

    def test_patch_does_not_add_broader_authorization_or_service_changes(self) -> None:
        production_additions = [
            line[1:]
            for line in self.patch.splitlines()
            if line.startswith("+")
            and not line.startswith("+++")
            and "[A-Z][a-zA-Z0-9]*" in line
        ]
        self.assertEqual(
            production_additions,
            [
                "                        [A-Z][a-zA-Z0-9]*",
                "                            [A-Z][a-zA-Z0-9]*",
            ],
        )
        for forbidden in (
            "permission",
            "claim",
            "expiry",
            "decoder.rs",
            ".service",
            "SRCREV",
        ):
            self.assertNotIn(forbidden, "\n".join(production_additions))

    def test_repository_delta_stays_in_exact_three_path_boundary(self) -> None:
        delta = changed_paths()
        self.assertTrue(delta)
        self.assertLessEqual(delta, ALLOWED_PATHS)


if __name__ == "__main__":
    unittest.main()
