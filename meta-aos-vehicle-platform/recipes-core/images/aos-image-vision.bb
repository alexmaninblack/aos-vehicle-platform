# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

# Explicit specialist target. aos-image-vm and its bbappend remain Main-owned.
require recipes-core/images/aos-image-vm.bb
SUMMARY = "Isolated Vision ARM64 controller bootstrap"
IMAGE_BASENAME = "aos-image-vision"
IMAGE_INSTALL:append = " aos-camera-access-platform"
FILESEXTRAPATHS:prepend := "${THISDIR}/../../../contracts/camera-access:${THISDIR}/../../../camera-access/src/aos_camera_access:"
SRC_URI += "file://native-profile.json file://native-services-profile.json file://vision_image.py file://core.py"
AOS_VISION_NATIVE_SERVICES ??= "0"
ROOTFS_POSTPROCESS_COMMAND:append = " aos_vision_native_profile; "

# FOTA needs the fully preprocessed tree, not an old manufacturing build's
# shared link. The inherited do_create_shared_links also depends on image_wic;
# this explicit task exports only a link and never assembles a filesystem/disk.
AOS_VISION_FOTA_ROOTFS_DIR = "${TMPDIR}/work-shared/aos-vision-fota-${MACHINE}"
do_prepare_vision_rootfs_fota[cleandirs] = "${AOS_VISION_FOTA_ROOTFS_DIR}"
do_prepare_vision_rootfs_fota() {
    test "${AOS_VISION_CAMERA_INGRESS}" = "1"
    test -d "${IMAGE_ROOTFS}"
    ln -r -s "${IMAGE_ROOTFS}" "${AOS_VISION_FOTA_ROOTFS_DIR}/rootfs"
}
addtask prepare_vision_rootfs_fota after do_image

# Image recipes disable normal unpack tasks. Resolve the build-time helpers
# from the layer and include their actual bytes in do_rootfs signatures.
python __anonymous() {
    for name in ("native-profile.json", "native-services-profile.json", "vision_image.py", "core.py"):
        path = bb.utils.which(d.getVar("FILESPATH"), name)
        if not path:
            bb.fatal("Missing Vision build input: " + name)
        d.appendVarFlag("do_rootfs", "file-checksums", " " + path + ":True")
}

python aos_vision_native_profile() {
    import json
    import importlib.util
    import sys
    import types
    from pathlib import Path
    root = Path(d.getVar("IMAGE_ROOTFS"))
    work = Path(bb.utils.which(d.getVar("FILESPATH"), "vision_image.py")).parent
    # Load the exact source-owned build-time selector without importing host code.
    package = types.ModuleType("aos_camera_access")
    package.__path__ = [str(work)]
    prior = sys.modules.get("aos_camera_access")
    sys.modules["aos_camera_access"] = package
    try:
        spec = importlib.util.spec_from_file_location("aos_camera_access.vision_image", work / "vision_image.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = root / "etc/aos/sm.cfg"
        resource = root / "etc/aos/resources.cfg"
        native = json.loads(Path(bb.utils.which(d.getVar("FILESPATH"), "native-profile.json")).read_text())
        services = json.loads(Path(bb.utils.which(d.getVar("FILESPATH"), "native-services-profile.json")).read_text()) if d.getVar("AOS_VISION_NATIVE_SERVICES") == "1" else None
        sm, resources = module.select(json.loads(config.read_text()), json.loads(resource.read_text()), native, services)
        config.write_text(json.dumps(sm, indent=4) + "\n")
        resource.write_text(json.dumps(resources, indent=4) + "\n")
        if services is not None:
            cm = root / "etc/aos/cm.cfg"
            cm.write_text(json.dumps(module.select_communication(json.loads(cm.read_text()), services), indent=4) + "\n")
    finally:
        for key in ("aos_camera_access.core", "aos_camera_access.vision_image", "aos_camera_access"):
            sys.modules.pop(key, None)
        if prior is not None:
            sys.modules["aos_camera_access"] = prior
    # SM's Main-only helper must not require a VDP commit in the Vision VM.
    dropin = root / "etc/systemd/system/aos-sm.service.d/40-aos-demo-service-inputs.conf"
    if dropin.exists():
        if dropin.is_symlink() or "aos-demo-service-inputs.py" not in dropin.read_text():
            bb.fatal("Unexpected SM input projection")
        dropin.unlink()
    forbidden = (root / "usr/libexec/aos-vehicle-data-provider-launcher", root / "usr/lib/systemd/system/aos-vehicle-data-provider.service")
    if any(p.exists() for p in forbidden):
        bb.fatal("Vision must not include VDP bootstrap or target")
}
