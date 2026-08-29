// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/verifier_prepare.hpp"

#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include <unistd.h>

namespace {

class TemporaryDirectory final {
 public:
  TemporaryDirectory() {
    std::string pattern = "/tmp/aos-kuksa-verifier-test-XXXXXX";
    char* result = ::mkdtemp(pattern.data());
    assert(result != nullptr);
    path_ = result;
  }
  ~TemporaryDirectory() { std::filesystem::remove_all(path_); }
  const std::filesystem::path& path() const { return path_; }

 private:
  std::filesystem::path path_;
};

void WriteFile(const std::filesystem::path& path) {
  std::ofstream output(path, std::ios::binary);
  assert(output.good());
  output << "interrupted";
  output.close();
  assert(output.good());
}

}  // namespace

int main() {
  TemporaryDirectory fixture;
  const auto temporary = fixture.path() / ".kuksa-jwt-public.pem.tmp";
  assert(aos::kac::RemoveStaleTemporaryVerifier(temporary.string()));

  WriteFile(temporary);
  assert(aos::kac::RemoveStaleTemporaryVerifier(temporary.string()));
  assert(!std::filesystem::exists(temporary));

  const auto target = fixture.path() / "target";
  WriteFile(target);
  assert(::symlink("target", temporary.c_str()) == 0);
  assert(!aos::kac::RemoveStaleTemporaryVerifier(temporary.string()));
  assert(std::filesystem::exists(target));
  std::filesystem::remove(temporary);

  std::filesystem::create_directory(temporary);
  assert(!aos::kac::RemoveStaleTemporaryVerifier(temporary.string()));
  std::filesystem::remove(temporary);

  WriteFile(temporary);
  const auto hardlink = fixture.path() / "hardlink";
  std::filesystem::create_hard_link(temporary, hardlink);
  assert(!aos::kac::RemoveStaleTemporaryVerifier(temporary.string()));
  assert(std::filesystem::exists(temporary));
  return 0;
}
