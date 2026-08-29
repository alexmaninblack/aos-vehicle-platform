# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += " \
    file://vehicle_data_provider.te \
    file://vehicle_data_provider.fc \
    file://vehicle_data_provider.if \
    file://aos_kuksa_auth_compat.te \
    file://aos_kuksa_auth_compat.fc \
    file://aos_kuksa_auth_compat.if \
    file://aos_kuksa_factory_integration.te \
    file://aos_kuksa_factory_integration.fc \
    file://aos_kuksa_factory_integration.if \
"

do_compile:prepend() {
    install -m 0644 ${WORKDIR}/vehicle_data_provider.te ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/vehicle_data_provider.fc ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/vehicle_data_provider.if ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/aos_kuksa_auth_compat.te ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/aos_kuksa_auth_compat.fc ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/aos_kuksa_auth_compat.if ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/aos_kuksa_factory_integration.te ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/aos_kuksa_factory_integration.fc ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/aos_kuksa_factory_integration.if ${S}/policy/modules/services
}
