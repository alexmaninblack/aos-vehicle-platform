# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
# Full Vision FOTA needs this native tool for the first time. Preserve the
# pinned 4.6.1 commit; the upstream recipe's v6.1.1 branch is no longer usable.
# Do not alter target packages, Main defaults, revisions or network guards.
SRC_URI:remove:class-native = "${@'git://github.com/plougher/squashfs-tools.git;protocol=https;branch=v6.1.1' if d.getVar('AOS_VISION_CAMERA_INGRESS') == '1' else ''}"
SRC_URI:append:class-native = "${@' git://github.com/plougher/squashfs-tools.git;protocol=https;nobranch=1' if d.getVar('AOS_VISION_CAMERA_INGRESS') == '1' else ''}"

python __anonymous() {
    if d.getVar('AOS_VISION_CAMERA_INGRESS') == '1' and bb.data.inherits_class('native', d):
        if d.getVar('SRCREV') != 'd8cb82d9840330f9344ec37b992595b5d7b44184':
            bb.fatal('Vision native squashfs source revision changed')
}
