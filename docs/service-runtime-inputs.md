<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Test service public-input resources

Status: opt-in declaration for the authorized transient Test proof. A bounded
native token-mount ownership correction is now a source candidate (see below).
Neither change is installed, live-qualified, or part of Factory `.31`. No
credential exchange, service identity or SELinux policy change is introduced.

The accepted payload and provenance contract is owned by Demo Control in
[`demo-control-service-inputs.md`](../../aosedge-sdv-demo/docs/architecture/demo-control-service-inputs.md).
Demo Control is the sole projector; this repository does not add a producer,
daemon, lifecycle hook, metadata cache, runtime file or public certificate.

## Resource asset and native interpretation

[`resources-demo-services.cfg`](../meta-aos-vehicle-platform/recipes-aos/aos-servicemanager/files/resources-demo-services.cfg)
is an array of additional native resource declarations, not a replacement
for the current effective resource file. Its SPDX ownership is this document.
It is intentionally absent from recipe `SRC_URI` and install actions until
the transient proof closes the required access boundary.

| Service | Required additional resource | Exact host source directory |
| --- | --- | --- |
| Brake | `brake-runtime-inputs` | `/run/aos-demo-service-inputs/brake` |
| Tire | `tire-runtime-inputs` | `/run/aos-demo-service-inputs/tire` |

Each service receives only its own directory at
`/run/aosedge/platform/service-inputs`, containing exactly `metadata.json`
and `kuksa-ca.pem`. Both still require the existing `kuksa` and
`kuksa-auth-client` resources. Neither package may request the peer's input
resource. The mount is a non-recursive `bind,ro,nosuid,nodev,noexec`; the
shared host parent, source trust directory, keys and credentials are not
mounted. The same destination is deliberate in separate containers, not an
instruction to assign both resources to one instance.

The native schema is `name` plus optional `sharedCount`, `groups`, `mounts`,
`envs`, `hosts`, `devices`. A mount has `destination`, `type`, `source`,
`options`. These declarations add no groups, environment, devices or host
aliases. `sharedCount` is omitted (native parse default `0`); this file does
not claim a new scheduling or exclusive-resource policy.

Pinned AosCore `9eecb80c4994937b5c8cbe0464970f81e8ad4c2d` establishes:

