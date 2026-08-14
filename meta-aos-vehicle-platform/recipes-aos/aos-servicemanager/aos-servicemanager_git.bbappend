# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " \
    file://0001-add-production-systemd-slot-component-runtime.patch \
    file://systemd-slot-component \
"

EXTRA_OECMAKE:append = " \
    -DAOS_SYSTEMD_SLOT_COMPONENT_DIR=${WORKDIR}/systemd-slot-component \
"
