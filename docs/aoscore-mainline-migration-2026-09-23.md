<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Coordinated AosCore mainline candidate — 23 September 2026

Status: native/source-qualified candidate, **not a qualified Factory**.
Current Test and immutable Factory .36 remain untouched. Package, image,
clean-VM and live staging gates must still pass.

## Pinned inputs

All three recipes (CM, SM and IAM) select the same immutable triplet:

| Source | Revision |
| --- | --- |
| aos_core_cpp | `9d613a46df3c7f550062e2f19ae3406c57715694` |
| aos_core_lib_cpp | `5560291ba6914e36a5b841ade4d8fc54134a9e91` (v9.1.2) |
| aos_core_api | `af3552a0a5eb0237eff7f5f183780ca46c339cd3` (unchanged) |

Keep recipe-private library/API sources; do not modify the shared source cache.
The existing Yocto baseline, permission scopes, KUKSA identity/trust, models,
quotas and external publication contracts are unchanged.

## Patch disposition

| Previous patch/behavior | Mainline disposition |
| --- | --- |
| CM 0001 shared stream write lock | Removed: equivalent upstream implementation is present. |
| CM 0002 stale snapshot reconciliation | Upstream handles versions; retain cross-node rejection. |
| CM 0005 startup rebalance, 0007 shared storage | Consolidated with residual snapshot validation in new 0002; preserve failed owners and acquire/release pairing for mainline stable UID/GID references. |
| CM 0003/0004 idle full status, 0006 disconnect | Retained, adapted to the allocator interface; native default remains opt-in, Factory config 60 seconds. |
| SM 0001 systemd-slot runtime | Retained; add side-effect-free `InitInstances`, use the new utility header. |
| SM 0002 teardown | Rebased; preserve raw errno and owned container on real errors, normalize only proved absence. |
| SM 0003 replacement, 0004 preparation retry | Consolidated in new 0003 around mainline startup adoption. Failed teardown retains durable row, network and image. |
| IAM permission reply | Retained with real-server tests for 17/32 keys, each 256 characters. |
| IAM PKCS#11 | Keep cache capacity3 for the existing three token/flag keys. Remove the obsolete fixed allocator override; mainline injects IAM's HeapAllocator. Add 20 clear/reopen cycles with a retained old session. |

The library's unused historical fixed-pool macro still exists upstream. Its
presence is not evidence that the current LibraryContext uses a fixed pool.
The source validator checks both injected allocator and application ownership.
The Python fixed-pool replay remains a **historical negative control**, not
qualification of the new allocator.

## Native evidence

Isolated Linux ARM64 containers, no network during tests and no live VM mounts.
CM, IAM and SM application targets compile. SM includes container and production
VDP runtime; native boot/rootfs runtime targets are excluded here and must compile
in the actual package gate.

| Suite | Result |
| --- | --- |
| CM launcher/storage/UID | 47/47 |
| CM idle status | 11/11 |
| SM replacement/retry | 27/27 |
| CM transport lock harness | 17/17 |
| IAM gRPC server | 61/61 |
| Library permission handler | 7/7 |
| Library storage/state | 15/15 |
| Three-token PKCS#11 (real SoftHSM) | 14/14 |
| VDP runtime | 81 pass, 2 VM-only tests skipped |
| Container runtime | 42/42 |
| Actual crun adapter with injected errors | 5/5 |
| Network manager | 93/93 |
| Namespace cleanup | 4/4 |

Negative controls: pristine main plus storage tests fails17/43; the corrected SM
new-install fixture fails5/25 before the residual patch. A failed legacy-UID
acquire followed by cleanup exposed an extra reference-release regression;
explicit acquired flags close it. These residuals are not advertised as already
fixed upstream.

Native dependency exceptions are **test environment only**: Debian12 OpenSSL3.0
lacks `BN_signed_bin2bn`; use the application's declared OpenSSL3.2.1 at
`a7e992847de83aa36be0c399c89db3fb827b0be2`. The actual platform inventory already
pins OpenSSL3.2.6, which still requires package verification. Native crun1.14.3 is
`1961d211ba98f532ea52d2e80f4c20359f241a98`. GCC12 RelWithDebInfo (`-O2`) builds
without suppressing warnings; Debug and `-O3` expose upstream diagnostics and
do not establish a production failure. Namespace tests alone use SYS_ADMIN in a
disposable container. No product capability or policy was relaxed.

## Reproduction and acceptance boundaries

`tools/validate_aoscore_mainline.py` checks recipe/inventory parity and reconstructs
each recipe's patch series from pristine pinned Git objects. With
`--proof-reference`, every modified file and VDP runtime asset must match the
tested native source byte-for-byte. It never patches a cached checkout.

`tools/validate_iam_pkcs11_allocator.py --source-root <lib> --app-root <app>`
checks production allocator ownership, exact cache topology and call flags.
Use `AOS_CORE_LIB_SOURCE` and `AOS_CORE_APP_SOURCE` for the pinned source tests.

Compact native evidence is retained in the local proof directory
`/private/tmp/aos-mainline-migration-20260923.A2qEwO`; it contains synthetic test
fixtures, not live credentials. No generated binary, certificate or token belongs
in Git. Source qualification does not qualify Factory, Safe Stop, real providers,
Cloud reconnection, service quotas or preserved legacy UID records. Those require
the ordered package, clean image and sequential staging E2E gates.
