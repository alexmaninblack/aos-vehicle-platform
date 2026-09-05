<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CM shared gRPC write lock — targeted qualification

Date: 2026-09-05. Factory source baseline: `72c0224ba65537bed41a6ca12a7bf3a9c07da194`.
Upstream CM source remains `9eecb80c4994937b5c8cbe0464970f81e8ad4c2d`.

## Change

Backport upstream commit `6e0b1980e71ea6ee9979292a8aa336574d317f09` unchanged.
`SMHandler::SendMessage` and `SyncMessageSender::SendSync` must hold the same
write mutex while writing to their shared gRPC stream. Response bookkeeping
uses its own mutex; the shared write lock is not held while waiting for a response.
No SM runtime, DNS, provisioning, Unit Model, credentials or service configuration changes.

## Regression proof

Apply `concurrent-writes-test.patch` to the pinned AosCore checkout. With the
existing native test dependencies configured, run:

```sh
cmake --build build-r61 --target aos_cm_smcontroller_test -j 6
timeout 45s build-r61/src/cm/smcontroller/tests/aos_cm_smcontroller_test \
  --gtest_filter=SMControllerTest.ConcurrentCloudStatusAndNodeConfigWrites
```

The test uses the actual SMController and a local gRPC server/client. It sends
5,000 asynchronous Cloud-status messages concurrently with 1,000 synchronous
node-config requests. It uses no Cloud credentials or external Cloud connection.

- Original CM: first execution aborted, exit 134, with
  `GRPC_CALL_ERROR_TOO_MANY_OPERATIONS`, `call_op_set.h:975/977`.
- Exact upstream backport: same test passed; 100 repeated executions passed.
- Full existing SMController suite including the regression: 20/20 passed.
- Native test cache uses gRPC 1.54.3; this is not the VM runtime qualification.

## VM-compatible compilation and live proof

Offline Yocto target-only build, `qemuarm64`, retained .27 layers/toolchain and
AosCore library/API pins. `bitbake -c compile aos-communicationmanager` succeeded:
1,557 tasks considered, 1,548 reused, no image task.
VM build links the production gRPC 1.60.1, not the native test-cache version.

Stripped ARM64 binary: 5,598,976 bytes; SHA-256
`a376b824444a282baa1bbd2dbc0ade42eb055b7335467860ffd84970c83f74cd`.
Interpreter: `/usr/lib/ld-linux-aarch64.so.1`.

The existing Test and demo Production VMs ran this exact binary through an
explicit temporary `/run/aos-cm-write-fix/aos_cm_app` ExecStart drop-in. Original
`/usr/bin/aos_cm_app` was retained. Owner/mode and `bin_t` label match the installed
binary; SELinux remains Enforcing and no policy changes were made.

At 09:27:51 UTC, `democtl status all --guest --cloud --profile oem-delivery`
reported both Units Online, provisioned, in their correct role Unit Sets, with
CM active/running, Result=success and NRestarts=0. Both running binary digests
matched the target above. No reprovisioning or Cloud mutation was used.

Both VMs completed the real CM/SM handshake and node-config request, with no
fresh kernel AVCs or gRPC assertion messages after their respective CM starts
(Test 09:24:14 UTC; demo Production 09:27:17 UTC). Source-layer validation and
all 21 existing R6.1 layer-contract tests passed before the package/image gate.

This proves the race regression and live CM/SM/Cloud connection. It does **not**
qualify a new Factory Image or a VM reboot: `/run` overrides disappear on reboot.
Image construction, fresh VM cycles, restart, and end-to-end acceptance are
separate gates. Transient overrides must be removed and stock behavior restored
after the live proof; record final disposition in the demo qualification record.
