<!-- SPDX-FileCopyrightText: 2026 maninblack -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Aos Vehicle Platform Yocto Layer

This layer contains the OEM integration delta for the R6.1 vehicle-data
provider component runtime. It is applied after the unchanged AosVM 6.1.0
`qemuarm64` Main Node baseline has built and booted successfully.

R6.1-2 installs only the bootstrap runtime boundary, fixed launcher profile,
persistent empty-store layout, health probe, and SELinux policy. Atomic
component prepare, activation, rollback, and recovery remain R6.1-3 work.
