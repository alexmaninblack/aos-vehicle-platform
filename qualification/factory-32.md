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
was required for that proposed interruption. This boundary was superseded by
the authorized context-only unlink correction; Docker Desktop was not restarted.

## Clean Test progress — 12 September 2026

Demo Control context fix `de7a6e8` completed old-Test cleanup. Original .32 was
copied and SHA-verified into Test's separate backing without changing Production
.31. A fresh Test started with working SSH, DNS and role initialization (61.53 s).
Provisioning completed in 20.39 s; new Unit
`923b9820-999b-41bb-91db-b2a2c469e743`, UID
`5aa1f8e4a1114467a6ccfb269c62a7a8`, Online in Test Vehicles. Both backend containers
were recreated from their retained images/volumes, without restarting Docker or
Watt. CARLA/Gateway connected to Test; Driving Control and telemetry show Safe Stop.

The native installed managers are active with zero restarts, not transient copies:

- SM `/usr/bin/aos_sm_app`, SHA-256
  `936fbd563f7e9d54651504f5aeba84fee0f3736861d30c2efb60eb564e039783`.
- CM `/usr/bin/aos_cm_app`, SHA-256
  `85e03a5206576c71a571a46ef90345d43037ea71b2e00c77181d247be533028d`.
- Both native service input resources are present in `/etc/aos/resources.cfg`.
- SM observation: SELinux enforcing, zero denied entries since SM startup.

Qualification remains open: Cloud lists VDP 18.0.0 `to be installed`, while the
native retained desired status contains zero items/instances and the provider
payload is not installed. CM remains connected and receives acknowledgements;
no SM startup failure is reported. This is an observed delivery gap, not an
established Cloud or image root cause. Preserve this Test for diagnosis rather
than publish a replacement release or reapply transient managers. Services,
mock backend ingestion and reboot recovery have not yet been proved on .32.

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
