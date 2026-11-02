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
AOS_VISION_CAMERA_INGRESS ??= "0"
AOS_VISION_NATIVE_SERVICES ??= "0"
FILESEXTRAPATHS:prepend := "${THISDIR}/../../../tests/fixtures/vision-native-exchange:"
SRC_URI:append = " ${@'file://aos-vision-exchange-launcher.c file://aos-vision-exchange.service file://aos-vision-exchange.conf file://36-vision-image-storage.conf' if d.getVar('AOS_VISION_NATIVE_SERVICES') == '1' else ''}"
SRC_URI:append = " ${@'file://aos-camera-ingress-launcher.c file://aos-camera-ingress.service' if d.getVar('AOS_VISION_CAMERA_INGRESS') == '1' else ''}"
inherit systemd useradd
USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "${@'--system --gid 990 aos-camera-read; --system --gid 989 aos-vision-exchange; --system --gid 988 aos-vision-perc-pub; --system --gid 987 aos-vision-perc-read; --system --gid 986 aos-vision-context-read; --system --gid 985 aos-vision-assess-pub' if d.getVar('AOS_VISION_NATIVE_SERVICES') == '1' else '--system aos-camera-read'}"
USERADD_PARAM:${PN} = "--system ${@'--uid 992' if d.getVar('AOS_VISION_NATIVE_SERVICES') == '1' else ''} --home /nonexistent --no-create-home --shell /bin/false --gid aos-camera-read aos-camera-access"
USERADD_PARAM:${PN}:append = "${@'; --system --uid 989 --home /nonexistent --no-create-home --shell /bin/false --gid aos-vision-exchange aos-vision-exchange' if d.getVar('AOS_VISION_NATIVE_SERVICES') == '1' else ''}"
RDEPENDS:${PN} = "python3-modules coreutils e2fsprogs-e2fsck e2fsprogs-mke2fs kernel-module-loop util-linux-blkid util-linux-losetup util-linux-findmnt"
# Only storage bootstrap is enabled. Camera's process is native-OEM-owned.
SYSTEMD_SERVICE:${PN} = "aos-camera-access-bootstrap.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"
do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-camera-access-launcher.c -o ${B}/aos-camera-access-launcher
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-camera-access-loop.c -o ${B}/aos-camera-access-loop
    if [ "${AOS_VISION_CAMERA_INGRESS}" = "1" ]; then
        ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-camera-ingress-launcher.c -o ${B}/aos-camera-ingress-launcher
    fi
    if [ "${AOS_VISION_NATIVE_SERVICES}" = "1" ]; then
        ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-vision-exchange-launcher.c -o ${B}/aos-vision-exchange-launcher
    fi
}
do_install() {
    install -d ${D}${libexecdir} ${D}${systemd_system_unitdir} ${D}${libdir}/tmpfiles.d
    if [ "${AOS_VISION_CAMERA_INGRESS}" = "1" ]; then
        install -m 0755 ${B}/aos-camera-ingress-launcher ${D}${libexecdir}
        install -m 0644 ${WORKDIR}/aos-camera-ingress.service ${D}${systemd_system_unitdir}
    fi
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
    if [ "${AOS_VISION_NATIVE_SERVICES}" = "1" ]; then
        install -m 0755 ${B}/aos-vision-exchange-launcher ${D}${libexecdir}
        install -m 0644 ${WORKDIR}/aos-vision-exchange.service ${D}${systemd_system_unitdir}
        install -m 0644 ${WORKDIR}/aos-vision-exchange.conf ${D}${libdir}/tmpfiles.d
        install -d ${D}${sysconfdir}/systemd/system/aos-cm.service.d
        for owner in cm sm; do
            install -m 0644 ${WORKDIR}/36-vision-image-storage.conf ${D}${sysconfdir}/systemd/system/aos-${owner}.service.d
        done
    fi
}
FILES:${PN} += "${libexecdir}/aos-camera-access-* ${libdir}/tmpfiles.d/aos-camera-access.conf ${systemd_system_unitdir}/aos-camera-access.service ${systemd_system_unitdir}/aos-camera-access-selftest@.service"
FILES:${PN} += "${systemd_system_unitdir}/aos-camera-access-* ${systemd_system_unitdir}/var-aos-workdirs-sm-runtimes-systemd*camera*access.mount ${libdir}/aos-camera-access/store.conf ${sysconfdir}/modules-load.d/aos-camera-access-loop.conf ${sysconfdir}/systemd/system/aos-sm.service.d/30-aos-camera-access.conf"
FILES:${PN} += "${libexecdir}/aos-camera-ingress-launcher ${systemd_system_unitdir}/aos-camera-ingress.service"
FILES:${PN}:append = " ${@'${libexecdir}/aos-vision-exchange-launcher ${systemd_system_unitdir}/aos-vision-exchange.service ${libdir}/tmpfiles.d/aos-vision-exchange.conf ${sysconfdir}/systemd/system/aos-cm.service.d/36-vision-image-storage.conf ${sysconfdir}/systemd/system/aos-sm.service.d/36-vision-image-storage.conf' if d.getVar('AOS_VISION_NATIVE_SERVICES') == '1' else ''}"
