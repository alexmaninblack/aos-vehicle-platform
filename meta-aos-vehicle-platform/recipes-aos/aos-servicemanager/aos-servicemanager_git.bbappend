# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Exact VSS permission paths exceed the native 32-character default. Apply
# uniformly to the application and embedded Core library; match CM and IAM.
# This changes storage capacity only, never scopes or authorization decisions.
CXXFLAGS:append = " -DAOS_CONFIG_TYPES_FUNCTION_LEN=256"

# Build-only dependency required by the upstream ARM64 test targets. It is not
# a runtime dependency and is not installed into aos-image-vm.
DEPENDS:append = " softhsm"

SRC_URI += " \
    file://0001-add-production-systemd-slot-component-runtime.patch \
    file://0002-idempotent-service-container-teardown.patch \
    git://github.com/aosedge/aos_core_lib_cpp.git;protocol=https;nobranch=1;name=serviceupdatelib;destsuffix=service-update-deps/aos_core_lib_cpp \
    git://github.com/aosedge/aos_core_api.git;protocol=https;nobranch=1;name=serviceupdateapi;destsuffix=service-update-deps/aos_core_api \
    file://0003-preserve-failed-service-replacement.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
    file://0004-retry-failed-service-preparation.patch;patchdir=../service-update-deps/aos_core_lib_cpp \
    file://systemd-slot-component \
    file://resources-demo-services.cfg \
    file://aos-demo-service-inputs.py \
    file://40-aos-demo-service-inputs.conf \
"

# Public input projection is the accepted Demo Control integration, not a
# launcher or token authority. All imports must be available on a clean image.
RDEPENDS:${PN}:append = " python3-modules openssl"

# Private, recipe-owned dependencies: do not patch the shared warm source cache.
SRCREV_serviceupdatelib = "60cb83535f773762c61ac5f544b31b7b88c502e3"
SRCREV_serviceupdateapi = "af3552a0a5eb0237eff7f5f183780ca46c339cd3"
SRCREV_FORMAT = "default_serviceupdatelib_serviceupdateapi"

EXTRA_OECMAKE:append = " \
    -DAOS_CORE_DIR=${WORKDIR}/service-update-deps \
    -DAOS_SYSTEMD_SLOT_COMPONENT_DIR=${WORKDIR}/systemd-slot-component \
    -DWITH_TEST=ON \
    -DCMAKE_GTEST_DISCOVER_TESTS_DISCOVERY_MODE=PRE_TEST \
"

do_configure:prepend() {
    install -m 0644 \
        ${WORKDIR}/systemd-slot-component/providerarchive.hpp \
        ${S}/src/sm/imagemanager/providerarchive.hpp
}

do_install:append() {
    install -d ${D}${libexecdir} ${D}${sysconfdir}/systemd/system/aos-sm.service.d
    install -m 0644 ${WORKDIR}/aos-demo-service-inputs.py ${D}${libexecdir}
    install -m 0644 ${WORKDIR}/40-aos-demo-service-inputs.conf \
        ${D}${sysconfdir}/systemd/system/aos-sm.service.d
    # WITH_TEST installs only CMake test-support data below an erroneous
    # ${prefix}/usr path. The qualifier itself remains in the build tree and
    # production packages must not contain this test-only staging directory.
    if [ -d "${D}${prefix}/usr" ]; then
        find "${D}${prefix}/usr" -depth -delete
    fi
}

# Native configuration processing follows install; merge after that task so
# the final packaged configuration, not an intermediate file, owns the mounts.
do_update_config[postfuncs] += "aos_demo_service_resources"
python aos_demo_service_resources() {
    import json
    from pathlib import Path
    path = Path(d.getVar("D")) / d.getVar("sysconfdir").lstrip("/") / "aos/resources.cfg"
    resources = json.loads(path.read_text())
    additions = json.loads((Path(d.getVar("WORKDIR")) / "resources-demo-services.cfg").read_text())
    names = [item["name"] for item in resources]
    if len(names) != len(set(names)) or set(names) & {item["name"] for item in additions}:
        bb.fatal("Duplicate native service input resource")
    path.write_text(json.dumps(resources + additions, indent=4) + "\n")
}

FILES:${PN}:append = " ${libexecdir}/aos-demo-service-inputs.py ${sysconfdir}/systemd/system/aos-sm.service.d/40-aos-demo-service-inputs.conf"
