# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

# The qemuarm64 VM resolves through its local dnsmasq instance.  The host-side
# loopback bridge is reached by dnsmasq, not by systemd-networkd directly.
do_install:append:qemuarm64() {
    cat >${D}${sysconfdir}/systemd/network/20-wired.network <<EOF
[Match]
Name=en*

[Network]
Address=${AOS_NODE_IP}
Gateway=${AOS_NODE_GW_IP}
DNS=${AOS_DNS_IP}
EOF
}
