# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Existing Main policy inputs remain unchanged unless the explicit Vision-only
# delivery configuration selects this domain.
AOS_VISION_CAMERA_INGRESS ??= "0"
SRC_URI:append = " ${@'file://camera_ingress.te file://camera_ingress.fc file://camera_ingress.if' if d.getVar('AOS_VISION_CAMERA_INGRESS') == '1' else ''}"

SRC_URI += " \
    file://camera_access.te \
    file://camera_access.fc \
    file://camera_access.if \
    file://0001-corenetwork-label-aos-kuksa-iam-port.patch \
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
    if [ "${AOS_VISION_CAMERA_INGRESS}" = "1" ]; then
        install -m 0644 ${WORKDIR}/camera_ingress.te ${S}/policy/modules/services
        install -m 0644 ${WORKDIR}/camera_ingress.fc ${S}/policy/modules/services
        install -m 0644 ${WORKDIR}/camera_ingress.if ${S}/policy/modules/services
    else
        # This recipe's warm S can have been used by the explicit Vision task.
        # Remove only our three optional inputs before rebuilding Main policy.
        rm -f ${S}/policy/modules/services/camera_ingress.te ${S}/policy/modules/services/camera_ingress.fc ${S}/policy/modules/services/camera_ingress.if
    fi
    install -m 0644 ${WORKDIR}/camera_access.te ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/camera_access.fc ${S}/policy/modules/services
    install -m 0644 ${WORKDIR}/camera_access.if ${S}/policy/modules/services
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
