# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

SUMMARY = "Bootstrap profile for the Aos vehicle data provider component"
DESCRIPTION = "Fixed launcher, atomic A/B lifecycle, health, and systemd interfaces for the OEM FOTA provider runtime"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

SRC_URI = " \
    file://aos-vehicle-data-provider-launcher.c \
    file://aos-vehicle-data-provider-health \
    file://aos-vehicle-data-provider.service \
    file://aos-vehicle-data-provider-selftest@.service \
    file://aos-vehicle-data-provider-bootstrap.service \
    file://aos-vehicle-data-provider-store-prepare.service \
    file://aos-vehicle-data-provider-store.mount \
    file://aos-vehicle-data-provider-store-prepare \
    file://aos-vehicle-data-provider-store-check \
    file://aos-vehicle-data-provider-loop.conf \
    file://aos-vehicle-data-provider.conf \
    file://30-aos-vehicle-data-provider.conf \
"

S = "${WORKDIR}"

inherit systemd

RDEPENDS:${PN} += " \
    e2fsprogs-e2fsck \
    e2fsprogs-mke2fs \
    kernel-module-loop \
    util-linux-blkid \
    util-linux-fallocate \
    util-linux-losetup \
"

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
    install -m 0755 ${WORKDIR}/aos-vehicle-data-provider-store-prepare ${D}${libexecdir}
    install -m 0755 ${WORKDIR}/aos-vehicle-data-provider-store-check ${D}${libexecdir}

    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider.service ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider-selftest@.service \
        ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider-bootstrap.service ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider-store-prepare.service \
        ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider-store.mount \
        '${D}${systemd_system_unitdir}/var-aos-workdirs-sm-runtimes-systemd\x2dslot\x2dcomponent.mount'

    install -d ${D}${sysconfdir}/modules-load.d
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider-loop.conf \
        ${D}${sysconfdir}/modules-load.d

    install -d ${D}${libdir}/aos-vehicle-data-provider
    install -m 0644 ${WORKDIR}/aos-vehicle-data-provider.conf \
        ${D}${libdir}/aos-vehicle-data-provider/store.conf

    install -d ${D}${sysconfdir}/systemd/system/aos-sm.service.d
    install -m 0644 ${WORKDIR}/30-aos-vehicle-data-provider.conf \
        ${D}${sysconfdir}/systemd/system/aos-sm.service.d

    install -d ${D}/var/aos/workdirs/sm/runtimes/systemd-slot-component
}

FILES:${PN} += " \
    ${libexecdir}/aos-vehicle-data-provider-launcher \
    ${libexecdir}/aos-vehicle-data-provider-health \
    ${libexecdir}/aos-vehicle-data-provider-store-prepare \
    ${libexecdir}/aos-vehicle-data-provider-store-check \
    ${systemd_system_unitdir}/aos-vehicle-data-provider.service \
    ${systemd_system_unitdir}/aos-vehicle-data-provider-selftest@.service \
    ${systemd_system_unitdir}/aos-vehicle-data-provider-store-prepare.service \
    ${systemd_system_unitdir}/var-aos-workdirs-sm-runtimes-systemd*component.mount \
    ${libdir}/aos-vehicle-data-provider/store.conf \
    ${sysconfdir}/modules-load.d/aos-vehicle-data-provider-loop.conf \
    ${sysconfdir}/systemd/system/aos-sm.service.d/30-aos-vehicle-data-provider.conf \
    /var/aos/workdirs/sm/runtimes/systemd-slot-component \
"
