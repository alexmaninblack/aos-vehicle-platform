<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CM shared gRPC write-lock regression fixture

This directory retains the targeted concurrency regression patch, not an
installed-image selector or an instruction to restore old VM overrides.

The fixture pins AosCore source
`9eecb80c4994937b5c8cbe0464970f81e8ad4c2d` and the unchanged upstream fix
`6e0b1980e71ea6ee9979292a8aa336574d317f09`.
`SMHandler::SendMessage` and `SyncMessageSender::SendSync` must hold the same
write mutex for their shared gRPC stream. Response bookkeeping keeps its own
mutex; the write lock is not held while waiting for a response.

## Specialist execution

Apply `concurrent-writes-test.patch` to its exact pinned source with the
matching native test dependencies. In that isolated checkout:

```sh
cmake --build build-r61 --target aos_cm_smcontroller_test -j 6
timeout 45s build-r61/src/cm/smcontroller/tests/aos_cm_smcontroller_test \
  --gtest_filter=SMControllerTest.ConcurrentCloudStatusAndNodeConfigWrites
```

This is an explicit specialist compile/test command, not an ordinary
documentation check. It uses the real SMController and a local gRPC server/client:
5,000 asynchronous status messages run alongside 1,000 synchronous config
requests. No Cloud credentials or external Cloud connection are needed.

The regression distinguishes the shared-write race from unrelated runtime,
DNS, provisioning or credential behavior. Its native dependency versions
do not establish the guest ABI or selected Factory source. Exact earlier
measurements and transient live proof remain in Git history.

## Acceptance boundary

Fixture success is not a new image, reboot or complete demo qualification.
Use the [current baseline](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/qualification/current-baseline.md)
for selected media and scoped live results. Do not reapply an old ExecStart
override, replace an installed binary or reprovision a Unit based on this
reference. Preserve stock policy, identities and unrelated resources.
