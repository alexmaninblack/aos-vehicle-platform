<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .37 — coordinated AosCore mainline candidate

Status: source/native gates passed; package, image and live gates pending.
Preserve immutable .36 and the current diagnostic Test. No deployed services,
credentials, Subjects or working service data enter this image.

The pinned inputs, patch disposition and native results are in
[the mainline migration record](../docs/aoscore-mainline-migration-2026-09-23.md).
Keep the existing platform runtime, KAC, provider, SELinux, six-partition disk
layout and all accepted .36 functionality. Remove only superseded patches and
the obsolete fixed PKCS#11 allocator override; cache3/permission-key256 remain.

Before image construction:

1. Reconstruct each recipe from the pinned triplet and compare with native proof.
2. Compile CM, SM (including boot/rootfs/container/VDP), IAM and KAC using the
   warm production toolchain and offline caches.
3. Run native launcher/storage/UID, idle-status, replacement, permission reply,
   crypto cache, runtime and KAC/provider tests with that toolchain. Record exact
   executed/skipped counts; no fallback to an older source checkout.
4. Verify actual CMake source bindings, uniform permission-key256, IAM cache3,
   and packaged configuration: idle60s, public resources, IAM/KUKSA integration.
5. Require package QA, then one image build/image QA and unchanged disk assembly.

Freeze as BUILT_NOT_LIVE_QUALIFIED. A clean isolated smoke must precede separately
authorized staging use. Live acceptance: each service/VDP release installed and
verified before publishing the next; VDP Safe Stop; persistent data and stable
UID/resource metrics; external network OFF with continued local analytics and
stopped backend ingress; ON/reconnect/queued delivery; owned-Test Finish. Do not
claim that a fresh image repairs old mismatched UID records on the preserved Test.
