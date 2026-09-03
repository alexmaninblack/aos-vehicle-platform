# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# v1.0 stored TLS peer public keys in whichever SoftHSM slot happened to have
# the lowest random slot ID.  That made verification depend on token creation
# order and could prompt for the unrelated token PIN.  v1.2.0 ties ephemeral
# objects to their owning non-login session and includes the upstream
# no-login storage fix.  The later upstream URI fix is required for embedded
# PKCS#11 key URIs used by AosCore.
PV = "1.2.0+git"
SRCREV = "c7a5c8b62a0ff012b16574f01651254ef7e664ee"

SRC_URI += "file://0001-safely-extract-and-null-terminate-uri-string.patch"
