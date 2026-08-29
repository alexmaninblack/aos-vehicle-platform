# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://0002-authorization-accept-decimal-digits-in-scope-path.patch"

do_compile:append() {
    export CARGO_TARGET_AARCH64_AOS_LINUX_RUNNER="${RECIPE_SYSROOT}/lib/ld-linux-aarch64.so.1 --library-path ${RECIPE_SYSROOT}/lib:${RECIPE_SYSROOT}/usr/lib"
    bbnote "Running scoped KUKSA authorization::jwt::scope tests"
    "${CARGO}" test ${CARGO_BUILD_FLAGS} -p databroker --lib authorization::jwt::scope -- --nocapture
}
