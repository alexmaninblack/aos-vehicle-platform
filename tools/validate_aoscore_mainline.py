#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate coordinated pins and reconstruct each recipe's native patch series.

No network, cached-checkout edits, VM access or image construction. Optional
proof references compare the reconstructed changed files with tested sources.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ROOT / 'meta-aos-vehicle-platform/recipes-aos'
APP = '9d613a46df3c7f550062e2f19ae3406c57715694'
LIB = '5560291ba6914e36a5b841ade4d8fc54134a9e91'
API = 'af3552a0a5eb0237eff7f5f183780ca46c339cd3'
MANAGERS = ('aos-communicationmanager', 'aos-servicemanager', 'aos-iamanager')


def validate_pins() -> None:
    inventory = json.loads((ROOT / 'DEPENDENCIES.json').read_text())
    # The inventory layout has descriptive metadata beside its dependencies.
    records = inventory['build']
    for name, revision in (('AosCore C++', APP), ('AosCore C++ library', LIB), ('AosCore API', API)):
        assert [r['revision'] for r in records if r['name'] == name] == [revision], name
    for name in MANAGERS:
        recipe = (RECIPES / name / (name + '_git.bbappend')).read_text()
        for variable, pin in (('SRCREV', APP), ('SRCREV_default', APP), ('SRCREV_serviceupdatelib', LIB), ('SRCREV_serviceupdateapi', API)):
            assert re.findall(r'^' + variable + r' = "([^"]+)"$', recipe, re.M) == [pin], (name, variable)
        assert '-DAOS_CORE_DIR=${WORKDIR}/service-update-deps' in recipe, name
        assert 'name=serviceupdatelib;destsuffix=service-update-deps/aos_core_lib_cpp' in recipe, name
        assert 'name=serviceupdateapi;destsuffix=service-update-deps/aos_core_api' in recipe, name
        assert '0001-serialize-sm-stream-writes.patch' not in recipe


def export(source: Path, revision: str, target: Path) -> None:
    target.mkdir(parents=True)
    archive = subprocess.Popen(['git', 'archive', revision], cwd=source, stdout=subprocess.PIPE)
    try:
        subprocess.run(['tar', '-xf', '-', '-C', str(target)], stdin=archive.stdout, check=True)
    finally:
        archive.stdout.close()
    assert archive.wait() == 0, 'source archive failed'


def reconstruct(app: Path, lib: Path, output: Path, reference: Path | None = None) -> None:
    validate_pins()
    assert not output.exists(), 'output must be a new directory; existing proof is never overwritten'
    output.mkdir(parents=True)
    for name in MANAGERS:
        recipe_dir = RECIPES / name
        recipe = (recipe_dir / (name + '_git.bbappend')).read_text()
        targets = {'app': output / name / 'app', 'lib': output / name / 'lib'}
        export(app, APP, targets['app'])
        export(lib, LIB, targets['lib'])
        patches = re.findall(r'file://([^\s"\\]+\.patch)(;patchdir=[^\s"\\]+)?', recipe)
        assert patches, name
        changed = {'app': set(), 'lib': set()}
        for filename, patchdir in patches:
            kind = 'lib' if patchdir else 'app'
            assert patchdir in ('', ';patchdir=../service-update-deps/aos_core_lib_cpp'), patchdir
            patch = recipe_dir / 'files' / filename
            body = patch.read_text()
            assert f'Base: aos_core_{"lib_cpp" if kind == "lib" else "cpp"} {LIB if kind == "lib" else APP}' in body, filename
            subprocess.run(['git', 'apply', '--check', str(patch)], cwd=targets[kind], check=True)
            subprocess.run(['git', 'apply', str(patch)], cwd=targets[kind], check=True)
            changed[kind].update(re.findall(r'^diff --git a/(\S+) b/\S+$', body, re.M))
        # Several ordered patches may legitimately edit one file. Compare
        # the final recipe bytes with the tested source, not intermediate states.
        if reference:
            for kind, paths in changed.items():
                for path in paths:
                    assert (targets[kind] / path).read_bytes() == (reference / kind / path).read_bytes(), (name, path)
        if name == 'aos-servicemanager':
            runtime = recipe_dir / 'files/systemd-slot-component'
            shutil.copytree(runtime, output / name / 'runtime')
            shutil.copyfile(runtime / 'providerarchive.hpp', targets['app'] / 'src/sm/imagemanager/providerarchive.hpp')
            if reference:
                for path in runtime.rglob('*'):
                    if path.is_file():
                        assert path.read_bytes() == (reference / 'runtime' / path.relative_to(runtime)).read_bytes(), path
        print(f'{name}: {len(patches)} patches apply to the pinned baseline' + ('; native-proof bytes match' if reference else ''))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-source', type=Path)
    parser.add_argument('--lib-source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--proof-reference', type=Path)
    args = parser.parse_args()
    validate_pins()
    if args.app_source or args.lib_source or args.output or args.proof_reference:
        if not (args.app_source and args.lib_source):
            parser.error('both source repositories are required for reconstruction')
        if args.output:
            reconstruct(args.app_source, args.lib_source, args.output, args.proof_reference)
        else:
            with tempfile.TemporaryDirectory(prefix='aos-mainline-series-') as directory:
                reconstruct(args.app_source, args.lib_source, Path(directory) / 'source', args.proof_reference)
    print('Coordinated AosCore mainline source gate passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
