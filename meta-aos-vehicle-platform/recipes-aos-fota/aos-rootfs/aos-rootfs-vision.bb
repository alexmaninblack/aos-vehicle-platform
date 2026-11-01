# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
require recipes-aos-fota/aos-rootfs/aos-rootfs.bb
SUMMARY = "Vision-only native rootfs update, not a manufacturing disk"
IMAGE_BASENAME = "aos-image-vision"
AOS_ROOTFS_SOURCE_DIR = "${TMPDIR}/work-shared/aos-image-vision-${MACHINE}/rootfs"
AOS_ROOTFS_IMAGE_TYPE = "full"
AOS_ROOTFS_IMAGE_FILE = "${DEPLOY_DIR_IMAGE}/update/aos-vision-rootfs-${AOS_ROOTFS_IMAGE_VERSION}.squashfs"
do_create_rootfs_image[depends] += "aos-image-vision:do_rootfs"
