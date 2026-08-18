<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos–KUKSA Credential Broker and OEM Access Policy

This directory is the source boundary for the Credential Broker and OEM KUKSA
access policy owned by the FOTA-delivered Vehicle Data Platform Component. The
target is not implemented yet.

Upstream Eclipse KUKSA Databroker remains unchanged. A SOTA service declares
its requested `kuksa` paths and `r`, `w`, or `rw` modes in Aos service
metadata. Service Manager registers those permissions and injects a
per-instance `AOS_SECRET`. The local broker will:

1. call Aos IAM `GetPermissions(secret, "kuksa")`;
2. identify the running service instance and its complete requested path/mode
   set;
3. compare that request with the FOTA-managed OEM allowlist for the service;
4. reject the complete request on any mismatch; or
5. issue a short-lived, path-scoped KUKSA JWT on success.

`r` maps to KUKSA `read`, `w` to `actuate`, and `rw` to both. Functional
services never receive `provide` or `create`; the Vehicle Data Provider uses a
distinct platform credential. KUKSA trusts only the broker's public verifier.

The signing key, `AOS_SECRET`, and issued JWTs must never be committed, placed
in FOTA/SOTA artifacts or command lines, or printed in logs. Existing manually
issued prototype tokens are qualification history, not this implementation.
