<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos–KUKSA Credential Broker Boundary

This directory is the source boundary for the thin Credential Broker, KUKSA
trust configuration and provider platform-credential integration owned by the
FOTA-delivered Vehicle Data Platform Component. The target is not implemented
yet.

Upstream Eclipse KUKSA Databroker remains unchanged. A SOTA service declares
its requested `kuksa` paths and `r`, `w`, or `rw` modes in Aos service
metadata. Service Manager registers those permissions with Aos IAM and injects
a per-instance `AOS_SECRET`. Aos IAM owns that identity, secret and permission
lifecycle. The local broker will:

1. call Aos IAM `GetPermissions(secret, "kuksa")`;
2. accept only the running service instance and permissions currently
   registered in IAM;
3. reject an invalid/stale secret, unknown mode, malformed path or permission
   outside the installed VDP contract; or
4. issue a short-lived, path-scoped KUKSA JWT on success without widening or
   silently rewriting the IAM result.

The broker does not maintain a second identity store or per-service OEM policy
database. OEM review and deployment authorization remain lifecycle decisions;
native pre-transfer Cloud admission remains deferred until a supporting
AosCloud release is qualified.

This permission translation is a cybersecurity least-privilege mechanism
inside the QM domain, not a functional-safety case. The VDP outbound allowlist
is defense in depth. The Vehicle Gateway independently enforces the final
QM-channel boundary and denies arbitrary VSS, vehicle-motion and
safety-critical operations.

`r` maps to KUKSA `read`, `w` to `actuate`, and `rw` to both. Functional
services never receive `provide` or `create`; the Vehicle Data Provider uses a
separate short-lived platform credential whose FOTA-component identity binding
remains a design gate. KUKSA trusts only the broker's public verifier.

The broker signs through a per-Unit key protected by the Aos
IAM/certificate-module and PKCS#11 integration. The Factory Image contains only
the non-secret integration seam. The signing key, `AOS_SECRET`, and issued JWTs
must never be committed, baked into an image, placed in FOTA/SOTA artifacts or
command lines, or printed in logs. Existing manually issued prototype tokens
are qualification history, not this implementation.
