# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Keep complete VSS permission keys across CM, SM and IAM registration/readback.
# Capacity only: permission scopes, values and authorization remain unchanged.
CXXFLAGS:append = " -DAOS_CONFIG_TYPES_FUNCTION_LEN=256"

# Match CM and SM, including recipe-private library/API sources. Never patch
# or silently reuse an older shared warm-cache checkout.
SRCREV = "9d613a46df3c7f550062e2f19ae3406c57715694"
SRCREV_default = "9d613a46df3c7f550062e2f19ae3406c57715694"
SRCREV_serviceupdatelib = "5560291ba6914e36a5b841ade4d8fc54134a9e91"
SRCREV_serviceupdateapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"
SRCREV_FORMAT = "default_serviceupdatelib_serviceupdateapi"
SRC_URI += " \
    git://github.com/aosedge/aos_core_lib_cpp.git;protocol=https;nobranch=1;name=serviceupdatelib;destsuffix=service-update-deps/aos_core_lib_cpp \
    git://github.com/aosedge/aos_core_api.git;protocol=https;nobranch=1;name=serviceupdateapi;destsuffix=service-update-deps/aos_core_api \
    file://0002-test-three-token-session-cache.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
"
DEPENDS:append = " softhsm googletest"
EXTRA_OECMAKE:append = " -DAOS_CORE_DIR=${WORKDIR}/service-update-deps -DWITH_TEST=ON -DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST"

SRC_URI += "file://enable-permissions-handler.py file://aos-kuksa-iam-configure.py"
SRC_URI += "file://0001-use-function-count-for-permission-response.patch"

inherit python3native

# Aos IAM uses three distinct SoftHSM session keys in the accepted image:
# aoscloud, aoscore, and aos-kuksa, all with RW|SERIAL flags. Retain all three
# keys in the cache. Mainline now injects the application's HeapAllocator;
# the old fixed per-library allocator override is obsolete. The native test
# covers cache clear/reopen while an older session remains referenced.
# Keep this recipe-local; no topology or authorization change.
CXXFLAGS:append = " -DAOS_CONFIG_PKCS11_SESSION_POOL_MAX_SIZE=3"

do_install:append() {
    ${PYTHON} ${WORKDIR}/enable-permissions-handler.py \
        --config ${D}${sysconfdir}/aos/iam.cfg
    ${PYTHON} ${WORKDIR}/aos-kuksa-iam-configure.py \
        ${D}${sysconfdir}/aos/iam.cfg
    # Match CM/SM: exclude the upstream nested-prefix test-only fixtures.
    if [ -d "${D}${prefix}/usr" ]; then
        find "${D}${prefix}/usr" -depth -delete
    fi
}
