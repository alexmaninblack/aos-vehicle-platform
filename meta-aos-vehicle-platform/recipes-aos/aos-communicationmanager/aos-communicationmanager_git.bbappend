# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Keep the pinned upstream CM version. Backport only the shared gRPC write lock.
SRC_URI += "file://0001-serialize-sm-stream-writes.patch"
