<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# KUKSA Platform Configuration

This directory is reserved for non-secret, vehicle-program KUKSA
configuration. The current prototype needs no additional repository-owned
configuration: the OEM rootfs integration owns the fixed Databroker endpoint
and runtime boundary.

Private keys, certificates, service tokens, provisioned identities, and
vehicle-specific credentials never belong here.
