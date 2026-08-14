# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " \
    file://vehicle_data_provider.te \
    file://vehicle_data_provider.fc \
    file://vehicle_data_provider.if \
"

do_compile:prepend() {
    install -m 0644 ${WORKDIR}/vehicle_data_provider.te ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/vehicle_data_provider.fc ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/vehicle_data_provider.if ${S}/policy/modules/services
}
