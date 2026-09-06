# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

IMAGE_INSTALL:append = " aos-vehicle-data-provider-platform aos-kuksa-auth-compat aos-kuksa-factory-integration"

# The local-demo profile is packaged, not patched into a provisioned overlay.
ROOTFS_POSTPROCESS_COMMAND:append = " aos_demo_runtime_inputs; "

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
