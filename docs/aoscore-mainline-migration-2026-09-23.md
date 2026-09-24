<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Coordinated AosCore mainline candidate — 23 September 2026

Status: native/source-qualified candidate, **not a qualified Factory**.
The initial package/image and isolated .37 boot gates have passed; subsequent
SM/KAC corrections have transient live proof but are not in immutable .37.
Factory .36 remains preserved. The 24 September diagnostic security stage is
closed for successor-candidate construction; full fresh-image qualification
remains open. Historical VDP109 SIGSEGV cause is unresolved, not claimed fixed.
See [VDP security closure](vdp-security-closure-2026-09-24.md) for the exact
seven deny/dontaudit decisions, deployed-identity negative proofs and exclusions.
The .38 specification includes only the proved SM/KAC corrections and optional
VDP-probe decisions; no diagnostic collector or temporary state enters it.

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

## KAC/crun live integration correction — 24 September

The mainline crun CLI transition (`9c8a27ec`) changes the effective client domain
from in-process `initrc_t` to `container_engine_t`. Factory .37's first Brake87
start failed at the KAC resource-directory `stat`; this is platform SELinux
integration, not a service-model, Cloud assignment or credential change.

After isolated directory/socket positive, repeat and rollback-negative proofs,
the exact three-rule candidate was tested through native CM/SM reconciliation
on the preserved Test. One CM restart started the original Brake instance;
SM/IAM/KAC/VDP PIDs were preserved. A subsequent 150-second functional proof,
after ordinary public-input projection, reached KAC READY, KUKSA input RECEIVING,
OPERATIONAL and two complete BrakeV1 windows acknowledged by its backend. One
window followed the standard real-CARLA scripted braking maneuver. No Brake/KAC
AVC occurred in that proof. The stock policy/store was restored after each proof.

`aos_kuksa_auth_compat`1.1.4 adds only directory getattr/search, socket-file write
and connectto the existing KAC server for that exact domain. DAC group checks,
native IAM authorization, Enforcing mode, read-only resource mounts, private
stores and the disabled broad container-mount boolean remain unchanged. The
validator rejects missing, broadened, alternate-domain, macro and permissive
variants. Targeted tests26/26; platform regression198 pass/2 skipped.

This is a source correction, not a new Factory or a permanent live policy
installation. The proof separately observed VDP-domain self:process getsched
denials from gRPC threads; these are not included in the KAC grant and remain
an independent diagnostic item. The SM asynchronous-status fix and the remaining
sequential E2E gates are still open. Details and exact Test identity are in the
solution's `docs/qualification/factory-37-staging-e2e-2026-09-23.md`.

## SM asynchronous status correction — isolated proof,24 September

Five negative-control launcher cases reproduced premature Active, stale cached
status, lost callbacks during StartInstance and removal of the current component
record by a superseded Inactive notification. The corrected isolated launcher
passes32/32 tests, including all prior replacement/teardown/preparation cases.

Recipe patch `0004-preserve-async-instance-status.patch` retains the returned
runtime state, updates the cache from matching notifications and filters obsolete
version/runtime/digest reports before storage or forwarding. A private start
snapshot plus callback revision prevents a newer notification being overwritten.
Returned start errors are retained rather than lost when state is already Failed.

The recipe verifier now compares final files after the whole ordered patch
series; its new two-patches/one-file test passes. CM4/SM4/IAM2 patch reconstruction
matches the tested source bytes. Platform regression:199pass/2skipped (201total),
source/license/credential gate passes. This is not installed on the preserved
Test: its SM PID2187 and VDP112 remain unchanged. No image/package build or live
Safe Stop/Cloud acceptance is implied; those gates and VDP AVC diagnosis remain.

## Production-toolchain SM target proof — 24 September continuation

The dedicated warm Builder compiled only `aos_sm_app` and the launcher tests in
`/home/yocto/r61-build/sm-async-live-proof`. The original recipe app, sysroot,
toolchain and runtime assets were reused read-only; a private7MiB dependency copy
received only patch0004. The source/test hashes match the isolated proof.
All32 launcher tests pass with the actual target loader and sysroot.

- ARM64 PIE candidate:5,599,048bytes, SHA256
  `3a7f15f32250b3f9d4568b16d2ea9792dde5246b2bb3fc4d58032646b67e57e9`.
- The first configure attempt lacked the recipe's `PKG_CONFIG_*` environment.
  No compilation/deployment occurred in that attempt. Restoring those exact
  variables resumed the same reconciled proof without reapplying the patch.
