# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Pure image configuration units; no image task, process or target activity."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'camera-access/src'))
from aos_camera_access.vision_image import select,select_communication


class NativeProfileTests(unittest.TestCase):
    def setUp(self):
        self.camera=json.loads((ROOT/'contracts/camera-access/native-profile.json').read_bytes())
        self.services=json.loads((ROOT/'contracts/camera-access/native-services-profile.json').read_bytes())
        self.sm=dict(runtimes=[dict(plugin='systemd-slot-component',type='vehicle-data-provider',
            config=dict(unit='aos-vehicle-data-provider.service'))])
        self.cm=dict(imageManager=dict(installPath='/var/aos/workdirs/cm/imagemanager/install',downloadPath='/var/aos/workdirs/cm/imagemanager/downloads'))

    def test_native_flag_adds_only_five_exact_readonly_resources(self):
        original=copy.deepcopy(self.sm)
        sm,resources=select(self.sm,[],self.camera,self.services)
        self.assertEqual(self.sm,original)
        self.assertEqual([r['name'] for r in resources],['vision-camera-read']+['vision-'+r for r in self.services['roles']])
        self.assertEqual(sm['imageManager']['imagePath'],self.services['imagePaths']['service'])
        for row in resources:
            self.assertEqual(row['sharedCount'],1)
            self.assertEqual(row['mounts'][0]['options'],['bind','ro','nosuid','nodev','noexec'])
        _,legacy=select(self.sm,[],self.camera)
        self.assertEqual(len(legacy),1);self.assertNotIn('imageManager',self.sm)

    def test_communication_uses_standard_install_path_only(self):
        value=select_communication(self.cm,self.services)
        self.assertEqual(value['imageManager']['installPath'],self.services['imagePaths']['communication'])
        self.assertEqual(value['imageManager']['downloadPath'],self.cm['imageManager']['downloadPath'])
        self.assertEqual(self.cm['imageManager']['installPath'],'/var/aos/workdirs/cm/imagemanager/install')
        with self.assertRaises(ValueError):select_communication(value,self.services)

    def test_known_native_accounts_and_no_boot_enabled_exchange(self):
        self.assertEqual((self.services['ownerUid'],self.services['ownerGid'],self.services['cameraUid'],self.services['cameraGid']),(989,989,992,990))
        self.assertEqual(list(self.services['groups'].values()),[988,987,986,985])
        unit=(ROOT/'tests/fixtures/vision-native-exchange/aos-vision-exchange.service').read_text()
        self.assertNotIn('[Install]',unit);self.assertIn('Restart=no',unit);self.assertIn('SocketBindDeny=any',unit)
        image=(ROOT/'qualification/vision-services-1.conf').read_text()
        self.assertIn('6.1.1-vision-camera.6',image);self.assertIn('AOS_VISION_NATIVE_SERVICES:forcevariable = "1"',image)


if __name__=='__main__':unittest.main()
