// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "factory/integration.hpp"

#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <string>
#include <utility>
#include <vector>

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

constexpr const char* kPkcs11Tokens = "/var/lib/softhsm/tokens";

std::pair<std::string, std::string> Split(std::string_view path) {
  const auto separator = path.rfind('/');
  return {std::string(path.substr(0, separator)), std::string(path.substr(separator + 1U))};
}

class FixedRoot final : public CleanupRoot {
 public:
  bool RemoveFile(std::string_view path) override {
    const auto [parent, name] = Split(path);
    const int directory = OpenLookupDirectory(parent);
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
  bool ClearDedicatedPkcs11Tokens() override { return ClearPkcs11Tokens(kPkcs11Tokens); }
  bool SyncProviderDirectory() override {
    return SyncDirectory("/var/lib/aos-kuksa-provider");
  }
  bool SyncTlsDirectory() override { return SyncDirectory("/var/lib/aos-kuksa-tls"); }

 private:
  static int OpenLookupDirectory(const std::string& path) {
#ifdef O_PATH
    // unlinkat/fstatat need only a stable lookup handle.  O_PATH avoids
    // granting the cleanup domain directory-content read access to broad
    // parents such as /var/lib.
    return ::open(path.c_str(), O_PATH | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
#else
    return ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
#endif
  }

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

bool ClearPkcs11Tokens(std::string_view tokens_directory) {
  struct TokenDirectory {
    std::string name;
    int descriptor{-1};
    dev_t device{};
    ino_t inode{};
    std::vector<std::string> files;

    TokenDirectory() = default;
    TokenDirectory(const TokenDirectory&) = delete;
    TokenDirectory& operator=(const TokenDirectory&) = delete;
    TokenDirectory(TokenDirectory&& other) noexcept
        : name(std::move(other.name)),
          descriptor(std::exchange(other.descriptor, -1)),
          device(other.device),
          inode(other.inode),
          files(std::move(other.files)) {}
    TokenDirectory& operator=(TokenDirectory&& other) noexcept {
      if (this == &other) return *this;
      if (descriptor >= 0) ::close(descriptor);
      name = std::move(other.name);
      descriptor = std::exchange(other.descriptor, -1);
      device = other.device;
      inode = other.inode;
      files = std::move(other.files);
      return *this;
    }
    ~TokenDirectory() {
      if (descriptor >= 0) ::close(descriptor);
    }
  };

  const std::string root_path(tokens_directory);
  const int root = ::open(root_path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (root < 0) return false;

  bool valid = true;
  struct stat root_status {};
  if (::fstat(root, &root_status) != 0 || !S_ISDIR(root_status.st_mode) ||
      root_status.st_uid != ::geteuid()) {
    valid = false;
  }

  std::vector<TokenDirectory> tokens;
  std::size_t total_files = 0U;
  const int root_scan_fd = ::dup(root);
  DIR* root_scan = root_scan_fd >= 0 ? ::fdopendir(root_scan_fd) : nullptr;
  if (root_scan == nullptr) {
    if (root_scan_fd >= 0) ::close(root_scan_fd);
    valid = false;
  }

  while (valid) {
    errno = 0;
    dirent* entry = ::readdir(root_scan);
    if (entry == nullptr) {
      if (errno != 0) valid = false;
      break;
    }
    const std::string name(entry->d_name);
    if (name == "." || name == "..") continue;
    if (tokens.size() >= kMaximumPkcs11TokenDirectories) {
      valid = false;
      break;
    }

    const int token_fd = ::openat(root, name.c_str(),
                                  O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (token_fd < 0) {
      valid = false;
      break;
    }
    struct stat token_status {};
    if (::fstat(token_fd, &token_status) != 0 || !S_ISDIR(token_status.st_mode) ||
        token_status.st_uid != ::geteuid()) {
      ::close(token_fd);
      valid = false;
      break;
    }

    TokenDirectory token;
    token.name = name;
    token.descriptor = token_fd;
    token.device = token_status.st_dev;
    token.inode = token_status.st_ino;

    const int token_scan_fd = ::dup(token_fd);
    DIR* token_scan = token_scan_fd >= 0 ? ::fdopendir(token_scan_fd) : nullptr;
    if (token_scan == nullptr) {
      if (token_scan_fd >= 0) ::close(token_scan_fd);
      valid = false;
      break;
    }
    while (valid) {
      errno = 0;
      dirent* file_entry = ::readdir(token_scan);
      if (file_entry == nullptr) {
        if (errno != 0) valid = false;
        break;
      }
      const std::string file_name(file_entry->d_name);
      if (file_name == "." || file_name == "..") continue;
      if (token.files.size() >= kMaximumPkcs11FilesPerToken ||
          total_files >= kMaximumPkcs11FilesTotal) {
        valid = false;
        break;
      }
      struct stat file_status {};
      if (::fstatat(token_fd, file_name.c_str(), &file_status, AT_SYMLINK_NOFOLLOW) != 0 ||
          !S_ISREG(file_status.st_mode) || file_status.st_uid != ::geteuid() ||
          file_status.st_nlink != 1) {
        valid = false;
        break;
      }
      token.files.push_back(file_name);
      ++total_files;
    }
    ::closedir(token_scan);
    if (valid) tokens.push_back(std::move(token));
  }
  if (root_scan != nullptr) ::closedir(root_scan);

  if (valid) {
    for (auto& token : tokens) {
      for (const auto& file : token.files) {
        if (::unlinkat(token.descriptor, file.c_str(), 0) != 0) valid = false;
      }
      if (::fsync(token.descriptor) != 0) valid = false;
      struct stat current {};
      if (::fstatat(root, token.name.c_str(), &current, AT_SYMLINK_NOFOLLOW) != 0 ||
          !S_ISDIR(current.st_mode) || current.st_dev != token.device ||
          current.st_ino != token.inode ||
          ::unlinkat(root, token.name.c_str(), AT_REMOVEDIR) != 0) {
        valid = false;
      }
    }
    if (::fsync(root) != 0) valid = false;
  }
  ::close(root);
  return valid;
}

bool CleanupRuntime(CleanupRoot& root) {
  bool ok = true;
  for (auto path : kFiles) ok = root.RemoveFile(path) && ok;
  ok = root.ClearDedicatedPkcs11Tokens() && ok;
  ok = root.SyncProviderDirectory() && ok;
  ok = root.SyncTlsDirectory() && ok;
  return ok;
}

}  // namespace aos::factory

#ifndef AOS_FACTORY_NO_MAIN
int main() {
  aos::factory::FixedRoot root;
  return aos::factory::CleanupRuntime(root) ? 0 : 1;
}
#endif
