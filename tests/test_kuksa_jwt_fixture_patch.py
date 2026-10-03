"""Bound the test fixture repair without weakening production JWT validation."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'meta-aos-vehicle-platform/recipes-connectivity/kuksa-databroker'


class JwtFixturePatchTests(unittest.TestCase):
    def test_only_decoder_test_region_changes(self):
        text = (RECIPE / 'files/0004-test-renewable-jwt-fixtures.patch').read_text()
        self.assertEqual(re.findall(r'^--- (.+)$', text, re.M),
                         ['a/databroker/src/authorization/jwt/decoder.rs'])
        self.assertTrue(all(int(n) >= 146 for n in re.findall(r'^@@ -(\d+),', text, re.M)))
        self.assertIn('test_expired_historical_token', text)
        self.assertIn('test_parse_fresh_token_with_full_validation', text)
        self.assertIn('now + 300', text)
        self.assertIn('now - 120', text)
        self.assertIn('ExpiredSignature', text)
        self.assertIn('InvalidAudience', text)
        additions = '\n'.join(l for l in text.splitlines() if l.startswith('+'))
        for forbidden in ('validate_exp', 'validate_aud', 'insecure', 'dangerous'):
            self.assertNotIn(forbidden, additions)
        self.assertIn('../../../../certificates/jwt/jwt.key', additions)

    def test_full_library_suite_is_a_build_gate(self):
        recipe = (RECIPE / 'kuksa-databroker_git.bbappend').read_text()
        self.assertIn('file://0004-test-renewable-jwt-fixtures.patch', recipe)
        self.assertIn('"${CARGO}" test ${CARGO_BUILD_FLAGS} -p databroker --lib\n', recipe)
        self.assertNotIn('--skip', recipe)
        config = (ROOT / 'qualification/factory-41.conf').read_text()
        self.assertIn('require factory-40.conf', config)
        self.assertIn('6.1.1-maninblack.41', config)


if __name__ == '__main__':
    unittest.main()
