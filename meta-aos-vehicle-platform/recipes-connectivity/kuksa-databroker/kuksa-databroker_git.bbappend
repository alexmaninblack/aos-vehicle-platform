# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://0002-authorization-accept-decimal-digits-in-scope-path.patch"
SRC_URI += "file://0003-val-v1-preserve-source-timestamps.patch"

do_compile:append() {
    export CARGO_TARGET_AARCH64_AOS_LINUX_GNU_RUNNER="${RECIPE_SYSROOT}${base_libdir}/ld-linux-aarch64.so.1 --library-path ${RECIPE_SYSROOT}${base_libdir}:${RECIPE_SYSROOT}${libdir}"
    bbnote "Running scoped KUKSA authorization::jwt::scope tests"
    "${CARGO}" test ${CARGO_BUILD_FLAGS} -p databroker --lib authorization::jwt::scope -- --nocapture
    bbnote "Running KUKSA VAL v1 source timestamp tests"
    "${CARGO}" test ${CARGO_BUILD_FLAGS} -p databroker --lib source_timestamp_tests -- --nocapture
}
