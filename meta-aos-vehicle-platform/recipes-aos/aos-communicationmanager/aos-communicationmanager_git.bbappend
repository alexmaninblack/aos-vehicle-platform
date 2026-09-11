# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Keep the pinned native CM and shared gRPC write-lock backport.
SRC_URI += " \
    file://0001-serialize-sm-stream-writes.patch \
    git://github.com/aosedge/aos_core_lib_cpp.git;protocol=https;nobranch=1;name=serviceupdatelib;destsuffix=service-update-deps/aos_core_lib_cpp \
    git://github.com/aosedge/aos_core_api.git;protocol=https;nobranch=1;name=serviceupdateapi;destsuffix=service-update-deps/aos_core_api \
    file://0002-reconcile-stale-instance-snapshot.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
"

SRCREV_serviceupdatelib = "60cb83535f773762c61ac5f544b31b7b88c502e3"
SRCREV_serviceupdateapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"
SRCREV_FORMAT = "default_serviceupdatelib_serviceupdateapi"
DEPENDS:append = " softhsm googletest"
EXTRA_OECMAKE:append = " -DAOS_CORE_DIR=${WORKDIR}/service-update-deps -DWITH_TEST=ON -DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST"
