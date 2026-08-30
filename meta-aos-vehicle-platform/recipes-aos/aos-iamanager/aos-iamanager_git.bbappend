# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://enable-permissions-handler.py file://aos-kuksa-iam-configure.py"

inherit python3native

# Aos IAM uses three distinct SoftHSM session keys in the accepted image:
# aoscloud, aoscore, and aos-kuksa, all with RW|SERIAL flags.  The upstream
# session cache allocates a replacement before it considers LRU eviction, so
# its allocator must retain the upstream invariant allocator == cache + 1.
# Keep this recipe-local; it is not a platform-wide resource limit.
CXXFLAGS:append = " -DAOS_CONFIG_PKCS11_SESSION_POOL_MAX_SIZE=3 -DAOS_CONFIG_PKCS11_SESSIONS_PER_LIB=4"

do_install:append() {
    ${PYTHON} ${WORKDIR}/enable-permissions-handler.py \
        --config ${D}${sysconfdir}/aos/iam.cfg
    ${PYTHON} ${WORKDIR}/aos-kuksa-iam-configure.py \
        ${D}${sysconfdir}/aos/iam.cfg
}
