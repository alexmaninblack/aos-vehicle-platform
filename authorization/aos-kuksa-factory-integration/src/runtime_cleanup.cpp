// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "factory/integration.hpp"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <string>

namespace aos::factory {
namespace {

const std::vector<std::string_view> kFiles{
    "/var/lib/aos-kuksa-provider/kuksa-token",
    "/var/lib/aos-kuksa-provider/.kuksa-token.tmp",
    "/var/lib/aos-kuksa-tls/server.key",
    "/var/lib/aos-kuksa-tls/server.pem",
    "/var/lib/aos-kuksa-tls/.server.key.tmp",
    "/var/lib/aos-kuksa-tls/.server.pem.tmp",
    "/run/aos-kuksa-verifier/kuksa-jwt-public.pem",
    "/run/aos-kuksa-auth-compat/request.sock"};
const std::vector<std::string_view> kDirectories{
    "/run/aos-kuksa-verifier", "/run/aos-kuksa-auth-compat", "/var/lib/aos-kuksa-tls"};

std::pair<std::string, std::string> Split(std::string_view path) {
  const auto separator = path.rfind('/');
  return {std::string(path.substr(0, separator)), std::string(path.substr(separator + 1U))};
}

class FixedRoot final : public CleanupRoot {
 public:
  bool RemoveFile(std::string_view path) override {
    const auto [parent, name] = Split(path);
    const int directory = ::open(parent.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0) return errno == ENOENT;
    struct stat status {};
    bool ok = true;
    if (::fstatat(directory, name.c_str(), &status, AT_SYMLINK_NOFOLLOW) != 0) {
      ok = errno == ENOENT;
    } else if (!S_ISREG(status.st_mode) && !S_ISSOCK(status.st_mode)) {
      ok = false;
    } else {
      ok = ::unlinkat(directory, name.c_str(), 0) == 0;
    }
    ::close(directory);
    return ok;
  }
  bool RemoveEmptyDirectory(std::string_view path) override {
    const auto [parent, name] = Split(path);
    const int directory = ::open(parent.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0) return errno == ENOENT;
    const bool ok = ::unlinkat(directory, name.c_str(), AT_REMOVEDIR) == 0 || errno == ENOENT;
    ::close(directory);
    return ok;
  }
  bool SyncProviderDirectory() override {
    return SyncDirectory("/var/lib/aos-kuksa-provider");
  }
  bool SyncTlsDirectory() override { return SyncDirectory("/var/lib/aos-kuksa-tls"); }

 private:
  static bool SyncDirectory(const char* path) {
    const int directory = ::open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (directory < 0) return errno == ENOENT;
    const bool ok = ::fsync(directory) == 0;
    ::close(directory);
    return ok;
  }
};

}  // namespace

const std::vector<std::string_view>& CleanupFiles() { return kFiles; }
const std::vector<std::string_view>& CleanupDirectories() { return kDirectories; }

bool CleanupRuntime(CleanupRoot& root) {
  bool ok = true;
  for (auto path : kFiles) ok = root.RemoveFile(path) && ok;
  ok = root.SyncProviderDirectory() && ok;
  ok = root.SyncTlsDirectory() && ok;
  for (auto path : kDirectories) ok = root.RemoveEmptyDirectory(path) && ok;
  return ok;
}

}  // namespace aos::factory

#ifndef AOS_FACTORY_NO_MAIN
int main() {
  aos::factory::FixedRoot root;
  return aos::factory::CleanupRuntime(root) ? 0 : 1;
}
#endif
