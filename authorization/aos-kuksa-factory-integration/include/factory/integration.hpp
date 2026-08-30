// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <string_view>
#include <vector>

namespace aos::factory {

enum class TlsPrepareResult { kReused, kCreated, kRejected, kUnavailable };

TlsPrepareResult PrepareTlsIdentity(std::string_view directory);

class CleanupRoot {
public:
  virtual ~CleanupRoot() = default;
  virtual bool RemoveFile(std::string_view absolute_path) = 0;
  virtual bool ClearDedicatedPkcs11Tokens() = 0;
  virtual bool SyncProviderDirectory() = 0;
  virtual bool SyncTlsDirectory() = 0;
};

bool CleanupRuntime(CleanupRoot &root);
bool ClearPkcs11Tokens(std::string_view tokens_directory);
const std::vector<std::string_view> &CleanupFiles();

inline constexpr std::size_t kMaximumPkcs11TokenDirectories = 8U;
inline constexpr std::size_t kMaximumPkcs11FilesPerToken = 128U;
inline constexpr std::size_t kMaximumPkcs11FilesTotal = 256U;

} // namespace aos::factory
