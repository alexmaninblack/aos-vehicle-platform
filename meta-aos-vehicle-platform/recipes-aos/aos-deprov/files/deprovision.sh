#!/bin/sh
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

COMMAND="$1"

run_kuksa_cleanup() {
    if ! systemctl start aos-kuksa-runtime-cleanup.service; then
        echo "KUKSA runtime cleanup rejected deprovision" | systemd-cat
        return 1
    fi
}

clear_disks() {
    run_kuksa_cleanup || return 1

    echo "Remove IAM DB and PKCS11 storage"
    rm /var/aos/iam -rf
    /opt/aos/clearhsm.sh

    echo "Delete Aos disks"
    /opt/aos/setupdisk.sh delete

    sync
}

remove_firewall_rules() {
    nft delete table inet aos-provfw 2>/dev/null
}

deprovision_async() {
    {
        sleep 1

        # use systemctl stop all aos.target services instead of systemctl stop aos.target, because this approach doesn't wait
        # all services really stopped.
        systemctl stop -- $(systemctl show -p Wants aos.target | cut -d= -f2)

        run_kuksa_cleanup || exit 1

        remove_firewall_rules

        echo "Restore unprovisioned flag" | systemd-cat
        rm /var/aos/.provisionstate -f

        systemctl start aos.target
    } > /dev/null 2>&1 &
}

case "$COMMAND" in
async)
    deprovision_async
    ;;

*)
    clear_disks
    ;;
esac
