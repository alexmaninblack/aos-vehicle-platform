<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# OEM Camera Access — separate Vision platform

Camera Access is an independent Vision-only OEM platform component, not a VDP
profile or an AI application. The retained Brake/Tire VM is outside its scope.
The bounded camera-data core, closed Unix IPC daemon, distinct OEM payload and
native activation profile are implemented in source. The explicit Vision
bootstrap/image target adds its own account and read resource, not a VDP slot.
An implemented source target is not an installed/qualified native Aos service.

## Boundaries

The simulation-side Gateway owns CARLA capture. A future authenticated OEM
adapter supplies the trusted selected-source binding and images to Camera
Access. Perception consumes admitted frames without knowing CARLA's address or
owning the sensor. Assessment and result delivery are separate consumers/work.
No VDP, KUKSA, model, Cloud, provisioning or motion API is imported by this core.

The [machine-readable profile](../contracts/camera-access/profile.json) freezes
front RGB 1280x720 JPEG/FOV 50, strict frame metadata, bounds and exclusions.
`select(SourceBinding)` is an OEM-only in-process entry, **not authentication**
and not a remotely exposed method. Untrusted frame fields cannot select an
origin or change the active epoch/calibration. No secret or credential database
is introduced. Actual native resource/peer authorization is a deployment gate.

`admit(metadata, jpeg)` checks exact fields, selected identity, profile, size,
SHA-256 and JPEG SOF dimensions before a downstream decoder can allocate pixels.
It does not fully decode/validate compressed pixel data. Only two immutable
frames are retained (at most 8 MiB JPEG bytes); no on-disk history or growing
FIFO exists. Slow inference gets the latest valid 80–120 ms world-frame pair.
Gaps, repeats and time regressions are never repaired by interpolation.
The original sensor time remains distinct, including observed +50-ms offsets.

`take_pair()` has one Perception delivery cursor. A repeated read returns no
new pair; replacing an unread pair is counted. `status()` exposes fixed reason
codes/counters, not source identifiers, calibration hashes, JPEGs or credentials.
These remain internal core APIs. The separate
[native contract](native-activation.md) defines the closed Unix protocol,
kernel peer checks, resource projection and independent OEM target.

## Loss, age and restart

Source/epoch/calibration changes explicitly flush images and reset the cursor.
Identical active selection is idempotent. Disconnect clears pixels, not the
current epoch's frame/time high-water marks; reconnect under the same binding
therefore still rejects replay. A process restart has no persisted replay
database: the authenticated adapter must establish a new session/epoch before
live admission. This condition must be proven in the future native scenario.

Both pair members must be no more than one second old in the **receiver's
monotonic clock**. Rejected packets cannot refresh them. Delivery becomes
explicitly stale/unavailable, not black pixels or zero detections. This bound
is local retention policy, not a qualified capture-freshness budget. Host and
guest monotonic clocks are not subtracted; pixel/capture-time alignment and
end-to-end age remain unqualified. The existing engineering world-frame
association is retained honestly, not presented as a CARLA source fix.

## Run offline source checks

From this repository's root, with the prepared development Python:

```sh
python3 -B tools/check_camera_access_native.py
```

This single source scenario runs Camera Access unit/contract tests, repository
policy and retained telemetry/Factory/mainline validators, preserving Main's
selectors, VDP bootstrap and resource defaults. It reports `PASS_NATIVE_SOURCE_ONLY`,
never deployment/live acceptance. The earlier `check_camera_access.py` remains
the frozen foundation-packet scope check; run it at its foundation source pin,
not as permission to widen that earlier packet.
The tests start no server, simulator, VM or container and use synthetic JPEG
headers solely for envelope-validation cases. They prove neither pixel decode,
native authorization, live camera delivery nor installed-package acceptance.

## Remaining deployment gates

Qualify transient non-root IPC/policy, the Vision bootstrap/image and normal
independent Unit provisioning, native OEM activation and actual Aos-managed
consumer delivery/revocation on M4. Authenticated Gateway ingress remains its
own gate. The narrow policy compiles but has not yet passed live AVC/rollback
proof; do not call it an accepted live security result. Neither manual crun,
root socket access nor unit mocks count as native SM allocation. Current Main
selectors, image, VM, Test and data are not modified or replaced.
