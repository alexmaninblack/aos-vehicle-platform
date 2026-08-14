# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

SUMMARY = "Bootstrap profile for the Aos vehicle data provider component"
DESCRIPTION = "Fixed launcher, empty-store, health, and systemd interfaces for the OEM FOTA provider runtime"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

SRC_URI = " \
    file://aos-vehicle-data-provider-launcher.c \
    file://aos-vehicle-data-provider-health \
    file://aos-vehicle-data-provider.service \
    file://aos-vehicle-data-provider-bootstrap.service \
    file://aos-vehicle-data-provider.conf \
    file://30-aos-vehicle-data-provider.conf \
"

S = "${WORKDIR}"

inherit systemd

SYSTEMD_SERVICE:${PN} = "aos-vehicle-data-provider-bootstrap.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} \
        ${WORKDIR}/aos-vehicle-data-provider-launcher.c \
        -o ${B}/aos-vehicle-data-provider-launcher
}

do_install() {
    install -d ${D}${libexecdir}
    install -m 0755 ${B}/aos-vehicle-data-provider-launcher ${D}${libexecdir}
    install -m 0755 ${WORKDIR}/aos-vehicle-data-provider-health ${D}${libexecdir}

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider.service ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider-bootstrap.service ${D}${systemd_system_unitdir}

    install -d ${D}${nonarch_libdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider.conf ${D}${nonarch_libdir}/tmpfiles.d

    install -d ${D}${sysconfdir}/systemd/system/aos-sm.service.d
    install -m 0644 ${WORKDIR}/30-aos-vehicle-data-provider.conf \
        ${D}${sysconfdir}/systemd/system/aos-sm.service.d
}

FILES:${PN} += " \
    ${libexecdir}/aos-vehicle-data-provider-launcher \
    ${libexecdir}/aos-vehicle-data-provider-health \
    ${systemd_system_unitdir}/aos-vehicle-data-provider.service \
    ${nonarch_libdir}/tmpfiles.d/aos-vehicle-data-provider.conf \
    ${sysconfdir}/systemd/system/aos-sm.service.d/30-aos-vehicle-data-provider.conf \
"
