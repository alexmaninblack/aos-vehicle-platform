# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Build-time Vision selection. Never edit a booted VM or Main defaults."""
from copy import deepcopy

from .core import require


def select(sm, resources, native, services=None):
    result = deepcopy(sm)
    entries = [r for r in result["runtimes"] if r["plugin"] == "systemd-slot-component"]
    require(len(entries) == 1, "VISION_OEM_TARGET_AMBIGUOUS")
    target = entries[0]
    old = target["type"]
    require(old in ("vehicle-data-provider", "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider",
                    "aos-vision-vm-1.0.0-main-qemuarm64-vehicle-data-provider"), "VISION_BASE_TARGET_UNKNOWN")
    require(target["config"]["unit"] == "aos-vehicle-data-provider.service", "VISION_BASE_UNIT_UNKNOWN")
    target["type"] = old.removesuffix("vehicle-data-provider")+"camera-access"
    target["config"].update(componentProfile=native["componentProfile"], workingDir=native["workingDirectory"],
                            unit=native["unit"], healthAdapter=native["healthAdapter"])
    # This fixed local-demo flag would otherwise project VDP-only source files.
    target["config"].pop("demoLocalSourceInputs", None)
    selected = [deepcopy(r) for r in resources if r["name"] not in
                ("kuksa", "kuksa-auth-client", "brake-runtime-inputs", "tire-runtime-inputs")]
    require(not selected, "VISION_UNREVIEWED_BASE_RESOURCE")
    resource = dict(name=native["resource"], sharedCount=native["sharedCount"],
                    groups=[native["readerGroup"]], mounts=[dict(source=native["resourceSource"],
                    destination=native["resourceDestination"], type="bind", options=native["mountOptions"])])
    selected=[resource]
    if services is not None:
        roles=['perception-publish','perception-read','context-read','assessment-publish']
        require(services['schemaVersion']==1 and services['roles']==roles
            and services['mountOptions']==['bind','ro','nosuid','nodev','noexec'],'VISION_SERVICE_PROFILE_INVALID')
        require('imagePath' not in result.get('imageManager',{}),'VISION_IMAGE_PATH_OVERRIDE_CONFLICT')
        result.setdefault('imageManager',{})['imagePath']=services['imagePaths']['service']
        require(set(services['groupNames'])==set(roles) and all(len(n)<=24 for n in services['groupNames'].values()),'VISION_GROUP_NAME_INVALID')
        selected += [dict(name='vision-'+role,sharedCount=1,groups=[services['groupNames'][role]],mounts=[dict(
            source='/run/aos-vision-exchange/'+role,destination='/run/aosedge/vision/'+role,type='bind',options=list(services['mountOptions']))]) for role in roles]
    return result, selected


def select_communication(cm, services):
    result=deepcopy(cm)
    require(result.get('imageManager',{}).get('installPath')=='/var/aos/workdirs/cm/imagemanager/install','VISION_CM_IMAGE_PATH_OVERRIDE_CONFLICT')
    require(services['imagePaths']==dict(communication='/var/aos/downloads/vision-services/cm-images',service='/var/aos/downloads/vision-services/sm-images'),
        'VISION_IMAGE_PATH_PROFILE_INVALID')
    result['imageManager']['installPath']=services['imagePaths']['communication']
    return result
