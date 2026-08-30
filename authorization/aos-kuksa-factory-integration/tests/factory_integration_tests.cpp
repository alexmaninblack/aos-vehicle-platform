// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "factory/integration.hpp"

#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <filesystem>
#include <fstream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {

class Cleanup final : public aos::factory::CleanupRoot {
public:
  bool RemoveFile(std::string_view path) override {
    files.emplace_back(path);
    return ok;
  }
  bool ClearDedicatedPkcs11Tokens() override {
    ++pkcs11_clears;
    return ok;
  }
  bool SyncProviderDirectory() override {
    ++syncs;
    return ok;
  }
  bool SyncTlsDirectory() override {
    ++syncs;
    return ok;
  }
  bool ok{true};
  unsigned syncs{0};
  unsigned pkcs11_clears{0};
  std::vector<std::string> files;
};

class TemporaryDirectory final {
public:
  TemporaryDirectory() {
    std::string pattern = "/tmp/aos-kuksa-cleanup-test-XXXXXX";
    char *result = ::mkdtemp(pattern.data());
    assert(result != nullptr);
    path_ = result;
  }
  TemporaryDirectory(const TemporaryDirectory &) = delete;
  TemporaryDirectory &operator=(const TemporaryDirectory &) = delete;
  ~TemporaryDirectory() { std::filesystem::remove_all(path_); }
  const std::filesystem::path &path() const { return path_; }

private:
  std::filesystem::path path_;
};

void WriteFile(const std::filesystem::path &path,
               std::string_view value = "fixture") {
  std::ofstream output(path, std::ios::binary);
  assert(output.good());
  output << value;
  output.close();
  assert(output.good());
}

bool ClearTokens(const std::filesystem::path &path) {
  const std::string value = path.string();
  return aos::factory::ClearPkcs11Tokens(value);
}

void TestCleanup() {
  Cleanup cleanup;
  assert(aos::factory::CleanupRuntime(cleanup));
  assert(cleanup.files.size() == 8U);
  assert(cleanup.pkcs11_clears == 1U);
  assert(cleanup.syncs == 2U);
  assert(cleanup.files[0] == "/var/lib/aos-kuksa-provider/kuksa-token");
  assert(cleanup.files[1] == "/var/lib/aos-kuksa-provider/.kuksa-token.tmp");
  for (const auto &path : cleanup.files) {
    assert(path.find(".kuksa-jwt-pin") == std::string::npos);
    assert(path.find("softhsm") == std::string::npos);
    assert(path.find("systemd-slot-component") == std::string::npos);
  }
}

void TestPkcs11CleanupNormalAndEmpty() {
  TemporaryDirectory fixture;
  const auto tokens = fixture.path() / "tokens";
  std::filesystem::create_directory(tokens);
  assert(ClearTokens(tokens));
  assert(std::filesystem::is_directory(tokens));

  for (const auto &token : {"token-a", "token-b"}) {
    const auto directory = tokens / token;
    std::filesystem::create_directory(directory);
    WriteFile(directory / "generation");
    WriteFile(directory / "object-01");
  }
  assert(ClearTokens(tokens));
  assert(std::filesystem::is_directory(tokens));
  assert(std::filesystem::is_empty(tokens));
}

void TestPkcs11CleanupRejectsHostileTrees() {
  {
    TemporaryDirectory fixture;
    const auto tokens = fixture.path() / "tokens";
    std::filesystem::create_directory(tokens);
    const auto token = tokens / "token";
    std::filesystem::create_directory(token);
    WriteFile(token / "preserved");
    assert(::symlink("preserved", (token / "link").c_str()) == 0);
    assert(!ClearTokens(tokens));
    assert(std::filesystem::exists(token / "preserved"));
  }
  {
    TemporaryDirectory fixture;
    const auto tokens = fixture.path() / "tokens";
    std::filesystem::create_directory(tokens);
    const auto token = tokens / "token";
    std::filesystem::create_directory(token);
    WriteFile(token / "preserved");
    assert(::mkfifo((token / "special").c_str(), 0600) == 0);
    assert(!ClearTokens(tokens));
    assert(std::filesystem::exists(token / "preserved"));
  }
  {
    TemporaryDirectory fixture;
    const auto tokens = fixture.path() / "tokens";
    std::filesystem::create_directory(tokens);
    const auto token = tokens / "token";
    std::filesystem::create_directory(token);
    WriteFile(token / "preserved");
    std::filesystem::create_directory(token / "nested");
    assert(!ClearTokens(tokens));
    assert(std::filesystem::exists(token / "preserved"));
  }
  {
    TemporaryDirectory fixture;
    const auto tokens = fixture.path() / "tokens";
    std::filesystem::create_directory(tokens);
    for (std::size_t index = 0;
         index <= aos::factory::kMaximumPkcs11TokenDirectories; ++index) {
      const auto token = tokens / ("token-" + std::to_string(index));
      std::filesystem::create_directory(token);
      WriteFile(token / "preserved");
    }
    assert(!ClearTokens(tokens));
    assert(std::filesystem::exists(tokens / "token-0" / "preserved"));
  }
  {
    TemporaryDirectory fixture;
    const auto tokens = fixture.path() / "tokens";
    std::filesystem::create_directory(tokens);
    const auto token = tokens / "token";
    std::filesystem::create_directory(token);
    for (std::size_t index = 0;
         index <= aos::factory::kMaximumPkcs11FilesPerToken; ++index) {
      WriteFile(token / ("object-" + std::to_string(index)));
    }
    assert(!ClearTokens(tokens));
    assert(std::filesystem::exists(token / "object-0"));
  }
  {
    TemporaryDirectory fixture;
    assert(!ClearTokens(fixture.path() / "missing"));
  }
}

void TestTlsIdentity() {
  std::string pattern = "/tmp/aos-kuksa-tls-test-XXXXXX";
  char *path = ::mkdtemp(pattern.data());
  assert(path != nullptr);
  assert(::chmod(path, 0700) == 0);
  const mode_t prior_umask = ::umask(0077);
  assert(aos::factory::PrepareTlsIdentity(path) ==
         aos::factory::TlsPrepareResult::kCreated);
  ::umask(prior_umask);

  const auto directory = std::filesystem::path(path);
  struct stat key_status{};
  struct stat cert_status{};
  assert(::stat((directory / "server.key").c_str(), &key_status) == 0);
  assert(::stat((directory / "server.pem").c_str(), &cert_status) == 0);
  assert((key_status.st_mode & 0777U) == 0600U);
  assert((cert_status.st_mode & 0777U) == 0644U);
  assert(aos::factory::PrepareTlsIdentity(path) ==
         aos::factory::TlsPrepareResult::kReused);

  assert(::chmod((directory / "server.key").c_str(), 0644) == 0);
  assert(aos::factory::PrepareTlsIdentity(path) ==
         aos::factory::TlsPrepareResult::kRejected);
  std::filesystem::remove_all(directory);
}

} // namespace

int main() {
  TestCleanup();
  TestPkcs11CleanupNormalAndEmpty();
  TestPkcs11CleanupRejectsHostileTrees();
  TestTlsIdentity();
  return 0;
}
