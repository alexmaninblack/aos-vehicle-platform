# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

# QEMU exposes the macOS resolver bridge at the fixed host-visible endpoint.
# Keep the guest-facing resolver local so Aos services never depend on QEMU's
# synthesized DNS server.
do_install:append:qemuarm64() {
    if grep -q '^server=' ${D}/var/aos/dns/dnsmasq.conf; then
        bbfatal "unexpected upstream server in base dnsmasq configuration"
    fi
    printf 'server=%s#18053\n' "${AOS_NODE_GW_IP}" >> \
        ${D}/var/aos/dns/dnsmasq.conf
}
