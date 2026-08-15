<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# AOS-2 CARLA VISS-to-KUKSA provider design

## Scope and Lifecycle

The provider is an OEM platform component inside the prototype AosVM. It is
not linked into CARLA and is not an AosCloud-managed service. A production
vehicle replaces this simulation provider with CAN, SOME/IP, DDS, or another
vehicle-network provider while preserving the same KUKSA/VSS contract for
services.

Provider `0.2.0` is an independently signed Aos component managed through the
OEM FOTA lifecycle. The bootstrap rootfs supplies the Service Manager
`systemd-slot-component` runtime, atomic A/B store, systemd supervision,
health boundary, fixed identity, and SELinux policy. The provider bundle owns
only its immutable application payload and ARM64 runtime dependencies.

## Data path

```text
macOS host                                      AosVM Main Node

CARLA -> carla-ego-runtime -> VISS 3.1/TLS -> provider -> KUKSA 0.5.0
                                 host-only       systemd    kuksa.val.v1
                                 10.0.0.1                   127.0.0.1
```

The provider initiates both connections and exposes no listener. QEMU user
networking makes the macOS loopback VISS listener reachable only through the
guest's host gateway. The VISS server remains bound to macOS loopback and is
not exposed to the LAN or Internet.

The prototype VISS certificate is explicitly trusted as a public anchor in the
guest. The TCP destination is `10.0.0.1`, while TLS verifies the certificate's
`127.0.0.1` identity through an explicit server-name setting. This is a
development-host identity, not the production PKI design.

## Contract and failure semantics

The provider subscribes at the VISS profile's minimum 50 ms period and
publishes the seven profile 0.1.1 paths in one authenticated KUKSA v1 batch.
It preserves source timestamps, enforces finite/range checks, and marks an
individual absent or invalid point unavailable.

The source freshness deadline is 250 ms. Once that deadline expires, all
retained values are cleared to KUKSA `NotAvailable` exactly once. Disconnect,
provider startup, provider shutdown, TLS failure, and invalid subscription
state follow the same rule. Reconnection uses bounded exponential backoff and
never substitutes zero.

## Authorization and Credentials

The pinned AosVM ships a public KUKSA demonstration verification key whose
well-known example tokens have expired. AOS-2 replaces that verifier with a
project-owned RSA public key and issues a short-lived provider token containing
only the seven `provide:<path>` scopes. The signing key remains in an ignored,
mode-0700 host directory. Only the public key and provider token enter the VM.

The token is delivered to the fixed `aos-vdp` systemd service through
`LoadCredential`; it is not included in source, a bundle, a command line, or a
log. AOS-5 will replace this temporary issuance mechanism with the
Aos-to-KUKSA Authorization Adapter.

## Runtime and Packaging

The official image contains CPython 3.12 but no KUKSA, gRPC, or WebSocket
Python modules. The component therefore embeds normalized runtime files from
five exact ARM64 wheels. All versions, upstream commits, licenses, and wheel
SHA-256 values are recorded. No compiler, package-manager mutation, virtual
environment, or installer is needed in the Unit.

The systemd unit uses the dedicated non-login `aos-vdp` account, an empty
capability set, `no_new_privs`, private devices and temporary storage,
protected kernel and system paths, and only the network families required by
VISS and KUKSA. SELinux transitions the payload into
`vehicle_data_provider_t` and grants only the reviewed store, credential,
DNS, random-device, KUKSA, and outbound VISS permissions.

The Service Manager prepares a candidate in the inactive slot, verifies the
archive and health contract, atomically switches slots, and records durable
transaction state. A failed candidate reverts to the previous slot. Ordinary
provider update and rollback do not reboot the Node.

## Qualification Gates

AOS-2 is accepted only after the integration repository proves:

1. exact bundle reproduction and ARM64 import compatibility;
2. all seven selected paths exist in the pinned VSS 5.0 tree;
3. VISS TLS and `VISSv3` negotiation from an ordinary guest process;
4. live 20 Hz VISS-to-KUKSA publication with source timestamps;
5. explicit unavailable state after CARLA loss, provider stop, and stale input;
6. bounded reconnect without duplicate batches or fabricated values;
7. provider and KUKSA recovery across a clean VM restart;
8. unchanged Aos Unit identity, cloud connectivity, and immutable base hashes;
9. no VISS listener reachable from the Mac's external interfaces;
10. no private key, token, certificate identity, or raw operational log in Git.

## Qualification Result

AOS-2 first passed on 2026-08-14 against the official AosVM 6.1.0 Main Node.
The later FOTA-managed provider `0.2.0` passed deterministic packaging,
official unsigned validation, 40 ARM64 lifecycle/recovery tests, real install,
live telemetry, source-loss handling, update, downgrade rejection, failed
candidate rollback, SELinux, resource, and secret-exclusion gates. Its
accepted source revision is
`e972d2bd7f14e27646bb5d7c10c7186ecdecfa9f`; its provider layer SHA-256 is
`baf1c29c9264b8f2422dc155540c3b22716bb43d5f80c1cfeb3cc9529f0bf3cb`.
It was signed and independently verified locally but has not been published
or assigned through AosCloud.

All seven contract paths were present in the embedded VSS 5.0 tree, and the
runtime imported successfully from the five hash-locked ARM64 wheels. The lock
uses Protocol Buffers 5.29.6, which includes the fix for CVE-2026-0994.

The provider negotiated verified TLS and `VISSv3` with the loopback-only CARLA
endpoint, then published 41 consecutive atomic seven-path KUKSA batches at an
observed 20.08 Hz. A separate read-only qualification JWT retrieved the live
values and source timestamps. CARLA loss immediately changed all seven values
to unavailable, with no fabricated zero state, and reconnect backoff remained
bounded.

The consolidated runtime delta was then built into local rootfs
`6.1.1-maninblack.11`. With global SELinux Enforcing, the provider read its
private systemd credential, resolved the VISS hostname, recovered across a
KUKSA restart without changing PID, failed closed on an invalid credential,
restarted after `SIGKILL`, and stayed fail-safe on DNS and TLS failures. The
rootfs is frozen as an unsigned local candidate; no `.11` signing, Cloud, or
provisioned-Unit mutation is implied by this qualification.
