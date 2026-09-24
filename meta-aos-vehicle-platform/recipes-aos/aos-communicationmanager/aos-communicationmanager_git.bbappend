# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Exact VSS permission paths exceed the native 32-character default. Apply
# uniformly to the application and embedded Core library; match SM and IAM.
# This changes storage capacity only, never scopes or authorization decisions.
CXXFLAGS:append = " -DAOS_CONFIG_TYPES_FUNCTION_LEN=256"

# Coordinated mainline baseline for CM, SM and IAM. Upstream already owns
# shared gRPC write serialization; keep only tested residual behavior.
SRCREV = "9d613a46df3c7f550062e2f19ae3406c57715694"
SRCREV_default = "9d613a46df3c7f550062e2f19ae3406c57715694"
SRC_URI += " \
    git://github.com/aosedge/aos_core_lib_cpp.git;protocol=https;nobranch=1;name=serviceupdatelib;destsuffix=service-update-deps/aos_core_lib_cpp \
    git://github.com/aosedge/aos_core_api.git;protocol=https;nobranch=1;name=serviceupdateapi;destsuffix=service-update-deps/aos_core_api \
    file://0002-mainline-cm-instance-lifecycle.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
    file://0007-reconcile-generated-components-on-start.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
    file://0003-refresh-idle-full-unit-status.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
    file://0004-configure-idle-full-unit-status.patch \
    file://0006-notify-outside-transport-lock.patch \
"

SRCREV_serviceupdatelib = "5560291ba6914e36a5b841ade4d8fc54134a9e91"
SRCREV_serviceupdateapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"
SRCREV_FORMAT = "default_serviceupdatelib_serviceupdateapi"
DEPENDS:append = " softhsm googletest"
EXTRA_OECMAKE:append = " -DAOS_CORE_DIR=${WORKDIR}/service-update-deps -DWITH_TEST=ON -DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST"

# Factory .33 enables the proven idle recovery on the existing CM worker.
# The native code default remains disabled; no reconnect or new daemon.
do_update_config[postfuncs] += "aos_demo_idle_full_status"
python aos_demo_idle_full_status() {
    import json
    from pathlib import Path
    path = Path(d.getVar("D")) / d.getVar("sysconfdir").lstrip("/") / "aos/cm.cfg"
    config = json.loads(path.read_text())
    config["idleFullStatusInterval"] = "60s"
    path.write_text(json.dumps(config, indent=4) + "\n")
}

do_install:append() {
    # Match SM packaging: WITH_TEST installs CMake-only test fixtures into an
    # erroneous nested /usr/usr prefix. They are not CM runtime dependencies.
    if [ -d "${D}${prefix}/usr" ]; then
        find "${D}${prefix}/usr" -depth -delete
    fi
}
