// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"
#include "kac/verifier_prepare.hpp"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>

#ifndef AOS_KAC_NO_VERIFIER_MAIN
namespace {

constexpr const char* kVerifier = "/run/aos-kuksa-verifier/kuksa-jwt-public.pem";
constexpr const char* kTemporary = "/run/aos-kuksa-verifier/.kuksa-jwt-public.pem.tmp";

bool WriteAll(int descriptor, const std::string& value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const ssize_t written = write(descriptor, value.data() + offset, value.size() - offset);
    if (written < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    offset += static_cast<std::size_t>(written);
  }
  return true;
}

}  // namespace

int main() {
  aos::kac::Pkcs11Signer signer;
  if (!signer.Ready()) return 1;
  const std::string probe = "aosedge-kuksa-verifier-self-test/v1";
  const auto signature = signer.Sign(probe);
  const auto public_key = signer.PublicKeyPem();
  if (!signature || !public_key || !signer.Verify(probe, *signature)) return 1;

  if (!aos::kac::RemoveStaleTemporaryVerifier(kTemporary)) return 1;
  const int descriptor = open(kTemporary, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0444);
  if (descriptor < 0) return 1;
  bool ok = WriteAll(descriptor, *public_key) && fsync(descriptor) == 0 &&
            fchmod(descriptor, 0444) == 0;
  if (close(descriptor) != 0) ok = false;
  if (!ok || rename(kTemporary, kVerifier) != 0) {
    unlink(kTemporary);
    return 1;
  }
  return 0;
}
#endif

namespace aos::kac {

bool RemoveStaleTemporaryVerifier(std::string_view path) {
  const std::string temporary(path);
  struct stat status {};
  if (::lstat(temporary.c_str(), &status) != 0) return errno == ENOENT;
  if (!S_ISREG(status.st_mode) || status.st_uid != ::geteuid() || status.st_nlink != 1) {
    return false;
  }
  return ::unlink(temporary.c_str()) == 0;
}

}  // namespace aos::kac
