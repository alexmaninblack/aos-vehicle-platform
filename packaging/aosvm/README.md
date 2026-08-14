<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# AosVM Platform Packaging

This directory contains the AOS-2 system-level development package:

- `build-provider-bundle` downloads an exact, hash-verified CPython 3.12 ARM64
  wheel set and creates a normalized, reproducible, ignored provider archive
  without macOS AppleDouble metadata;
- `install-provider` installs a versioned runtime under `/var`, installs the
  two required systemd files into the persistent overlay, and returns `/` to
  read-only mode;
- `uninstall-provider` removes only those two systemd files, restores the
  image-default KUKSA verifier, and deliberately preserves `/var` evidence;
- the provider systemd unit uses a dynamic user, systemd credentials, an empty
  capability set, and a read-only system view;
- the KUKSA drop-in replaces the public demo JWT key with a project-owned
  public verification key. The corresponding private signing key remains
  outside the repository and outside the VM.

The installer does not rebuild or modify the downloaded AosVM base image. It
changes only the active provisioned overlay. In a production vehicle program,
the same files and policy would be produced by the OEM Yocto/FOTA image build
rather than installed over SSH.

Generated bundles include the dependency inventory and third-party notice.
They never embed a KUKSA token, private signing key, VISS private key,
provisioned Aos identity, or account credential.

Before installation, verify the protected post-provision AosVM checkpoint.
The uninstall script is the normal rollback. The checkpoint is the recovery
path if the guest cannot boot; a restored identity must never run concurrently
with the active overlay.
