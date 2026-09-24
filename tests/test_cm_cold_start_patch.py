# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Package boundary; the native launcher suite owns behavioral assertions."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'meta-aos-vehicle-platform/recipes-aos/aos-communicationmanager'
NAME = '0007-reconcile-generated-components-on-start.patch'


class CMColdStartPatchTests(unittest.TestCase):
    def test_applied_once_after_existing_lifecycle_patch(self):
        text = (RECIPE / 'aos-communicationmanager_git.bbappend').read_text()
        self.assertEqual(text.count('file://' + NAME), 1)
        self.assertIn('file://' + NAME + ';patchdir=../service-update-deps/aos_core_lib_cpp', text)
        self.assertLess(text.index('0002-mainline-cm-instance-lifecycle.patch'), text.index(NAME))

    def test_scope_is_startup_intent_not_observed_status_authority(self):
        text = (RECIPE / 'files' / NAME).read_text()
        paths = set(re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M))
        self.assertEqual(paths, {'src/core/cm/launcher/' + name for name in (
            'launcher.cpp', 'runrequestsloader.cpp', 'runrequestsloader.hpp', 'tests/launcher.cpp')})
        self.assertIn('mForceRebalance = hasNotScheduledInstance || mRunRequestsLoader.HasGeneratedRequests()', text)
        self.assertIn('request.mNumInstances == 0 && request.mUpdateItemType == UpdateItemTypeEnum::eComponent', text)
        self.assertIn('Values(0, 1, 2, 3, 4, 5)', text)
        self.assertNotIn('/var/aos/', text)
        self.assertNotIn('brake-health', text)
