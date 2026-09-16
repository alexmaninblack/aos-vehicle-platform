<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Factory .34 — native permissions and advisory readiness

Status: authorized consolidation candidate, 16 September 2026; not built or
clean-boot/UI qualified. Preserve the running staging Test and immutable .33
until the successor passes. Production is excluded.

## Source scope

- Preserve .33 service replacement, CM reconciliation/60-second idle status,
  Factory role/DNS, native service inputs and component Safe Stop gates.
- Compile CM, SM and IAM consistently with a 256-character permission key
  capacity. IAM's response uses the existing 32-function map capacity rather
  than the three-service count. No authority or permission semantics change.
- Package the proved KAC time-marker read/search policy and soft activation
  dependency on VDP startup. No broad policy grant or new listener.
- Include the VSS advisory actuator/readiness and wheel-slip schema, and the
  native Provider's two additional readiness read scopes (29 total scopes).
- Include VDP V3 advisory/readiness transport in source. Factory remains the
  unprovisioned baseline; delivered functional versions remain Cloud updates.
- Preserve the original native PKCS#11 signer semantics. Diagnostic stages
  are fixed, non-secret labels. No experimental crypto fallback is retained.

No transient /run files, token, key, policy store, live Unit/Subject, installed
service, demo estimate or backend record is copied into the image. The disk
uses the same six-partition assembly and offline warm Builder/caches.

## Preserved-Test evidence and gates

On staging Test 42c0bf43-4eb7-44e6-8c74-f60f9959da66, VDP70/V3,
Brake49/V3 and Tire30/V1 have real KUKSA telemetry. Both services produced
Gateway-confirmed advisory, accepted independent Reset requests, and produced
new warnings from real collision-free CARLA maneuvers. Backend UI Reset and
native dashboard state were observed. Assessments remain explicitly demo
synthetic models, not production diagnoses.

The exact temporary KAC policy was restored to stock using Demo Control on
16 September; a second invocation confirmed an idempotent no-op. No canonical
policy store, manager process or VM restart was involved. The existing Test
still has separately inventoried transient binaries/schema/Provider inputs;
it is not evidence of clean Factory reconstruction.

Before filesystem construction: source contract tests, affected ARM64 target
compilation, uniform manager flags, five native Factory regressions, KAC and
Provider tests, and package QA must pass. Freeze the new image with transfer
SHA once. Fresh Test must reconstruct its native credential, schema and
service input paths without transient proof commands.

Final acceptance remains a clean UI-only create/connect/provision, VDP
V1->V2->V3, service replacements without Safe Stop, real-data backend and
advisory/reset, connectivity recovery, retained-identity restart and Finish.
The separate UI integration gap for first-time authenticated Gateway enrollment
requires an agreed UI flow before that final run. Image build is not UI or E2E
acceptance. Detailed receipts belong to the Solution work packet
`docs/planning/active/work-packets/advisory-readiness-and-demo-reset.md`.