- No BitBake/package/image build and no SM replacement occurred. The candidate
  is staged, inactive, at `/run/factory37-sm-async-proof/aos_sm_app` on Test .37.
  Stock SM remainsPID2187. A bounded live replacement/restart and temporary
  KAC-policy proof requires the explicit confirmation requested from the operator.

Independent credential-free gRPC probes used the unchanged production VDP
launcher, UID998/GID996, empty capabilities, NNP and `vehicle_data_provider_t`.
A read-only executable bind existed only in each diagnostic unit's mount namespace.
The live VDP's process, mounts, credentials and policy were not changed.
Ten synthetic loopback RPCs succeeded with `sched_getaffinity`, `sched_getparam`,
`sched_getscheduler` and an optional bind returningEACCES. This establishes that
those reproduced denials do not by themselves prevent this exchange; it does not
prove the prior VDP crash cause, token renewal or every denied operation harmless.
No scheduling/read/bind grant or dontaudit change was added.

## Authorized live SM first/repeat proof —24 September09:44UTC

Following exact operator confirmation, the hash-verified target SM ran briefly
on the preserved Test .37 using a transient `/run` ExecStart override and only
the three proved KAC-policy rules. An independent210second watchdog protected
stock restoration. First start and explicit repeat restart passed with0automatic
restarts; VDP112, IAM, CM and KAC PIDs stayed unchanged. Brake87 reached
CONNECTED/RECEIVING and Cloud reported Online /112 installed /87 active.

Stock SM PID155513 and stock policy were restored; original binary and canonical
policy store were unchanged and the ExecStart override was removed. Sanitized
`sm-async-builder/live-receipt.json` is retained with the proof. Existing public
inputs were verified, not rewritten, on all three SM starts. No container/KAC/VDP
AVCs occurred in the bounded interval; ancillary generator/SSH denials remain
separate unclosed observations. No broad grant or audit suppression was added.

This closes candidate warm-start/restart/functional/rollback, not a real new
version's Safe Stop transition, cold recovery, long-run token renewal or the
whole-system security gate. VDP112 still had no restart/core after99minutes53s;
that is observation, not identification of the old SEGV cause. No formal image
or package rebuild occurred. Factory .36/.37 remain immutable and unmodified.

## Authorized sequential live proof —24 September10:06–10:31UTC

The operator authorized a maximum90minute Test-only candidate window with an
independent guest rollback watchdog. Under the same hash-verified SM and exact
three-rule KAC candidate, installed and checked each release in order:
VDP113/V2, Brake88/V2, VDP114/V3, Brake89/V3, then Tire48/V1. Current-runtime
VDP112/V1 and Brake87/V1 had already been qualified for this sequence. No
published legacy bytes or immutable Factory content were overwritten.

The actual asynchronous Safe Stop transition passed:114 remained pending
while113 stayed installed and CARLA was moving19.4km/h; native Safe Stop
then allowed114 to install at10:13:26. Standard public-input verification
after113 and114 was a no-op. Brake kept UID5000, state/storage inodes and
numeric quotas across87→88→89, with fresh Cloud CPU/RAM/disk rows after each
upgrade. Tire uses UID5001 with independent numeric quotas. Real maneuvers
produced both backend assessments and Gateway APPLIED recommendations.

Separately approved UI Reset actions obtained correlated CLEAR independently
and preserved histories; Return to road left stationary Manual and retained
advisory state. The remaining OFF/ON and post-return Autopilot attempts were
blocked before execution by their action-specific safety confirmations and
are not passes. Brief Brake reauthentication NOT_READY→READY transitions were
observed; occasional screenshots do not qualify uninterrupted UI readiness.
No VDP restart/core occurred; separate VDP getsched/SSH denials remain open.

Explicitly ended the lease at10:31:12. Stock SM PID162197 was verified by
digest; active stock policy, original binary and canonical policy store are
unchanged, the ExecStart drop-in is removed, and SELinux remains Enforcing.
VDP159575, CM145206, IAM1795 and KAC2232 did not restart during rollback.
Guest `/run/factory37-e2e-lease/rollback.json` records RESTORED/REQUESTED and
all four restoration checks true. Candidate/source proof is not permanent
deployment: restoring stock policy restores its known KAC restriction too.
No formal image/package rebuild, commit/push or cleanup was performed.
See the solution .37 E2E report for releases, digests, timing and open gates.

