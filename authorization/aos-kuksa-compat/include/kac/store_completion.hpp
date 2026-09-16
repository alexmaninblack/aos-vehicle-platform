// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0
#pragma once

namespace aos::kac::detail {
// Provider loaders can return false at EOF, which OSSL_STORE_load also maps
// to its generic error flag. A queued OpenSSL error is never accepted here.
constexpr bool CleanKeyStoreEnd(bool eof, unsigned long error, bool has_key) {
  return eof && error == 0 && has_key;
}
}  // namespace aos::kac::detail
