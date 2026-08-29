// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

int main() {
  aos::kac::GrpcIamClient iam;
  aos::kac::Pkcs11Signer signer;
  aos::kac::SystemClock clock;
  aos::kac::Core core(iam, signer, clock);
  return aos::kac::RunServer(core);
}