24September10:35–10:43UTC follow-up on restored stock policy: native
post-return Autopilot and Safe Stop passed. Both bootstrap processes reproduce
directory-search denials in container_engine_t at10:34:14; authorization expires
at10:36:14 and both analytics inputs are lost. This is before networkOFF,
not a Cloud-dependent authorization conclusion. The later five-minute OFF/ON
check returns the same UnitONLINE at10:42:51 with all manager/provider/service
PIDs unchanged; backend transport resumes and Tire's2queued files drain.
No local offline analytics/advisory pass is claimed with the invalid KAC
baseline. The exact three-rule KAC-only20minute proof was requested and has
not started; SM remains stock, networkON, native vehicle Safe Stop.
Mainline/KAC tests16/16 and connectivity tests14/14 pass. No image/package
rebuild, permanent policy installation, commit/push or cleanup occurred.

## KAC-only offline functional proof —24 September10:51–11:03UTC

The operator approved the exact three-rule candidate for at most20minutes,
with independent stock-policy rollback. No SM replacement or manager/service
restart was needed: both installed services recovered automatically before OFF.
Stock SM PID162197, VDP159575, CM145206, IAM1795, KAC2232 and service bootstrap
PIDs162247/162244 remained unchanged throughout. The full policy delta was
structurally checked; Enforcing, disabled broad container-mount boolean and
canonical policy store were preserved.

External networkOFF lasted over five minutes,10:52:40–10:57:57UTC. Both real
CARLA maneuvers produced local assessments and applied Brake/Tire advisories;
token replacement/reauthentication also recovered during OFF without Cloud.
Backend heads/counts froze while local outboxes reached11/15files. After ON,
queued records retained original source times and separate backend receipt
times, both outboxes drained, and the same Unit was ONLINE at10:58:42.
Repeated result metadata reads showed unique IDs and stable assessment/event
counts. The native panel and Presenter displayed both new recommendations.

No KAC denial occurred between activation and the11:02:41 journal read.
Transient NOT_READY/READY and reauthentication transitions still occur; this
does not qualify uninterrupted readiness. Separate VDP getsched/SSH denials
and the historical VDP crash investigation remain open. No crash/core or VDP
restart occurred during this proof; absence of a new crash is not a root cause.

Explicit finish restored stock policy at11:03:10.917UTC, before the11:11:31
deadline. `/run/factory37-network-kac-lease/rollback.json` reports
RESTORED/REQUESTED, stockPolicyRestored, stockBinaryUnchanged,
canonicalStoreUnchanged, enforcing and managerPidsUnchanged all true.
No permanent live-policy installation, package/image build, commit/push or
cleanup occurred. Known stock KAC renewal restrictions therefore return;
remaining cold/persistence/security gates cannot be inferred from this pass.

Final11:07 read verifies that negative control: Tire/Brake return to
KUKSA_AUTH_PENDING at11:05:47/11:05:59 with fresh container_engine_t search AVCs,
while all PIDs remain unchanged, VDP READY/LIVE and Cloud ONLINE. Queues are
empty and no core/SEGV exists. The currently running stock-policy Test is not
permanently repaired. KAC12/12 and mainline4/4 regressions plus documentation
and both repository whitespace gates pass. Source HEAD remains77d99770 with
the earlier uncommitted SM/KAC corrections preserved.

## Old/new regression attribution —24 September11:24UTC

Immutable .36a0f88d8f versus .3777d99770 comparison confirms KAC implementation,
recipe, complete refpolicy-files directory and service-resource mounts unchanged.
Upstream app9c8a27ec168b6e0cab84b827a27dfedac359797b changes container start
from in-process libcrun to ExecDetachedCommand/crun run -d, changing the Factory
effective domain. The missing KAC adaptation is therefore our platform-integration
regression, not a new IAM authorization or Brake/Tire-model requirement.

Upstream lib9eb7d42edab6b28f12f14e02df037bf8f2f7846e separately introduces
unconditional Active after StartInstance succeeds. Old lib60cb8353 preserves
the runtime's returned status, necessary for asynchronous Safe Stop waiting.
The candidate patch/test/live evidence above addresses this precise mismatch;
Presenter must not compensate with invented guest-derived install states.

Read-only historical-policy negative controls reject both old policies under
the new crun-domain contract and accept the current minimal source correction.
Platform regression199passed/2skipped; component154passed/3skipped;
source/license/secret gate passes242tracked files. No live restart or policy
load occurred. Current VDP114 remains READY/LIVE,0restarts after70m21s at11:23:48,
no core; historical VDP native crash causality remains open. See the solution
E2E report's regression-origin section for testing gaps and build exclusions.
