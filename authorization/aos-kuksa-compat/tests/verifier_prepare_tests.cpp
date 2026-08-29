// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/verifier_prepare.hpp"

#ifdef NDEBUG
#undef NDEBUG
#endif
#include <array>
#include <cassert>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iterator>
#include <map>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace {

class TemporaryDirectory final {
public:
  TemporaryDirectory() {
    std::string pattern = "/tmp/aos-kuksa-verifier-test-XXXXXX";
    char *result = ::mkdtemp(pattern.data());
    assert(result != nullptr);
    path_ = result;
  }
  ~TemporaryDirectory() { std::filesystem::remove_all(path_); }
  const std::filesystem::path &path() const { return path_; }

private:
  std::filesystem::path path_;
};

void WriteFile(const std::filesystem::path &path) {
  std::ofstream output(path, std::ios::binary);
  assert(output.good());
  output << "interrupted";
  output.close();
  assert(output.good());
  assert(::chmod(path.c_str(), 0600) == 0);
}

constexpr const char *kTokenUuid = "11111111-2222-3333-0123-456789abcdef";
constexpr const char *kSecondTokenUuid = "99999999-aaaa-bbbb-0123-456789abcdef";
constexpr const char *kObjectUuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
constexpr const char *kSerial = "0123456789abcdef";

std::filesystem::path
CreateTokenTree(const std::filesystem::path &root,
                std::string_view token_uuid = kTokenUuid) {
  const auto token = root / token_uuid;
  std::filesystem::create_directory(token);
  assert(::chmod(token.c_str(), 0700) == 0);
  for (const auto *name : {"generation", "token.object", "token.lock"}) {
    WriteFile(token / name);
  }
  WriteFile(token / (std::string(kObjectUuid) + ".object"));
  WriteFile(token / (std::string(kObjectUuid) + ".lock"));
  return token;
}

aos::kac::SoftHsmAccessIdentity Identity(unsigned matches = 1U, bool key = true,
                                         std::string serial = kSerial) {
  return {matches, key, std::move(serial)};
}

std::string Snapshot(const std::filesystem::path &root) {
  std::map<std::string, std::string> entries;
  for (const auto &entry :
       std::filesystem::recursive_directory_iterator(root)) {
    struct stat status{};
    assert(::lstat(entry.path().c_str(), &status) == 0);
    std::ostringstream value;
    value << std::oct << (status.st_mode & 07777U) << ':' << std::dec
          << status.st_uid << ':' << status.st_gid << ':' << status.st_nlink
          << ':' << status.st_size;
    if (S_ISREG(status.st_mode)) {
      std::ifstream input(entry.path(), std::ios::binary);
      value << ':' << std::string(std::istreambuf_iterator<char>(input), {});
    } else if (S_ISLNK(status.st_mode)) {
      std::array<char, 256> target{};
      const ssize_t size =
          ::readlink(entry.path().c_str(), target.data(), target.size());
      assert(size >= 0);
      value << ':'
            << std::string(target.data(), static_cast<std::size_t>(size));
    }
    entries.emplace(std::filesystem::relative(entry.path(), root).string(),
                    value.str());
  }
  std::ostringstream result;
  for (const auto &[name, value] : entries)
    result << name << '=' << value << '\n';
  return result.str();
}

void AssertRejectedWithoutMutation(
    const std::filesystem::path &root,
    const aos::kac::SoftHsmAccessIdentity &identity,
    uid_t expected_owner = ::geteuid(),
    gid_t initial_group = static_cast<gid_t>(-1),
    gid_t target_group = static_cast<gid_t>(-1)) {
  if (initial_group == static_cast<gid_t>(-1)) {
    struct stat status{};
    if (::stat((root / kTokenUuid).c_str(), &status) == 0)
      initial_group = status.st_gid;
    else
      initial_group = ::getegid();
  }
  if (target_group == static_cast<gid_t>(-1))
    target_group = initial_group;
  const std::string before = Snapshot(root);
  const auto result = aos::kac::FinalizeSoftHsmAccess(
      root.string(), identity, expected_owner, initial_group, target_group);
  assert(result == aos::kac::SoftHsmAccessResult::kRejected ||
         result == aos::kac::SoftHsmAccessResult::kUnavailable);
  assert(Snapshot(root) == before);
}

