"""Static packaging boundary; compiled Rust behavior is also gated by the recipe."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "meta-aos-vehicle-platform/recipes-connectivity/kuksa-databroker"
PATCH = RECIPE / "files/0003-val-v1-preserve-source-timestamps.patch"

class KuksaSourceTimestampTests(unittest.TestCase):
    def test_exact_source_and_production_delta(self):
        text = PATCH.read_text()
        self.assertIn("Pinned-Upstream-Commit: 30e5c13abc496d0b39aaa6c25acebb088b9902e3", text)
        self.assertIn("Frozen-Source-Git-Blob: d9b972d13523b821682d748da19d5e76456865d3", text)
        self.assertEqual(re.findall(r"^diff --git (.+)$", text, re.M), [
            "a/databroker/src/grpc/kuksa_val_v1/conversions.rs b/databroker/src/grpc/kuksa_val_v1/conversions.rs"])
        production = text.split("@@ -338,3", 1)[0]
        additions = [l[1:].strip() for l in production.splitlines() if l.startswith('+') and not l.startswith('+++')]
        removals = [l[1:].strip() for l in production.splitlines() if l.startswith('-') and not l.startswith('---')]
        self.assertEqual(additions, ["timestamp: Some(from.source_ts.unwrap_or(from.ts).into()),"] * 16)
        self.assertEqual(removals, ["timestamp: Some(from.ts.into()),"] * 16)

    def test_behavior_cases_are_compiled_before_packaging(self):
        text = PATCH.read_text()
        for name in ["preserves_all_values_and_nanoseconds", "roundtrip_does_not_refresh_old_or_future_data",
                     "preserves_batch_across_receipt_millisecond_boundary", "missing_retains_receipt_fallback",
                     "not_available_stays_absent", "value_only_conversion_has_no_invented_time"]:
            self.assertIn("fn source_timestamp_" + name + "()", text)
        recipe = (RECIPE / "kuksa-databroker_git.bbappend").read_text()
        self.assertIn('SRC_URI += "file://0003-val-v1-preserve-source-timestamps.patch"', recipe)
        self.assertIn('"${CARGO}" test ${CARGO_BUILD_FLAGS} -p databroker --lib source_timestamp_tests -- --nocapture', recipe)
        self.assertIn("CARGO_TARGET_AARCH64_AOS_LINUX_GNU_RUNNER", recipe)
        self.assertNotIn("do_install", recipe)

if __name__ == '__main__':
    unittest.main()
