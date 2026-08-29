// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aos::factory {

struct PinState {
  bool exists{false};
  bool regular{false};
  bool root_owned{false};
  unsigned mode{0};
  std::string value;
};

struct TokenState {
  unsigned matching_tokens{0};
  bool user_pin_valid{false};
};

class PinStore {
 public:
  virtual ~PinStore() = default;
  virtual std::optional<PinState> Inspect() = 0;
  virtual std::optional<std::string> Generate() = 0;
  virtual bool Publish(std::string_view pin) = 0;
};

class TokenStore {
 public:
  virtual ~TokenStore() = default;
  virtual std::optional<TokenState> Inspect(std::optional<std::string_view> pin) = 0;
  virtual bool Initialize(std::string_view user_pin, std::string_view ephemeral_so_pin) = 0;
};

enum class InitResult { kValidated, kCreated, kRejected, kUnavailable };

InitResult InitializeToken(PinStore& pins, TokenStore& tokens);

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

bool CleanupRuntime(CleanupRoot& root);
bool ClearPkcs11Tokens(std::string_view tokens_directory);
const std::vector<std::string_view>& CleanupFiles();

inline constexpr std::size_t kMaximumPkcs11TokenDirectories = 8U;
inline constexpr std::size_t kMaximumPkcs11FilesPerToken = 128U;
inline constexpr std::size_t kMaximumPkcs11FilesTotal = 256U;

}  // namespace aos::factory
