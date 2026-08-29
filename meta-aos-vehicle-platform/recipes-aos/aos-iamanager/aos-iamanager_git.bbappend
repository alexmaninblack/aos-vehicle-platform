# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://enable-permissions-handler.py"

inherit python3native

do_install:append() {
    ${PYTHON} ${WORKDIR}/enable-permissions-handler.py \
        --config ${D}${sysconfdir}/aos/iam.cfg
}