void TestSoftHsmAccessSuccessAndIdempotence() {
  TemporaryDirectory fixture;
  const auto root = fixture.path() / "tokens";
  std::filesystem::create_directory(root);
  const auto token = CreateTokenTree(root);
  struct stat status{};
  assert(::stat(token.c_str(), &status) == 0);
  const gid_t token_group = status.st_gid;
  const gid_t target_group = ::getegid();
  const auto result = aos::kac::FinalizeSoftHsmAccess(
      root.string(), Identity(), ::geteuid(), token_group, target_group);
  assert(result == aos::kac::SoftHsmAccessResult::kUpdated);
  assert(::stat(token.c_str(), &status) == 0);
#ifdef __APPLE__
  assert((status.st_mode & 07777U) == 0750U);
#else
  assert((status.st_mode & 07777U) == 02750U);
#endif
  for (const auto *name : {"generation", "token.object", "token.lock"}) {
    assert(::stat((token / name).c_str(), &status) == 0);
    assert((status.st_mode & 07777U) == 0660U);
  }
  for (const auto &suffix : {".object", ".lock"}) {
    assert(::stat((token / (std::string(kObjectUuid) + suffix)).c_str(),
                  &status) == 0);
    assert((status.st_mode & 07777U) == 0640U);
  }
  assert(aos::kac::FinalizeSoftHsmAccess(root.string(), Identity(), ::geteuid(),
                                         token_group, target_group) ==
         aos::kac::SoftHsmAccessResult::kAlreadyCorrect);
}

void TestSoftHsmAccessRejectsIdentityAndMapping() {
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    CreateTokenTree(root);
    AssertRejectedWithoutMutation(root, Identity(0U));
    AssertRejectedWithoutMutation(root, Identity(2U));
    AssertRejectedWithoutMutation(root, Identity(1U, false));
    AssertRejectedWithoutMutation(root, Identity(1U, true, "fedcba9876543210"));
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    CreateTokenTree(root);
    CreateTokenTree(root, kSecondTokenUuid);
    AssertRejectedWithoutMutation(root, Identity());
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    std::filesystem::create_directory(root / "not-a-canonical-uuid");
    AssertRejectedWithoutMutation(root, Identity());
  }
}

void TestSoftHsmAccessRejectsHostileTrees() {
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    const auto token = CreateTokenTree(root);
    assert(::symlink("generation", (token / "link").c_str()) == 0);
    AssertRejectedWithoutMutation(root, Identity());
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    const auto token = CreateTokenTree(root);
    assert(::mkfifo((token / "special").c_str(), 0600) == 0);
    AssertRejectedWithoutMutation(root, Identity());
  }
#ifndef __APPLE__
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    CreateTokenTree(root);
    const int socket_descriptor = ::socket(AF_UNIX, SOCK_STREAM, 0);
    assert(socket_descriptor >= 0);
    sockaddr_un address{};
    address.sun_family = AF_UNIX;
    const std::string path = (root / "socket").string();
    assert(path.size() < sizeof(address.sun_path));
    std::memcpy(address.sun_path, path.c_str(), path.size() + 1U);
    const socklen_t address_size = static_cast<socklen_t>(
        offsetof(sockaddr_un, sun_path) + path.size() + 1U);
#ifdef __APPLE__
    address.sun_len = static_cast<unsigned char>(address_size);
#endif
    assert(::bind(socket_descriptor, reinterpret_cast<sockaddr *>(&address),
                  address_size) == 0);
    ::close(socket_descriptor);
    AssertRejectedWithoutMutation(root, Identity());
  }
#endif
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    const auto token = CreateTokenTree(root);
    std::filesystem::create_directory(token / "nested");
    AssertRejectedWithoutMutation(root, Identity());
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    const auto token = CreateTokenTree(root);
    std::filesystem::create_hard_link(
        token / (std::string(kObjectUuid) + ".object"),
        token / "bbbbbbbb-cccc-dddd-eeee-ffffffffffff.object");
    AssertRejectedWithoutMutation(root, Identity());
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    const auto token = CreateTokenTree(root);
    for (std::size_t index = 0; index < 65U; ++index) {
      std::ostringstream uuid;
      uuid << std::hex << std::setfill('0') << std::setw(8) << index
           << "-0000-0000-0000-" << std::setw(12) << index;
      WriteFile(token / (uuid.str() + ".object"));
      WriteFile(token / (uuid.str() + ".lock"));
    }
    AssertRejectedWithoutMutation(root, Identity());
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    const auto token = CreateTokenTree(root);
    std::filesystem::remove(token / "generation");
    AssertRejectedWithoutMutation(root, Identity());
  }
  {
    TemporaryDirectory fixture;
    const auto root = fixture.path() / "tokens";
    std::filesystem::create_directory(root);
    CreateTokenTree(root);
    AssertRejectedWithoutMutation(root, Identity(), ::geteuid() + 1U);
    AssertRejectedWithoutMutation(root, Identity(), ::geteuid(),
                                  ::getegid() + 1U, ::getegid() + 2U);
  }
}

} // namespace

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
  TestSoftHsmAccessSuccessAndIdempotence();
  TestSoftHsmAccessRejectsIdentityAndMapping();
  TestSoftHsmAccessRejectsHostileTrees();
  return 0;
}
