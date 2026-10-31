#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0
"""Targeted ARM64 OEM-runtime regression in the SSD-backed Linux Builder.

Reuse immutable recipe compiler/link commands and dependency objects. Recompile
every translation unit of the changed module and its tests in owned scratch;
never edit/reconfigure the warm source/build tree or construct a Factory image.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--scratch", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    a = p.parse_args()
    assert os.uname().sysname == "Linux" and os.uname().machine == "aarch64"
    assert all(x.is_absolute() and not x.is_symlink() for x in (a.work, a.source, a.scratch, a.evidence))
    assert not a.evidence.exists(), "COMPILE_ATTEMPT_EXISTS_RECONCILE"
    assert shutil.disk_usage(a.scratch).free >= 2*1024**3, "COMPILE_CAPACITY"
    a.evidence.parent.mkdir(mode=0o700, exist_ok=True)
    assert not a.evidence.parent.is_symlink()
    a.evidence.mkdir(mode=0o700)
    original = a.work / "systemd-slot-component"
    build = a.work / "build"
    commands = json.loads((build / "compile_commands.json").read_bytes())
    commands = [r for r in commands if Path(r["file"]).is_relative_to(original)]
    assert len(commands) == 10, "EXPECTED_SIX_RUNTIME_FOUR_TEST_UNITS"
    result = dict(scenario="CAMERA_ACCESS_NATIVE_TARGET_COMPILE", outcome="FAIL",
                  imageBuilt=False, liveAosAuthorization="NOT_RUN", m4Activation="NOT_RUN")
    start = time.monotonic()
    env = dict(os.environ)
    env["PATH"] = shlex.split(next(s for s in (a.work/"temp/run.do_compile").read_text().splitlines()
                                  if s.startswith("export PATH=")))[1].split("=", 1)[1]
    try:
        with tempfile.TemporaryDirectory(prefix="camera-native-", dir=a.scratch) as temporary:
            scratch = Path(temporary)
            objects = {}
            def compile_unit(row):
                relative = Path(row["file"]).relative_to(original)
                source = a.source / relative
                assert source.is_file() and not source.is_symlink()
                output = scratch / relative.with_suffix(".o")
                output.parent.mkdir(exist_ok=True)
                args = shlex.split(row["command"])
                assert Path(args[0]).is_relative_to(a.work/"recipe-sysroot-native"), "FOREIGN_COMPILER"
                args[1:1] = ["-I"+str(a.source)]
                args[args.index("-o")+1] = str(output)
                args[args.index("-c")+1] = str(source)
                completed = subprocess.run(args, cwd=row["directory"], env=env, capture_output=True, timeout=180)
                (a.evidence/(str(relative).replace("/", "-")+".log")).write_bytes(completed.stdout+completed.stderr)
                assert completed.returncode == 0, "TARGET_COMPILE_FAILED:"+str(relative)
                return relative, output
            print("CAMERA_NATIVE_TARGET_COMPILE_STARTED", flush=True)
            with ThreadPoolExecutor(max_workers=4) as pool:
                objects.update(pool.map(compile_unit, commands))
            library = scratch/"libcamera-runtime.a"
            compiler = Path(shlex.split(commands[0]["command"])[0])
            ar = compiler.with_name("aarch64-aos-linux-ar")
            subprocess.run([str(ar), "rcs", str(library), *[str(v) for k, v in objects.items() if k.parent == Path(".")]], check=True, timeout=15)
            test_dir = build/"src/sm/launcher/runtimes/systemd-slot-component/tests"
            link = shlex.split((test_dir/"CMakeFiles/aos_sm_runtimes_systemdslotcomponent_test.dir/link.txt").read_text())
            executable = scratch/"camera-oem-runtime-tests"
            link[link.index("-o")+1] = str(executable)
            for i, token in enumerate(link):
                if token.endswith(".o"):
                    link[i] = str(objects[Path("tests")/Path(token).name.removesuffix(".o")])
                elif token.endswith("libaos_sm_runtimes_systemdslotcomponent.a"):
                    link[i] = str(library)
            completed = subprocess.run(link, cwd=test_dir, env=env, capture_output=True, timeout=60)
            (a.evidence/"link.log").write_bytes(completed.stdout+completed.stderr)
            assert completed.returncode == 0, "TARGET_LINK_FAILED"
            loader = a.work/"recipe-sysroot/usr/lib/ld-linux-aarch64.so.1"
            libraries = str(a.work/"recipe-sysroot/lib")+":"+str(a.work/"recipe-sysroot/usr/lib")
            print("CAMERA_NATIVE_TARGET_TESTS_STARTED", flush=True)
            # The existing runtime suite exercises root-owned A/B stores and
            # readonly unpacked directories. Use its established root fixture
            # identity; running it as the Builder login user is not equivalent.
            completed = subprocess.run(["sudo", "-n", str(loader), "--library-path", libraries, str(executable),
                                        "--gtest_output=json:"+str(a.evidence/"gtest.json")],
                                       capture_output=True, timeout=180)
            (a.evidence/"tests.log").write_bytes(completed.stdout+completed.stderr)
            tests = json.loads((a.evidence/"gtest.json").read_bytes())
            assert completed.returncode == 0 and tests["failures"] == 0 and tests.get("disabled", 0) == 0, "TARGET_TESTS_FAILED"
            assert b"CameraAccessUsesOnlyItsExplicitTarget" in completed.stdout and b"DefaultVdpPayloadIdentityIsUnchanged" in completed.stdout, "CAMERA_TESTS_NOT_EXECUTED"
            result.update(outcome="PASS_TARGETED_NATIVE_UNIT", tests=tests["tests"],
                          executableSha256=hashlib.sha256(executable.read_bytes()).hexdigest())
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        result["code"] = str(error) if isinstance(error, AssertionError) else type(error).__name__
    result.update(seconds=round(time.monotonic()-start, 2), scratchRemoved=True)
    (a.evidence/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result), flush=True)
    return 0 if result["outcome"] == "PASS_TARGETED_NATIVE_UNIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
