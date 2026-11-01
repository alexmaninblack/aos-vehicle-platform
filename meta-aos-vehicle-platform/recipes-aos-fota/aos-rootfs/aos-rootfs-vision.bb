# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
require recipes-aos-fota/aos-rootfs/aos-rootfs.bb
SUMMARY = "Vision-only native rootfs update, not a manufacturing disk"
IMAGE_BASENAME = "aos-image-vision"
AOS_ROOTFS_SOURCE_DIR = "${TMPDIR}/work-shared/aos-vision-fota-${MACHINE}/rootfs"
AOS_ROOTFS_IMAGE_TYPE = "full"
AOS_ROOTFS_IMAGE_FILE = "${DEPLOY_DIR_IMAGE}/update/aos-vision-rootfs-${AOS_ROOTFS_IMAGE_VERSION}.squashfs"
# do_image runs IMAGE_PREPROCESS_COMMAND: notably systemd_preset_all and the
# final SELinux labelling. do_rootfs alone is not a boot-ready FOTA input.
# This does not invoke do_image_ext4, boot construction or disk assembly.
do_create_rootfs_image[depends] += "aos-image-vision:do_prepare_vision_rootfs_fota"
