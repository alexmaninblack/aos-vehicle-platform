# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:remove = "file://deprovision.sh"
SRC_URI:append = " file://deprovision.sh"

do_install:append() {
    install -m 0755 ${WORKDIR}/deprovision.sh ${D}/opt/aos/deprovision.sh
}
