# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Build-only dependency required by the upstream ARM64 test targets. It is not
# a runtime dependency and is not installed into aos-image-vm.
DEPENDS:append = " softhsm"

SRC_URI += " \
    file://0001-add-production-systemd-slot-component-runtime.patch \
    file://systemd-slot-component \
"

EXTRA_OECMAKE:append = " \
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
