<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Current-Release KUKSA Authorization Compatibility Boundary

This is the accepted future source boundary for the separately packaged,
removable `aos-kuksa-auth-compat` Factory/System component. No executable
implementation exists here yet.

The helper is outside the Vehicle Data Platform FOTA payload, both functional
SOTA services, upstream Eclipse KUKSA, analytics logic and the subsequent
Service-to-KUKSA data path. It runs as dedicated `aos-kac:aos-kac`, owns one
private Unix socket and obtains current authority only by calling native Aos
IAM `GetPermissions` for the implicit fixed resource `kuksa` on every issue or
renewal.

The shared Factory Image configuration enables `enablePermissionsHandler: true`
independently of provisioning. The unprovisioned image contains only
non-secret package/configuration and signer/verifier-preparation seams. After
provisioning, one Unit-specific protected `kuksa-jwt` key is created; private
bytes never leave PKCS#11, and only the verified public key is reconstructed in
volatile runtime state for unmodified KUKSA.

The accepted Service mapping is exact and non-widening:

- IAM `r` becomes KUKSA `read:<exact-path>`;
- IAM `rw` becomes KUKSA `actuate:<exact-path>` because the pinned KUKSA
  actuation scope includes read; and
- IAM `w`, unknown modes, wildcards, malformed paths, partial trimming,
  `provide` and `create` reject the complete issuance.

Issued JWTs use the frozen `RS256` profile, 300-second lifetime, renewal after
180 seconds and bounded recovery before expiry. The Service bootstrap keeps
`AOS_SECRET` out of the analytics process and atomically writes only the
short-lived JWT to its private volatile token location. The helper persists no
Service identity, permission database, JWT or Cloud state and adds no Cloud
dependency to offline-local renewal.

The trusted OEM Provider is a separate Platform integration. It receives no
authority, credential or lifecycle from this helper. Its exact KUKSA
connection configuration and selected-Unit VISS mTLS profile remain explicit
implementation parameters that must be frozen before Provider/VDP code begins.
