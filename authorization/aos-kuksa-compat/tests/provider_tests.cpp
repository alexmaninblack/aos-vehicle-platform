// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/provider.hpp"

#include <cassert>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace {

class FakeSigner final : public aos::kac::provider::Signer {
 public:
  bool ready{true};
  bool Ready() const override { return ready; }
  std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) override {
    last.assign(input);
    return std::vector<std::uint8_t>(256U, 0x5aU);
  }
  bool Verify(std::string_view input,
              const std::vector<std::uint8_t>& signature) const override {
    return input == last && signature == std::vector<std::uint8_t>(256U, 0x5aU);
  }
  mutable std::string last;
};

class FakeStore final : public aos::kac::provider::Store {
 public:
  std::optional<aos::kac::provider::ExistingToken> Read() override { return token; }
  bool ReplaceAtomically(std::string_view bytes) override {
    ++writes;
    if (!write_ok) return false;
    token = {true, true, true, 0600U, std::string(bytes)};
    return true;
  }
  aos::kac::provider::ExistingToken token{};
  bool write_ok{true};
  unsigned writes{0};
};

void TestClaims() {
  FakeSigner signer;
  auto token = aos::kac::provider::CreateToken(1700000000, signer);
  assert(token);
  assert(aos::kac::provider::ValidateToken(*token, 1700000000, signer));
  assert(!aos::kac::provider::ValidateToken(*token, 1700604800, signer));
  assert(aos::kac::provider::Payload(1700000000).find("\"exp\":1700604800") !=
         std::string::npos);
  assert(aos::kac::provider::kScope.find("Row2") != std::string_view::npos);
  assert(aos::kac::provider::kScope.find("create:") == std::string_view::npos);
  assert(aos::kac::provider::kScope.find("actuate:") == std::string_view::npos);
  assert(aos::kac::provider::kScope.find('*') == std::string_view::npos);
}

void TestLifecycle() {
  FakeSigner signer;
  FakeStore store;
  assert(aos::kac::provider::Prepare(1700000000, signer, store) ==
         aos::kac::provider::Result::kCreated);
  assert(store.writes == 1U);
  assert(aos::kac::provider::Prepare(1700000001, signer, store) ==
         aos::kac::provider::Result::kReused);
  assert(store.writes == 1U);
  assert(aos::kac::provider::Prepare(1700604800, signer, store) ==
         aos::kac::provider::Result::kCreated);
  assert(store.writes == 2U);
  store.token.mode = 0644U;
  assert(aos::kac::provider::Prepare(1700604801, signer, store) ==
         aos::kac::provider::Result::kRejected);
}

void TestNegatives() {
  FakeSigner signer;
  auto token = aos::kac::provider::CreateToken(1700000000, signer);
  assert(token);
  std::string changed = *token;
  changed[0] = changed[0] == 'a' ? 'b' : 'a';
  assert(!aos::kac::provider::ValidateToken(changed, 1700000000, signer));
  assert(!aos::kac::provider::ValidateToken(*token + ".extra", 1700000000, signer));
  FakeStore store;
  store.write_ok = false;
  assert(aos::kac::provider::Prepare(1700000000, signer, store) ==
         aos::kac::provider::Result::kUnavailable);
  signer.ready = false;
  assert(aos::kac::provider::Prepare(1700000000, signer, store) ==
         aos::kac::provider::Result::kUnavailable);
}

}  // namespace

int main() {
  TestClaims();
  TestLifecycle();
  TestNegatives();
  return 0;
}
