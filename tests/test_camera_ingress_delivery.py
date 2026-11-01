# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class DeliverySourceTests(unittest.TestCase):
    def test_vision_delivery_is_explicit_and_keeps_manufacturing_baseline(self):
        old=(ROOT/'qualification/vision-bootstrap-1.conf').read_text()
        new=(ROOT/'qualification/vision-ingress-1.conf').read_text()
        self.assertIn('6.1.1-vision-camera.3',old)
        self.assertIn('require vision-bootstrap-1.conf',new)
        self.assertIn('6.1.1-vision-camera.4',new)
        self.assertIn('AOS_VISION_CAMERA_INGRESS:forcevariable = "1"',new)

    def test_native_policy_reads_sealed_store_not_the_transient_code_type(self):
        folder=ROOT/'meta-aos-vehicle-platform/recipes-security/refpolicy/files'
        te=(folder/'camera_ingress.te').read_text();fc=(folder/'camera_ingress.fc').read_text()
        self.assertIn('## <summary>',(folder/'camera_ingress.if').read_text())
        self.assertIn('allow camera_ingress_t camera_access_store_t:file { getattr open read };',te)
        self.assertNotIn('camera_ingress_code_t',te)
        for forbidden in ('execute_no_trans','name_bind','self:capability','permissive camera_ingress','unconfined'):
            self.assertNotIn(forbidden,te)
        self.assertIn('camera_ingress_exec_t',fc);self.assertIn('camera_access_unit_t',fc)

    def test_main_default_has_no_ingress_and_unit_is_not_boot_enabled(self):
        recipe=(ROOT/'meta-aos-vehicle-platform/recipes-aos/aos-camera-access-platform/aos-camera-access-platform_0.1.0.bb').read_text()
        self.assertIn('AOS_VISION_CAMERA_INGRESS ??= "0"',recipe)
        self.assertIn('SYSTEMD_SERVICE:${PN} = "aos-camera-access-bootstrap.service"',recipe)
        self.assertNotIn('SYSTEMD_SERVICE:${PN} += "aos-camera-ingress',recipe)
        policy=(ROOT/'meta-aos-vehicle-platform/recipes-security/refpolicy/refpolicy-aos_git.bbappend').read_text()
        self.assertIn('AOS_VISION_CAMERA_INGRESS ??= "0"',policy)
        self.assertIn('rm -f ${S}/policy/modules/services/camera_ingress.te',policy)

    def test_update_artifact_is_rootfs_envelope_not_factory_or_boot(self):
        recipe=(ROOT/'meta-aos-vehicle-platform/recipes-aos-fota/aos-rootfs/aos-rootfs-vision.bb').read_text()
        self.assertIn('require recipes-aos-fota/aos-rootfs/aos-rootfs.bb',recipe)
        self.assertIn('AOS_ROOTFS_IMAGE_TYPE = "full"',recipe)
        self.assertIn('aos-image-vision:do_rootfs',recipe)
        self.assertNotIn('aos-boot',recipe)

    def test_native_squashfs_uses_exact_commit_without_a_missing_branch(self):
        recipe=(ROOT/'meta-aos-vehicle-platform/recipes-devtools/squashfs-tools/squashfs-tools_git.bbappend').read_text()
        self.assertIn('SRC_URI:append:class-native',recipe)
        self.assertIn("d.getVar('AOS_VISION_CAMERA_INGRESS') == '1'",recipe)
        self.assertIn('d8cb82d9840330f9344ec37b992595b5d7b44184',recipe)
        self.assertIn('nobranch=1',recipe)
        self.assertNotIn('BB_NO_NETWORK',recipe)


if __name__=='__main__':unittest.main()
