// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "factory/integration.hpp"

#include <cassert>
#include <optional>
#include <string>
#include <vector>

namespace {

class Pins final : public aos::factory::PinStore {
 public:
  std::optional<aos::factory::PinState> Inspect() override { return state; }
  std::optional<std::string> Generate() override {
    ++generated;
    return generated == 1 ? "user-fixed-fake" : "so-fixed-fake";
  }
  bool Publish(std::string_view pin) override { published.assign(pin); return publish_ok; }
  aos::factory::PinState state{};
  unsigned generated{0};
  bool publish_ok{true};
  std::string published;
};

class Tokens final : public aos::factory::TokenStore {
 public:
  std::optional<aos::factory::TokenState> Inspect(
      std::optional<std::string_view>) override { return state; }
  bool Initialize(std::string_view user, std::string_view so) override {
    initialized = std::string(user) + ":" + std::string(so);
    return initialize_ok;
  }
  aos::factory::TokenState state{};
  bool initialize_ok{true};
  std::string initialized;
};

class Cleanup final : public aos::factory::CleanupRoot {
 public:
  bool RemoveFile(std::string_view path) override { files.emplace_back(path); return ok; }
  bool RemoveEmptyDirectory(std::string_view path) override { directories.emplace_back(path); return ok; }
  bool SyncProviderDirectory() override { ++syncs; return ok; }
  bool ok{true}; unsigned syncs{0};
  std::vector<std::string> files; std::vector<std::string> directories;
};

void TestInit() {
  Pins pins; Tokens tokens;
  assert(aos::factory::InitializeToken(pins, tokens) == aos::factory::InitResult::kCreated);
  assert(pins.published == "user-fixed-fake");
  pins.state = {true, true, true, 0600U, "user-fixed-fake"};
  tokens.state = {1U, true};
  assert(aos::factory::InitializeToken(pins, tokens) == aos::factory::InitResult::kValidated);
  tokens.state = {2U, true};
  assert(aos::factory::InitializeToken(pins, tokens) == aos::factory::InitResult::kRejected);
  tokens.state = {1U, false};
  assert(aos::factory::InitializeToken(pins, tokens) == aos::factory::InitResult::kRejected);
  pins.state.mode = 0644U;
  assert(aos::factory::InitializeToken(pins, tokens) == aos::factory::InitResult::kRejected);
}

void TestCleanup() {
  Cleanup cleanup;
  assert(aos::factory::CleanupRuntime(cleanup));
  assert(cleanup.files.size() == 4U);
  assert(cleanup.directories.size() == 2U);
  assert(cleanup.syncs == 1U);
  assert(cleanup.files[0] == "/var/lib/aos-kuksa-provider/kuksa-token");
  assert(cleanup.files[1] == "/var/lib/aos-kuksa-provider/.kuksa-token.tmp");
  for (const auto& path : cleanup.files) {
    assert(path.find(".kuksa-jwt-pin") == std::string::npos);
    assert(path.find("softhsm") == std::string::npos);
    assert(path.find("systemd-slot-component") == std::string::npos);
  }
}

}  // namespace

int main() {
  TestInit();
  TestCleanup();
  return 0;
}
