<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# CM VLAN allocation correction

The installed M1 journey on 3 October reproduced a guest networking failure
while updating Brake 105 V1 to 106 V2 on Factory .39. At 10:39:25 UTC, CM
allocated VLAN 4095 for the SP network. SM failed to create that VLAN with
`Input data out of range`, leaving the new service instance failed. VDP 130 V2
and the three managers remained active. This was not an application algorithm,
upload, credential or UI-only failure.

The exact core application baseline is
`9d613a46df3c7f550062e2f19ae3406c57715694`. Its allocator calls the exclusive-
upper-bound `RandInt(4096)`, allowing 0 and 4095. The uniqueness check also
continues the inner loop rather than rejecting an occupied candidate.

## Proof and source change

An automatically cleaned, isolated guest network namespace accepted VLAN 4094
and rejected 4095 with `8021q: Invalid VLAN id`. No live interface, persistent
database or service state was changed by this proof.

An isolated copy of the actual production recipe sources, toolchain and sysroot
reproduced four failing boundary/collision regression tests. With the correction,
all 31 native CM network tests passed, including 27 existing cases. The candidate
ARM64 CM executable compiled and was stripped and inspected. It is 5,664,496
bytes, SHA-256 `26d1c5aa48ea9986f6263bfaa448a5faf3bf532f15f4999aa1ab9cd76a074483`.
This is a target proof, not a live replacement or image acceptance result.

Recipe patch `0008-allocate-valid-unused-vlan-ids.patch` limits new allocations
to 1–4094 and retries reserved or occupied candidates within the existing four-
attempt budget. Exhaustion fails without persisting a new network. The patch
does not change identities, trust, quotas, storage, scheduling or security policy.

## Qualification boundary

Factory .40 is the successor candidate specification, not an accepted baseline.
It retains .39's pins and configuration and adds this correction only. Existing
persisted network rows are not silently rewritten. The failed disposable Test
must remain available until evidence is captured; a fresh Test on a corrected
immutable image is required for full serial-version qualification. Repeated
restart or database editing on .39 would not establish an installer fix.

Private target proof evidence is retained in the warm Builder at
`/home/yocto/r61-build/cm-vlan-proof-20261003`. Factory .39, Production .31 and
their manifests remain unchanged. No upstream submission or public release is
implied by this source correction.
