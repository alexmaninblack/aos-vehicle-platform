<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# AOS-2 CARLA VISS-to-KUKSA provider design

## Scope and lifecycle

The provider is an OEM platform component inside the prototype AosVM. It is
not linked into CARLA and is not an AosCloud-managed service. A production
vehicle replaces this simulation provider with CAN, SOME/IP, DDS, or another
vehicle-network provider while preserving the same KUKSA/VSS contract for
services.

For the prototype, the official AosVM 6.1.0 base image remains immutable. The
versioned provider runtime is installed into the identity-bearing provisioned
overlay under `/var/lib/aos-vehicle-platform`, with two small systemd files in
the overlay root filesystem. This is an integration package, not a rebuilt VM
release. An OEM production release would integrate the same inputs through its
Yocto and FOTA image pipeline.

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

## Authorization and credentials

The pinned AosVM ships a public KUKSA demonstration verification key whose
well-known example tokens have expired. AOS-2 replaces that verifier with a
project-owned RSA public key and issues a short-lived provider token containing
only the seven `provide:<path>` scopes. The signing key remains in an ignored,
mode-0700 host directory. Only the public key and provider token enter the VM.

The token is delivered to the dynamic systemd service through
`LoadCredential`; it is not included in source, a bundle, a command line, or a
log. AOS-5 will replace this temporary issuance mechanism with the Aos-to-KUKSA
Authorization Adapter.

## Runtime and packaging

The official image contains CPython 3.12 but no KUKSA, gRPC, or WebSocket
Python modules. The package therefore creates a private virtual environment
from five exact ARM64 wheels. All versions, upstream source commits, licenses,
and wheel SHA-256 values are recorded. Downloads use `--require-hashes`, and
no compiler or package-manager mutation is needed in the VM.

The systemd unit uses a dynamic user, an empty capability set, no-new-
privileges, private devices and temporary storage, protected kernel and system
paths, and only the network address families required by VISS and KUKSA.

The normal rollback removes the provider unit and KUKSA verifier drop-in, then
restarts KUKSA with the image-default configuration. It preserves the
versioned `/var` runtime and credential evidence. The verified post-provision
AosVM checkpoint is reserved for boot recovery and must never run at the same
time as the active provisioned identity.

## Qualification gates

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

## Qualification result

AOS-2 passed on 2026-08-14 against the official AosVM 6.1.0 Main Node. The
normalized ARM64 provider bundle reproduced byte-for-byte with SHA-256
`4d73c196f8ed8812c0a3912ee9231e4fb2d3ffc9d4ba2f16686777d0c35e5a87`.
All seven contract paths were present in the embedded VSS 5.0 tree, and the
runtime imported successfully from the five hash-locked ARM64 wheels.

The provider negotiated verified TLS and `VISSv3` with the loopback-only CARLA
endpoint, then published 41 consecutive atomic seven-path KUKSA batches at an
observed 20.08 Hz. A separate read-only qualification JWT retrieved the live
values and source timestamps. CARLA loss immediately changed all seven values
to unavailable, with no fabricated zero state, and reconnect backoff remained
bounded.

After a clean AosVM stop and start, KUKSA and the provider were enabled and
active with zero restarts. The root filesystem was read-only, SELinux remained
enforcing without a denial, the provisioned AosCore services were active, and
the cloud Unit remained Online with exactly one primary Main Node. Both
protected lifecycle checkpoints remained valid. The VISS listener was observed
only on macOS `127.0.0.1:6443`; no secret or operational evidence is part of
the repository.
