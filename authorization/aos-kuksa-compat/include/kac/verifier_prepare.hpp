// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstddef>
#include <string>
#include <string_view>
#include <sys/types.h>

namespace aos::kac {

// Removes only an exact, caller-owned regular temporary verifier with one
// hard link. Missing state is already clean; any other object fails closed.
bool RemoveStaleTemporaryVerifier(std::string_view path);

struct SoftHsmAccessIdentity {
  unsigned matching_tokens{0};
  bool exact_private_key{false};
  std::string serial;
};

enum class SoftHsmAccessResult {
  kAlreadyCorrect,
  kUpdated,
  kRejected,
  kUnavailable
};

// Validates the complete bounded SoftHSM token tree before changing any
// ownership or mode.  Only the one UUID directory mapped from the exact
// PKCS#11 serial is finalized for the dedicated non-root KAC group.
SoftHsmAccessResult FinalizeSoftHsmAccess(std::string_view tokens_root,
                                          const SoftHsmAccessIdentity &identity,
                                          uid_t expected_owner,
                                          gid_t initial_group,
                                          gid_t target_group);

inline constexpr std::size_t kMaximumSoftHsmTokenDirectories = 8U;
inline constexpr std::size_t kMaximumSoftHsmFiles = 128U;

} // namespace aos::kac
