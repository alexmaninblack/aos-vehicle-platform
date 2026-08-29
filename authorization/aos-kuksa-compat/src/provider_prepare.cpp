// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"
#include "kac/provider.hpp"

#include <ctime>

namespace {

class Adapter final : public aos::kac::provider::Signer {
 public:
  bool Ready() const override { return signer_.Ready(); }
  std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) override {
    return signer_.Sign(input);
  }
  bool Verify(std::string_view input,
              const std::vector<std::uint8_t>& signature) const override {
    return signer_.Verify(input, signature);
  }

 private:
  aos::kac::Pkcs11Signer signer_;
};

}  // namespace

int main() {
  const std::time_t now = std::time(nullptr);
  if (now < 0) return 1;
  Adapter signer;
  aos::kac::provider::FixedStore store;
  const auto result = aos::kac::provider::Prepare(now, signer, store);
  return result == aos::kac::provider::Result::kReused ||
                 result == aos::kac::provider::Result::kCreated
             ? 0
             : 1;
}
