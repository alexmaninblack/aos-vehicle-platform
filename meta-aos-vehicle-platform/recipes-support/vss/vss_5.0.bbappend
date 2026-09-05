# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://vdp_vss_schema.py"

# Compose the public data model at build time, before packaging/QA. No guest
# startup transformation, runtime bind mount, credential or policy change.
do_install[postfuncs] += "vdp_schema_install"

python vdp_schema_install() {
    import importlib.util
    from pathlib import Path

    source = Path(d.getVar("WORKDIR")) / "vdp_vss_schema.py"
    spec = importlib.util.spec_from_file_location("vdp_vss_schema", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.transform(Path(d.getVar("D")) / d.getVar("datadir").lstrip("/") / "vss/vss.json")
}
