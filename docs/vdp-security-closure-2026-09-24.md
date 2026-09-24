<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# VDP diagnostic security closure — 24 September 2026

## Decision and limits

The reviewed common runtime and seven exact optional-probe deny decisions have
passed production-identity transient proof. They can enter a **Factory .38
candidate**, not a live-qualified baseline. This is not a native-crash fix claim.
The earlier VDP109 SIGSEGV has no preserved native stack; its cause remains
unresolved and was not reproduced on the reviewed current runtime. Keep the
diagnostic .37 Test, .36/.37 images and evidence until successor qualification.
Stop the next live qualification for diagnosis on any new SIGSEGV.

The separate KAC/crun three-rule integration correction and SM asynchronous
status patch are documented in the mainline migration report. This VDP change
grants **no new permission** and does not relax TLS, freshness, capabilities,
systemd hardening or service identity. Unrelated host/SSH AVCs are not hidden.

## Exact optional-probe decisions

Source domain is `vehicle_data_provider_t` in every row. All operations below
still return EACCES under the candidate; only their exact audit events are
suppressed. No `setsched`, broad ioctl range, system configuration write or
generic Aos directory/file access is allowed.

| Target and operation | Observed use and validated fallback |
| --- | --- |
| self process `getsched` | CPU-affinity/own-thread scheduling inspection; gRPC/Abseil transport continues without the optional result. |
| `sysfs_t:file read` | CPU-count probe of `/sys/devices/system/cpu/possible`; transport continues. |
| `proc_t:file read` | CPU-count fallback at `/proc/stat`; transport continues. |
| `node_t:tcp_socket node_bind` | gRPC IPv6 availability probe binds `::1:0`; failure selects the IPv4 path. This does not authorize a listening service. |
| `initrc_runtime_t:file ioctl 0x5401` | CPython TCGETS/isatty on regular systemd credential files; file reading succeeds without terminal control. Only this ioctl number is suppressed. |
| `aos_var_run_t:dir getattr` | Non-strict `Path.resolve()` metadata checks on four parent directories; the installed entrypoint resolves correctly despite EACCES. Existing directory search is unchanged. |
| `sysctl_vm_t:dir search` | glibc2.39 optional `/proc/sys/vm/overcommit_memory` probe while freeing synthetic heap allocations; its default path works without reading the setting. |

The deny/dontaudit set is pinned by `validate_r6_1_layer.py`. Negative tests reject
missing/extra suppression, expanded ioctl range, extra scheduling permissions,
optional-probe allow rules and broad parent access. The pre-existing native
OpenSSL PIN-path probe also remains denied; this change grants no PIN access.

Primary implementation references:

- [gRPC1.75 IPv6 loopback availability](https://github.com/grpc/grpc/blob/v1.75.0/src/core/lib/event_engine/posix_engine/tcp_socket_utils.cc)
  returns false when its bind probe fails.
- [gRPC1.75 CPU count fallback](https://github.com/grpc/grpc/blob/v1.75.0/src/core/util/linux/cpu.cc)
  uses a conservative fallback when the query fails.
- [Pinned Abseil scheduling inspection](https://github.com/abseil/abseil-cpp/blob/76bb24329e8bf5f39704eb10d21b9a80befa7c81/absl/synchronization/mutex.cc)
  reports an unsuccessful scheduling query without making it a transport failure.
- [glibc2.39 heap-shrink probe](https://github.com/bminor/glibc/blob/glibc-2.39/sysdeps/unix/sysv/linux/malloc-sysdep.h)
  has a default when the overcommit setting cannot be opened.

## Production-equivalent proof

The preserved .37 Test ran the **installed VDP114/V3 runtime** with Python3.12,
gRPC1.75 and glibc2.39 through its production launcher: UID998/GID996,
`vehicle_data_provider_t`, empty capability sets, NoNewPrivs1 and the normal
systemd sandbox. A private mount replaced only the diagnostic unit entrypoint.
Live services, real credentials and telemetry were not used or changed.

Disposable loopback mTLS VISS and TLS gRPC servers supplied synthetic frames and
authorization. The fixture accelerated staleness/reconnect timing and disabled
its advisory consumer; neither change touched live configuration. This is a
transport/security proof, not a synthetic substitute for the separately recorded
real advisory and network OFF/ON tests.

| Run (UTC, 24 September) | Result |
| --- | --- |
| 11:46:00–11:47:28, stock policy | 80.02s runtime, 312 reconnect cycles, 625 authenticated sets; 936 duplicate frames, 104 stale periods, 104 forced disconnects and 104 out-of-order frames. Exit0, no SIGSEGV. |
| 11:51:50–11:53:18, five-rule candidate | 80.03s, 290 cycles, 581 sets; duplicate/stale/disconnect/out-of-order faults handled. Exact denied syscalls remain EACCES, scoped AVC set empty. |
| 11:55:01–11:55:17, early import | Installed runtime imports and short transport probe pass. |
| 11:59:40–11:59:48, actual entrypoint | Installed `provider_main.py --self-test` passes despite the parent metadata denials. |
| 12:03:35–12:03:54, startup negatives | Exact path resolution and glibc heap probe reproduce the remaining denials; normal operation continues. |
| 12:05:34–12:05:50, full seven-rule candidate | All seven operations remain denied, scoped AVC set empty; 27 authenticated sets and exit0. |

Every transport run rejects a wrong CA, wrong server name, missing client
certificate and invalid gRPC authorization. The first two produce certificate
verification errors; unauthenticated gRPC returns UNAUTHENTICATED. No optional
denial is reclassified merely because an audit message disappeared.

Both temporary policy stores used independent automatic rollback protection.
Full policy comparison permits only the listed deny/dontaudit additions;
allow rules, types, booleans, permissive domains and constraints are unchanged.
Restoration at11:53:18 and12:05:50 verifies stock active policy, unchanged canonical
store, Enforcing mode and unchanged manager/provider PIDs. Stock active policy
digest: `0974d04f730ed91042963e504031dd152efe6067eb3e2925d70585c5781c4faf`.

The first harness attempt at11:44 is excluded: a synthetic root-owned key was
passed directly instead of through LoadCredential. The harness was corrected;
no production file permissions were relaxed. A host-side quoting failure before
SSH is also excluded. Neither is a product defect or passing run.

## Evidence and remaining gates

Compact receipts are retained under the private proof root
`/private/tmp/aos-mainline-migration-20260923.A2qEwO/security-evidence`.
Do not commit private keys, JWTs, raw telemetry, memory or generated binaries.
The solution qualification report records temporary core-capture removal.

Platform regression after these source changes: **202 tests, 200 passed,
2 explicitly skipped**; targeted policy/lifecycle suite25/25. Native KAC10/10,
provider and verifier programs pass using the production toolchain. Source and
recipe/package gates must be rerun at the committed .38 build checkpoint.

Remaining qualification is a new immutable image, isolated clean boot/repeat,
then separately authorized fresh staging E2E with one version at a time,
Safe Stop for VDP, live advisory, independent Reset, offline local operation,
backend delivery recovery and security observations. Neither this document nor
a successful build promotes the candidate or retires the preserved diagnostic VM.