- [`config.cpp`](https://github.com/aosedge/aos_core_cpp/blob/9eecb80c4994937b5c8cbe0464970f81e8ad4c2d/src/sm/config/config.cpp):
  root key `resourcesConfigFile`, default `/etc/aos/resources.cfg`.
- [`resourcemanager.cpp`](https://github.com/aosedge/aos_core_cpp/blob/9eecb80c4994937b5c8cbe0464970f81e8ad4c2d/src/sm/resourcemanager/resourcemanager.cpp):
  `Init` parses the array once; a missing file is not proof of loaded resources.
- [`instance.cpp`](https://github.com/aosedge/aos_core_cpp/blob/9eecb80c4994937b5c8cbe0464970f81e8ad4c2d/src/sm/launcher/runtimes/container/instance.cpp):
  native instance UID/GID are used; `AddResources` copies the mount without
  populating, chowning or relabeling its source.
- [`runtimeconfig.cpp`](https://github.com/aosedge/aos_core_cpp/blob/9eecb80c4994937b5c8cbe0464970f81e8ad4c2d/src/sm/launcher/runtimes/container/runtimeconfig.cpp):
  `AddMount` replaces an earlier mount with the same destination. Combining
  both input resources is therefore not a way to expose two safe namespaces.
- [`filesystem.cpp`](https://github.com/aosedge/aos_core_cpp/blob/9eecb80c4994937b5c8cbe0464970f81e8ad4c2d/src/sm/launcher/runtimes/container/filesystem.cpp):
  `CreateMountPoints` tests whether the bind source is a directory; input
  directories must already exist before native instance construction.

## Projection and identity requirements

The root-owned projector prepares directories with mode `0755` and regular
public files with mode `0444`, ownership `root:root`. It rejects symlinks,
unexpected entries and unowned existing paths. The service keeps the native
instance UID/GID; do not introduce a fixed service UID or grant write access
to this public-input directory. Public readability is not KUKSA authority.

The seven metadata fields and their authoritative sources remain exactly the
Demo Control contract. In particular, `serviceArtifactSha256` is the signed
ARM64 OCI manifest digest; the VDP contract pair is from the verified committed
active capability manifest, not the capability-manifest file hash or selected
functional profile. The public trust source is only
`/var/lib/aos-kuksa-tls/server.pem`; no sibling private key is copied.

Prepare both files before assignment. Replace file entries atomically inside
the stable bound directory; replacing the host directory would leave an
existing bind attached to the old inode. Refresh VDP provenance only after
committed slot/process agreement. A service update must reconcile the actual
native version and manifest digest with the projected candidate tuple.

Brake uses its existing arguments:

```text
--metadata-file /run/aosedge/platform/service-inputs/metadata.json
--ca-file /run/aosedge/platform/service-inputs/kuksa-ca.pem
```

The metadata has no bearer credentials. Native `AOS_SECRET` and the existing
KAC request socket/token-renewal boundary remain separate and unchanged.
The existing `kuksa-auth-client` token tmpfs is mode `0700`; its effective
ownership must match the actual bootstrap UID. The resource declaration alone
does not prove that condition or authorize a wider mode. A mismatch is a
specific integration blocker, not a reason to run the service as root.

## Labels and transient proof

Resource JSON cannot set SELinux labels. The pinned policy's
[`files.fc`](https://github.com/aosedge/refpolicy/blob/c8be82c7e62f69cb6530de8cc1da3beb389a6681/policy/modules/kernel/files.fc)
labels `/run` as `var_run_t` but marks `/run/.*` as `<<none>>`. The new input
paths have no platform-owned explicit file context. Therefore neither a
particular descendant label nor access by the native service domain is
declared proven; creation transitions and effective installed policy matter.
No new `.fc`, allow rule, `chcon` shortcut or credential-store access is added.

The integration owner executes the following bounded proof through Demo
Control only, without rebuilding `.31`:

1. Resolve the exact Test identity, initialized Test role, signed candidate
   and committed VDP contract. Project that service's two public files.
2. Read the complete effective SM configuration and its effective resource
   file. Append only the requested declaration into a temporary `/run` copy;
   preserve every existing entry. Reject conflicting resource names or a
   package requesting both inputs. Point a temporary copy of SM configuration
   at that file via `resourcesConfigFile`. Bind only the temporary config
   read-only into the exact Test SM unit and restart once, retaining the
   existing binary, credentials and component runtime configuration.
3. Observe real process UID/GID, source ownership/modes/labels and effective
   OCI mounts. Verify public-file reads under the deployed service identity,
   no input write or peer input access, KAC socket/token ownership, actual
   renewal, TLS verification for `Server`, and subscription. Capture only
   fixed status/digest facts, never raw secrets, metadata or trust contents.
4. Reconcile native instance version/manifest digest. Prove an atomic public
   input refresh is seen by the real consumer and fresh scoped AVCs are empty.
   Process Running alone does not establish telemetry or backend readiness.
5. Retain the exact temporary state explicitly or restore the previous SM
   configuration with services safely stopped. `/run` inputs/overrides do not
   survive reboot; Demo Control must re-project them before service startup
   during the next authorized activation. No hidden boot producer is added.

Only after this proof may the qualified declarations be integrated into the
single subsequent clean Factory image. If exact identity/label/mount evidence
fails, retain the failure and report that narrow boundary; do not broaden
permissions or manufacture a certificate to pass.

## Authorized token-owner correction — 11 September 2026

The user authorized correction of the token-directory ownership boundary.
`0002-bind-kuksa-token-tmpfs-to-instance-owner.patch` changes only the native
container launcher's handling of the exact `kuksa-auth-client` resource mount
at `/run/aosedge/secrets/kuksa`. It copies the mount per instance and adds
`uid`/`gid` from native `mInstanceInfo`, before writing OCI runtime configuration.
The shared resource declaration is never mutated. There are no fixed UID/GID,
root service, ownership placeholders, directory-creation daemon or host chmod.

The source/type must both be `tmpfs`; the original six mount options must be
exactly the existing owner-only, 64-KiB policy. Conflicting owner options,
duplicate/missing flags, another filesystem, root or invalid ownership fail
before launch. Other resources and the KAC socket bind keep native behavior.
The recipe stages the small pure option function beside the native instance
source; a later normal package build includes this candidate.

The actual option function compiles with C++17 warnings-as-errors. Tests cover
distinct dynamic UID/GID pairs, repeat construction without shared-state
mutation, order-independent policy matching and invalid/foreign mounts. The
patch applies to the pinned `9eecb80...` instance source. Nine focused tests and
the repository quality gate pass. These are source-equivalent tests, **not**
a complete native SM compile, Linux mount/SELinux proof or running service.
Those gates remain required before the candidate is considered qualified or
used in the next Factory image. No Builder, Test SM or VM was restarted.
