# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
SUMMARY = "Vision-only Camera Access native OEM bootstrap"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"
SRC_URI = "file://aos-camera-access-launcher.c file://aos-camera-access-health file://aos-camera-access.service file://aos-camera-access-selftest@.service file://aos-camera-access.conf"
SRC_URI += "file://aos-camera-access-loop.c file://aos-camera-access-loop.conf \
 file://aos-camera-access-store-layout file://aos-camera-access-store-layout.service \
 file://aos-camera-access-store-prepare file://aos-camera-access-store-prepare.service \
 file://aos-camera-access-store-attach.service file://aos-camera-access-store.mount \
 file://aos-camera-access-store-check file://camera-store.conf \
 file://aos-camera-access-bootstrap.service file://30-aos-camera-access.conf"
S = "${WORKDIR}"
inherit systemd useradd
USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system aos-camera-read"
USERADD_PARAM:${PN} = "--system --home /nonexistent --no-create-home --shell /bin/false --gid aos-camera-read aos-camera-access"
RDEPENDS:${PN} = "python3-modules coreutils e2fsprogs-e2fsck e2fsprogs-mke2fs kernel-module-loop util-linux-blkid util-linux-losetup util-linux-findmnt"
# Only storage bootstrap is enabled. Camera's process is native-OEM-owned.
SYSTEMD_SERVICE:${PN} = "aos-camera-access-bootstrap.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"
do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-camera-access-launcher.c -o ${B}/aos-camera-access-launcher
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-camera-access-loop.c -o ${B}/aos-camera-access-loop
}
do_install() {
    install -d ${D}${libexecdir} ${D}${systemd_system_unitdir} ${D}${libdir}/tmpfiles.d
    install -m 0755 ${B}/aos-camera-access-launcher ${WORKDIR}/aos-camera-access-health ${D}${libexecdir}
    install -m 0644 ${WORKDIR}/aos-camera-access.service ${WORKDIR}/aos-camera-access-selftest@.service ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-camera-access.conf ${D}${libdir}/tmpfiles.d
    install -m 0755 ${B}/aos-camera-access-loop ${D}${libexecdir}
    install -m 0755 ${WORKDIR}/aos-camera-access-store-layout ${WORKDIR}/aos-camera-access-store-prepare ${WORKDIR}/aos-camera-access-store-check ${D}${libexecdir}
    install -m 0644 ${WORKDIR}/aos-camera-access-bootstrap.service ${WORKDIR}/aos-camera-access-store-layout.service ${WORKDIR}/aos-camera-access-store-prepare.service ${WORKDIR}/aos-camera-access-store-attach.service ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-camera-access-store.mount '${D}${systemd_system_unitdir}/var-aos-workdirs-sm-runtimes-systemd\x2dslot\x2dcamera\x2daccess.mount'
    install -d ${D}${sysconfdir}/modules-load.d ${D}${libdir}/aos-camera-access ${D}${sysconfdir}/systemd/system/aos-sm.service.d
    install -m 0644 ${WORKDIR}/aos-camera-access-loop.conf ${D}${sysconfdir}/modules-load.d
    install -m 0644 ${WORKDIR}/camera-store.conf ${D}${libdir}/aos-camera-access/store.conf
    install -m 0644 ${WORKDIR}/30-aos-camera-access.conf ${D}${sysconfdir}/systemd/system/aos-sm.service.d
}
FILES:${PN} += "${libexecdir}/aos-camera-access-* ${libdir}/tmpfiles.d/aos-camera-access.conf ${systemd_system_unitdir}/aos-camera-access-selftest@.service"
FILES:${PN} += "${systemd_system_unitdir}/aos-camera-access-* ${systemd_system_unitdir}/var-aos-workdirs-sm-runtimes-systemd*camera*access.mount ${libdir}/aos-camera-access/store.conf ${sysconfdir}/modules-load.d/aos-camera-access-loop.conf ${sysconfdir}/systemd/system/aos-sm.service.d/30-aos-camera-access.conf"
