<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# VDP optional-probe security policy

This stable path is referenced by the SELinux policy source. It documents
current denied optional probes, not instructions to preserve an old Test,
recreate diagnostic images or resume an earlier Factory build.

The source domain is `vehicle_data_provider_t`. The exact operations below
remain denied; only their specific audit events are suppressed. No new allow,
scheduling change, broad ioctl range or generic Aos filesystem access follows.

| Target and operation | Optional use / permitted fallback |
| --- | --- |
| self process `getsched` | gRPC/Abseil own-thread scheduling inspection; transport continues without the result |
| `sysfs_t:file read` | CPU-count probe of `/sys/devices/system/cpu/possible`; transport uses a fallback |
| `proc_t:file read` | CPU-count fallback at `/proc/stat`; transport still handles denied access |
| `node_t:tcp_socket node_bind` | IPv6 availability probe at `::1:0`; failure selects IPv4, not a listening-service permission |
| `initrc_runtime_t:file ioctl 0x5401` | CPython TCGETS/isatty on a credential file; ordinary file reading does not require terminal control |
| `aos_var_run_t:dir getattr` | Non-strict parent metadata resolution; existing search authority is unchanged |
| `sysctl_vm_t:dir search` | glibc optional overcommit probe; its default path works without reading the setting |

The layer validator pins the deny/dontaudit set. Negatives reject missing or
extra suppression, wider ioctl ranges, extra scheduling permissions,
optional-probe allows and broad parent access. The independent PIN-path
probe remains denied. Disappearing audit messages are not proof of new
permission or successful platform operation.

## Validation and evidence boundary

Any policy change requires the production launcher identity, domain, empty
capability sets, NoNewPrivs and systemd sandbox. A harness identity mismatch
is corrected in the harness, not by relaxing deployed file permissions.

Use an isolated transient policy store, automatic rollback protection and
fresh scoped AVC evidence. Compare the full policy: allow rules, types,
booleans, permissive domains and constraints must remain unchanged when
reviewing only these suppression decisions. Verify stock policy restoration,
canonical-store preservation, Enforcing mode and unchanged unrelated owners.

The [current integration baseline](https://github.com/alexmaninblack/aosedge-sdv-demo/blob/main/docs/qualification/current-baseline.md)
owns image-specific runtime acceptance. Focused transport/policy tests do not
prove a native-crash cause, complete service E2E or every negative case.
Preserve any new failure for diagnosis; do not repeat an old image/VM
retention instruction as a current setup requirement.

## Primary implementation references

- [gRPC IPv6 probe](https://github.com/grpc/grpc/blob/v1.75.0/src/core/lib/event_engine/posix_engine/tcp_socket_utils.cc)
- [gRPC CPU-count fallback](https://github.com/grpc/grpc/blob/v1.75.0/src/core/util/linux/cpu.cc)
- [Pinned Abseil scheduling inspection](https://github.com/abseil/abseil-cpp/blob/76bb24329e8bf5f39704eb10d21b9a80befa7c81/absl/synchronization/mutex.cc)
- [glibc heap-shrink fallback](https://github.com/bminor/glibc/blob/glibc-2.39/sysdeps/unix/sysv/linux/malloc-sysdep.h)

Exact original transient measurements remain in this file's Git history,
not a second active qualification diary. Keep credentials, raw telemetry,
memory and generated binaries outside Git.
