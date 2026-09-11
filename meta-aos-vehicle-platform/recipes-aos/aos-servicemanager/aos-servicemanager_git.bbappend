# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Build-only dependency required by the upstream ARM64 test targets. It is not
# a runtime dependency and is not installed into aos-image-vm.
DEPENDS:append = " softhsm"

SRC_URI += " \
    file://0001-add-production-systemd-slot-component-runtime.patch \
    file://0002-idempotent-service-container-teardown.patch \
    git://github.com/aosedge/aos_core_lib_cpp.git;protocol=https;nobranch=1;name=serviceupdatelib;destsuffix=service-update-deps/aos_core_lib_cpp \
    git://github.com/aosedge/aos_core_api.git;protocol=https;nobranch=1;name=serviceupdateapi;destsuffix=service-update-deps/aos_core_api \
    file://0003-preserve-failed-service-replacement.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
    file://systemd-slot-component \
"

# Private, recipe-owned dependencies: do not patch the shared warm source cache.
SRCREV_serviceupdatelib = "60cb83535f773762c61ac5f544b31b7b88c502e3"
SRCREV_serviceupdateapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"
SRCREV_FORMAT = "default_serviceupdatelib_serviceupdateapi"

EXTRA_OECMAKE:append = " \
    -DAOS_CORE_DIR=${WORKDIR}/service-update-deps \
    -DAOS_SYSTEMD_SLOT_COMPONENT_DIR=${WORKDIR}/systemd-slot-component \
    -DWITH_TEST=ON \
    -DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST \
"

do_configure:prepend() {
    install -m 0644 \
        ${WORKDIR}/systemd-slot-component/providerarchive.hpp \
        ${S}/src/sm/imagemanager/providerarchive.hpp
}

do_install:append() {
    # WITH_TEST installs only CMake test-support data below an erroneous
    # ${prefix}/usr path. The qualifier itself remains in the build tree and
    # production packages must not contain this test-only staging directory.
    if [ -d "${D}${prefix}/usr" ]; then
        find "${D}${prefix}/usr" -depth -delete
    fi
}
