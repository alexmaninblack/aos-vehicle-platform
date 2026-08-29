# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

# The upstream recipe installs shared demo TLS private keys. AosEdge creates a
# unique server identity on each provisioned vehicle instead; the obsolete
# client credential is not used by any platform runtime path.
do_install:append() {
    rm -f \
        ${D}${sysconfdir}/kuksa-val/Server.key \
        ${D}${sysconfdir}/kuksa-val/Server.pem \
        ${D}${sysconfdir}/kuksa-val/Client.key \
        ${D}${sysconfdir}/kuksa-val/Client.pem
}
