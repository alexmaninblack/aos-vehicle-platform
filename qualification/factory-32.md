<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .32 — native service recovery

Status: built and frozen on 12 September 2026; clean Test qualification pending.

## Build result

- Platform source: `04fc8270c55ff5c35f1e98af534a5efccb035464`.
- Release: `6.1.1-maninblack.32/main-qemuarm64`, raw image, 6,997,147,648 bytes.
- SHA-256: `f56e037ff6ce11d1dea769055dc160a5a9a8061bbdd2d67745a3042181be2f14`.
- Artifact: `demo-artifacts/aosedge-sdv-demo/factory-images/6.1.1-maninblack.32/main-qemuarm64.img`
  beneath the operator's `OpenAI` workspace; not committed to Git.
- Offline manager compile, five native Factory/VDP regressions, manager package
  QA, final packaged resource/projector/hook checks, filesystem/image QA and
  unchanged disk assembly passed. Host transfer SHA matched; image is read-only.
- Eleven focused Platform tests and 80 affected Demo Control tests passed.
- Package QA retained six nonfatal `buildpaths` warnings in manager binaries,
  debug files and static libraries; the gate was not bypassed.
- Builder stopped cleanly. Current Test, Production, .31 and Cloud state were
  not changed. No transient overrides were removed from the running Test.

The user authorized the bounded Test-only lifecycle change on 12 September.
Demo Control now supports a separate Test .32 backing without replacing or
modifying Production's .31. Local lifecycle and Subject-retention regressions
passed; live clean Test and reboot qualification remain open.

12 September 02:52 UTC continuation: Demo Control retired the old Test Cloud
Unit/Node and confirmed both retained service Subjects have zero Unit recipients.
Production .31 remains running. Old Test local cleanup is paused because Docker
Desktop retains its context file after owned backend container removal. The
existing recovery command refused to restart Docker while other containers run;
no restart/bypass was attempted. Separate authority for that interruption is
required before continuing. No .32 Test VM has been created or qualified yet.

The user authorized the successor image after the 12 September 2026 transient
proof. Preserve .31 and Production until the new Test result is established.

## Included scope

- All .31 DNS, role, persistent VDP store and Safe Stop behavior is retained.
- Native SM idempotent container teardown, failed-replacement preservation,
  and retry of failed same-version service preparation are recipe patches.
- Native CM serialized stream writes and stale-instance snapshot reconciliation
  are recipe patches. No new service launcher or token authority is added.
- Native resources include the two narrow Brake/Tire public-input mounts.
- The accepted Demo Control projector is packaged byte-for-byte. SM systemd
  pre/post hooks restore volatile inputs from durable committed VDP state and
  verify process/slot agreement. Missing/in-flight data is deferred without
  blocking native recovery. No identity, credential, VDP payload or live VM
  state is copied into the image.
- Warm input refresh remains the existing explicit Demo Control operation;
  no background refresh mechanism is introduced by this image.

## Qualification sequence

Use `democtl image build 6.1.1-maninblack.32` for one offline warm-tree build,
package/image QA, unchanged six-partition disk assembly and transfer SHA check.
The Factory artifact is not live-qualified by its successful build.

Then use Demo Control to create a clean Test from that immutable artifact,
start/provision it, deliver compatible VDP and the existing permission-free
Brake/Tire mock releases, and verify Cloud/native process/backend identity.
Reboot with retained assignments; require automatic resource/input restoration
and both services running without transient CM/SM drop-ins or manual restarts.
Production is excluded. Failed Cloud delivery must be diagnosed from logs,
not bypassed with replacement releases or erased runtime databases.

KUKSA access and real telemetry remain excluded by the known Cloud permissions
defect. Successful mock backend records do not qualify actual vehicle advisory.

## Source checks

First build attempt: both managers compiled and all five native Factory/VDP
tests passed. CM package QA rejected build-only CMake crypto fixtures under
`/usr/usr`; the CM recipe now excludes that staging tree exactly as SM already
does. Final service resources are merged after native `do_update_config`.
Builder stopped automatically; no image was published from the failed attempt.

Native correction proof: 77 affected SM tests and four CM snapshot tests passed
before this image integration. Factory resource/hook tests and the unchanged
five native Factory/VDP configuration regressions are the build gates; record
actual clean-image results separately rather than inheriting transient success.
