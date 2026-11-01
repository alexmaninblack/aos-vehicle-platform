# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
SUMMARY = "Vision-only Camera Access native OEM bootstrap"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"
SRC_URI = "file://aos-camera-access-launcher.c file://aos-camera-access-health file://aos-camera-access.service file://aos-camera-access-selftest@.service file://aos-camera-access.conf"
S = "${WORKDIR}"
inherit systemd useradd
USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system aos-camera-read"
USERADD_PARAM:${PN} = "--system --home /nonexistent --no-create-home --shell /bin/false --gid aos-camera-read aos-camera-access"
RDEPENDS:${PN} = "python3-modules coreutils"
SYSTEMD_SERVICE:${PN} = "aos-camera-access.service"
SYSTEMD_AUTO_ENABLE:${PN} = "disable"
do_compile() {
    ${CC} ${CFLAGS} ${CPPFLAGS} ${LDFLAGS} -Wall -Wextra -Werror ${WORKDIR}/aos-camera-access-launcher.c -o ${B}/aos-camera-access-launcher
}
do_install() {
    install -d ${D}${libexecdir} ${D}${systemd_system_unitdir} ${D}${libdir}/tmpfiles.d
    install -m 0755 ${B}/aos-camera-access-launcher ${WORKDIR}/aos-camera-access-health ${D}${libexecdir}
    install -m 0644 ${WORKDIR}/aos-camera-access.service ${WORKDIR}/aos-camera-access-selftest@.service ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-camera-access.conf ${D}${libdir}/tmpfiles.d
}
FILES:${PN} += "${libexecdir}/aos-camera-access-* ${libdir}/tmpfiles.d/aos-camera-access.conf ${systemd_system_unitdir}/aos-camera-access-selftest@.service"
