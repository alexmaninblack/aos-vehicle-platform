// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"
#include "kac/provider.hpp"

#include <cstdio>
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
  aos::kac::provider::Result result = aos::kac::provider::Result::kUnavailable;
  {
    Adapter signer;
    {
      aos::kac::provider::FixedStore store;
      std::fputs("provider-prepare: stage=prepare-start\n", stderr);
      result = aos::kac::provider::Prepare(now, signer, store);
      std::fprintf(stderr, "provider-prepare: stage=prepare-complete result=%u\n",
                   static_cast<unsigned>(result));
    }
    std::fputs("provider-prepare: stage=store-destroyed\n", stderr);
  }
  std::fputs("provider-prepare: stage=signer-destroyed\n", stderr);
  return result == aos::kac::provider::Result::kReused ||
                 result == aos::kac::provider::Result::kCreated
             ? 0
             : 1;
}
