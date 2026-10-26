# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

IMAGE_INSTALL:append = " aos-vehicle-data-provider-platform aos-kuksa-auth-compat aos-kuksa-factory-integration"

# The local-demo profile is packaged, not patched into a provisioned overlay.
ROOTFS_POSTPROCESS_COMMAND:append = " aos_demo_runtime_inputs; aos_kuksa_reserved_ports; "

python aos_demo_runtime_inputs() {
    import json
    from pathlib import Path
    root = Path(d.getVar("IMAGE_ROOTFS"))
    config_path = root / "etc/aos/sm.cfg"
    config = json.loads(config_path.read_text())
    runtimes = [item["config"] for item in config["runtimes"]
                if item["plugin"] == "systemd-slot-component"]
    if len(runtimes) != 1:
        bb.fatal("Expected one OEM component runtime")
    runtimes[0]["demoLocalSourceInputs"] = True
    runtimes[0]["safeStopFreshnessProfile"] = "standard"
    config_path.write_text(json.dumps(config, indent=4) + "\n")
    marker = root / "usr/share/aos-vehicle-platform/demo-runtime-inputs-v1"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1\n")
    inputs = "/var/aos/workdirs/sm/runtimes/systemd-slot-component/demo-inputs"
    dropin = root / "etc/systemd/system/aos-vehicle-data-provider.service.d/50-democtl-source.conf"
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text("[Service]\nLoadCredential=viss-server-ca.pem:" + inputs + "/viss-update-ca\n"
                      "LoadCredential=viss-selected-source.json:" + inputs + "/selected.json\n")
}

# KUKSA explicitly binds 55555; NFS must not receive it from bind(port=0).
# Compose the effective image policy at build time, not in a guest daemon.
python aos_kuksa_reserved_ports() {
    import os
    import re
    from pathlib import Path
    root = Path(d.getVar("IMAGE_ROOTFS"))
    name = "99-aos-kuksa-ports.conf"
    selected = {}
    directories = ("etc/sysctl.d", "run/sysctl.d", "usr/local/lib/sysctl.d", "usr/lib/sysctl.d")
    for directory in directories:
        parent = root / directory
        if any(p.is_symlink() for p in (parent, *parent.parents) if p.is_relative_to(root)):
            bb.fatal("Linked sysctl configuration directory")
        for path in sorted(parent.glob("*.conf")):
            selected.setdefault(path.name, path)
    reserved = set()
    target = root / "usr/lib/sysctl.d" / name
    if name in selected and selected[name] != target or target.is_symlink():
        bb.fatal("KUKSA port policy is masked or linked")
    for filename, path in sorted(selected.items()):
        if path == target:
            if not path.read_text().startswith("# Factory-owned KUKSA port;"):
                bb.fatal("Unexpected existing KUKSA port policy")
            continue
        for _ in range(8):
            if not path.is_symlink():
                break
            link = os.readlink(path)
            if link == "/dev/null":
                path = None
                break
            path = Path(os.path.normpath(str(root / link.lstrip("/") if link.startswith("/") else path.parent / link)))
            if not path.is_relative_to(root) or any(p.is_symlink() for p in path.parents if p != root and p.is_relative_to(root)):
                bb.fatal("Unsafe sysctl configuration link")
        else:
            bb.fatal("Cyclic sysctl configuration link")
        if path is None:
            continue
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            bb.fatal("Invalid sysctl configuration file")
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith(("#", ";")):
                continue
            key, separator, value = line.partition("=")
            if key.strip().lstrip("-").replace("/", ".") != "net.ipv4.ip_local_reserved_ports":
                continue
            if not separator or filename > name:
                bb.fatal("Ambiguous or overriding KUKSA port reservation")
            ports = set()
            for token in value.strip().split(",") if value.strip() else ():
                if not re.fullmatch(r"[0-9]+(?:-[0-9]+)?", token.strip()):
                    bb.fatal("Invalid existing port reservation")
                endpoints = [int(part) for part in token.strip().split("-")]
                first, last = endpoints[0], endpoints[-1]
                if not 0 <= first <= last <= 65535:
                    bb.fatal("Invalid existing port reservation range")
                ports.update(range(first, last + 1))
            reserved = ports
    reserved.add(55555)
    ranges = []
    first = last = None
    for port in sorted(reserved):
        if last is not None and port != last + 1:
            ranges.append(str(first) if first == last else str(first) + "-" + str(last))
            first = None
        if first is None:
            first = port
        last = port
    ranges.append(str(first) if first == last else str(first) + "-" + str(last))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# Factory-owned KUKSA port; preserve effective image reservations.\n"
                      "net.ipv4.ip_local_reserved_ports = " + ",".join(ranges) + "\n")
    target.chmod(0o644)
    for unit in ("nfs-mountd.service", "kuksa-databroker.service"):
        dropin = root / "usr/lib/systemd/system" / (unit + ".d/10-aos-kuksa-ports.conf")
        dropin.parent.mkdir(parents=True, exist_ok=True)
        dropin.write_text("[Unit]\nRequires=systemd-sysctl.service\nAfter=systemd-sysctl.service\n")
        dropin.chmod(0o644)
}
