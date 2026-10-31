<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# OEM Camera Access — Vision foundation

Camera Access is an independent Vision-only OEM platform component, not a VDP
profile or an AI application. The retained Brake/Tire VM is outside its scope.
The source foundation implements the bounded camera-data boundary; it is not
yet an installable FOTA payload, daemon or native Aos resource grant.

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
These are internal core APIs, not a frozen socket or HTTP protocol.

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
python3 -B tools/check_camera_access.py
```

This single source scenario runs the Camera Access unit/contract tests,
repository policy and retained telemetry/Factory-layer validators, with an
explicit guard against modifying the old product source. It reports timed
phases and `PASS_SOURCE_ONLY`, never deployment/live acceptance.
The tests start no server, simulator, VM or container and use synthetic JPEG
headers solely for envelope-validation cases. They prove neither pixel decode,
native authorization, live camera delivery nor installed-package acceptance.

## Remaining deployment gates

Freeze and prove authenticated Gateway ingress, native Aos-managed local IPC,
actual non-root identity/peer isolation, SELinux, restart and resource revocation.
Give Camera Access a distinct OEM payload/target and qualify the existing native
lifecycle mechanism for that target; never rename it as VDP or use a VDP slot.
No recipe, systemd unit or resource declaration is added to Main by this packet.
