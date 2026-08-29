# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

SUMMARY = "Removable Aos IAM to KUKSA Service JWT compatibility helper"
DESCRIPTION = "Current-release fixed-resource KUKSA authorization helper and protected verifier preparation executable."
HOMEPAGE = "https://github.com/maninblack/aos-vehicle-platform"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

FILESEXTRAPATHS:prepend := "${THISDIR}/../../../authorization/aos-kuksa-compat:${THISDIR}/files:"

SRC_URI = " \
    git://github.com/AosEdge/aos_core_api.git;protocol=https;nobranch=1;name=aoscoreapi;destsuffix=aos_core_api \
    file://CMakeLists.txt;subdir=source \
    file://include;subdir=source \
    file://src;subdir=source \
    file://tests;subdir=source \
    file://aos-kuksa-auth-compat.service \
    file://aos-kuksa-verifier-prepare.service \
    file://aos-kuksa-auth-compat.conf \
"
SRCREV_aoscoreapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"
SRCREV_FORMAT = "aoscoreapi"

S = "${WORKDIR}/source"

inherit cmake systemd useradd

DEPENDS = "abseil-cpp grpc protobuf openssl grpc-native protobuf-native"
RDEPENDS:${PN} = "openssl pkcs11-provider softhsm"

EXTRA_OECMAKE = " \
    -DAOS_CORE_API_DIR=${WORKDIR}/aos_core_api \
    -DProtobuf_PROTOC_EXECUTABLE=${STAGING_BINDIR_NATIVE}/protoc \
    -DGRPC_CPP_PLUGIN_EXECUTABLE=${STAGING_BINDIR_NATIVE}/grpc_cpp_plugin \
    -DBUILD_TESTING=ON \
"

SYSTEMD_PACKAGES = "${PN}"
SYSTEMD_SERVICE:${PN} = "aos-kuksa-verifier-prepare.service aos-kuksa-auth-compat.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "--system aos-kac; --system aos-kuksa-clients"
USERADD_PARAM:${PN} = "--system --home /nonexistent --no-create-home --shell /sbin/nologin --gid aos-kac --groups aos-kuksa-clients aos-kac"

do_install:append() {
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/aos-kuksa-auth-compat.service \
        ${D}${systemd_system_unitdir}/aos-kuksa-auth-compat.service
    install -m 0644 ${WORKDIR}/aos-kuksa-verifier-prepare.service \
        ${D}${systemd_system_unitdir}/aos-kuksa-verifier-prepare.service

    install -d ${D}${libdir}/tmpfiles.d
    install -m 0644 ${WORKDIR}/aos-kuksa-auth-compat.conf \
        ${D}${libdir}/tmpfiles.d/aos-kuksa-auth-compat.conf
}

FILES:${PN} = " \
    ${libexecdir}/aos-kuksa-auth-compat \
    ${libexecdir}/aos-kuksa-verifier-prepare \
    ${systemd_system_unitdir}/aos-kuksa-auth-compat.service \
    ${systemd_system_unitdir}/aos-kuksa-verifier-prepare.service \
    ${libdir}/tmpfiles.d/aos-kuksa-auth-compat.conf \
"
