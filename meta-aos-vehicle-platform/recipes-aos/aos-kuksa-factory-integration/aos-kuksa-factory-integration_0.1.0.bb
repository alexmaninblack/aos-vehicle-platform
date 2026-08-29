# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

SUMMARY = "Aos KUKSA Factory credential lifecycle integration"
DESCRIPTION = "Fixed token initialization, finite systemd wiring and deprovision runtime cleanup."
HOMEPAGE = "https://github.com/maninblack/aos-vehicle-platform"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

FILESEXTRAPATHS:prepend := "${THISDIR}/../../../authorization/aos-kuksa-factory-integration:${THISDIR}/files:"
SRC_URI = " \
    file://CMakeLists.txt;subdir=source \
    file://include;subdir=source \
    file://src;subdir=source \
    file://tests;subdir=source \
    file://aos-kuksa-substrate.target \
    file://aos-kuksa-provision-reset.service \
    file://aos-kuksa-token-init.service \
    file://aos-kuksa-tls-prepare.service \
    file://aos-kuksa-runtime-cleanup.service \
    file://aos-iam-prov.service.d/20-kuksa-token-init.conf \
    file://aos-iam.service.d/20-kuksa-token-init.conf \
    file://kuksa-databroker.service.d/20-kuksa-verifier.conf \
    file://aos-vehicle-data-provider.service.d/20-kuksa-provider.conf \
"

S = "${WORKDIR}/source"

inherit cmake systemd

DEPENDS = "openssl softhsm"
RDEPENDS:${PN} = "aos-deprov aos-iamanager aos-kuksa-auth-compat aos-servicemanager aos-vehicle-data-provider-platform coreutils kuksa-databroker softhsm"

EXTRA_OECMAKE = "-DBUILD_TESTING=ON"

SYSTEMD_PACKAGES = "${PN}"
SYSTEMD_SERVICE:${PN} = "aos-kuksa-substrate.target"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install:append() {
    install -d ${D}${systemd_system_unitdir}
    for unit in aos-kuksa-substrate.target aos-kuksa-provision-reset.service \
        aos-kuksa-token-init.service aos-kuksa-tls-prepare.service \
        aos-kuksa-runtime-cleanup.service; do
        install -m 0644 ${WORKDIR}/${unit} ${D}${systemd_system_unitdir}/${unit}
    done
    for dropin in \
        aos-iam-prov.service.d/20-kuksa-token-init.conf \
        aos-iam.service.d/20-kuksa-token-init.conf \
        kuksa-databroker.service.d/20-kuksa-verifier.conf \
        aos-vehicle-data-provider.service.d/20-kuksa-provider.conf; do
        install -d ${D}${systemd_system_unitdir}/$(dirname ${dropin})
        install -m 0644 ${WORKDIR}/${dropin} ${D}${systemd_system_unitdir}/${dropin}
    done
}

FILES:${PN} = " \
    ${libexecdir}/aos-kuksa-token-init \
    ${libexecdir}/aos-kuksa-runtime-cleanup \
    ${libexecdir}/aos-kuksa-tls-prepare \
    ${systemd_system_unitdir}/aos-kuksa-substrate.target \
    ${systemd_system_unitdir}/aos-kuksa-provision-reset.service \
    ${systemd_system_unitdir}/aos-kuksa-token-init.service \
    ${systemd_system_unitdir}/aos-kuksa-tls-prepare.service \
    ${systemd_system_unitdir}/aos-kuksa-runtime-cleanup.service \
    ${systemd_system_unitdir}/aos-iam-prov.service.d/20-kuksa-token-init.conf \
    ${systemd_system_unitdir}/aos-iam.service.d/20-kuksa-token-init.conf \
    ${systemd_system_unitdir}/kuksa-databroker.service.d/20-kuksa-verifier.conf \
    ${systemd_system_unitdir}/aos-vehicle-data-provider.service.d/20-kuksa-provider.conf \
"
