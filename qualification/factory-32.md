<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .32 — native service recovery

Status: source prepared; build and clean Test qualification pending.

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

Native correction proof: 77 affected SM tests and four CM snapshot tests passed
before this image integration. Factory resource/hook tests and the unchanged
five native Factory/VDP configuration regressions are the build gates; record
actual clean-image results separately rather than inheriting transient success.
