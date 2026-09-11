<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Test service public-input resources

Status: source implementation of accepted
[ADR 0015](../../aosedge-sdv-demo/docs/architecture/decisions/0015-use-native-aos-service-runtime-inputs.md).
Not installed or live-qualified; current Factory image and Test are unchanged.

Demo Control owns [input preparation and sequence](../../aosedge-sdv-demo/docs/architecture/demo-control-service-inputs.md).
The opt-in [resource asset](../meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/resources-demo-services.cfg)
contains only brake-runtime-inputs and tire-runtime-inputs. Each maps its own
/run/aos-demo-service-inputs/<team> directory to
/run/aosedge/platform/service-inputs with bind,ro,nosuid,nodev,noexec.
It is not selected by recipes before the bounded transient proof.
This document supplies the resource JSON's SPDX ownership.

Both packages still request kuksa and kuksa-auth-client. They never request
the peer's input resource or bind a host credential directory.
Public files are metadata.json (five fields, schemaVersion 2) and
kuksa-ca.pem, root-owned 0444, in a root-owned 0755 stable directory.
Only the public /var/lib/aos-kuksa-tls/server.pem is projected.

## Native credential placement

The existing KAC socket bind/group are unchanged. Its per-container token
tmpfs retains rw,nosuid,nodev,noexec,size=65536; mount-root mode is now 1777.
Bootstrap creates an unpredictable private 0700 session and a regular 0400
token under it, owned by its actual UID/GID. Analytics receives only that path,
not AOS_SECRET. Authorization/renewal still use KAC and native IAM permissions;
no fixed UID, chown or SM code change is needed.

The unshipped token-owner SM patch, its private header, recipe wiring and
owner-option tests are retired. The systemd-slot component patch and all
unrelated SM corrections remain intact. Git preserves the retired source.
Do not activate the new mount with the legacy fixed-root bootstrap.

## Native constraints and qualification

Pinned AosCore 9eecb80c4994937b5c8cbe0464970f81e8ad4c2d reads
resourcesConfigFile at initialization, not via hot reload. It copies mounts
without preparing/chowning sources. Bind directories must exist before
instance construction. Configuration activation through Demo Control is not
a binary replacement.

Project inputs before assignment; refresh only after committed VDP
slot/process agreement; restore /run sources before retained assignments
launch on cold start. No daemon, persistent metadata cache or certificate
payload is added here. The exact boot hook is not yet qualified.

The bounded Test proof must establish native non-root execution, real private
mounts, peer isolation, public read-only access, KAC/TLS/subscriptions, renewal
and scoped SELinux results. Host source tests do not establish these facts.
Keep process, Cloud and product readiness separate. No rootfs remount,
broader policy, TOFU, Factory rebuild or Production change is included.

## Source increment evidence — 2026-09-11

Eight resource tests pass, including exact unchanged socket authority and the
absence of token-owner patch staging. Brake and Tire private-session host
tests pass independently. Product wire migration, package version projection
and live service qualification remain separate gates in the Solution plan.
