// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/verifier_prepare.hpp"
#include "kac/core.hpp"

#include <dirent.h>
#include <fcntl.h>
#include <grp.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

#ifndef AOS_KAC_NO_VERIFIER_MAIN
#include <dlfcn.h>
#include <openssl/crypto.h>
#endif

namespace {

#ifndef AOS_KAC_NO_VERIFIER_MAIN
constexpr const char *kVerifier =
    "/run/aos-kuksa-verifier/kuksa-jwt-public.pem";
constexpr const char *kTemporary =
    "/run/aos-kuksa-verifier/.kuksa-jwt-public.pem.tmp";
constexpr const char *kTokensRoot = "/var/lib/softhsm/tokens";
#endif

#ifdef __APPLE__
constexpr mode_t kFinalTokenDirectoryMode = 0750U;
#else
constexpr mode_t kFinalTokenDirectoryMode = 02750U;
#endif

class Descriptor final {
public:
  explicit Descriptor(int value = -1) : value_(value) {}
  Descriptor(const Descriptor &) = delete;
  Descriptor &operator=(const Descriptor &) = delete;
  Descriptor(Descriptor &&other) noexcept
      : value_(std::exchange(other.value_, -1)) {}
  Descriptor &operator=(Descriptor &&other) noexcept {
    if (this == &other)
      return *this;
    if (value_ >= 0)
      ::close(value_);
    value_ = std::exchange(other.value_, -1);
    return *this;
  }
  ~Descriptor() {
    if (value_ >= 0)
      ::close(value_);
  }
  int get() const { return value_; }
  explicit operator bool() const { return value_ >= 0; }

private:
  int value_;
};

struct AccessFile {
  std::string name;
  Descriptor descriptor;
  mode_t target_mode{0};
  gid_t current_group{0};
  mode_t current_mode{0};
};

bool IsLowerHex(char value) {
  return (value >= '0' && value <= '9') || (value >= 'a' && value <= 'f');
}

bool IsCanonicalUuid(std::string_view value) {
  if (value.size() != 36U)
    return false;
  for (std::size_t index = 0; index < value.size(); ++index) {
    if (index == 8U || index == 13U || index == 18U || index == 23U) {
      if (value[index] != '-')
        return false;
    } else if (!IsLowerHex(value[index])) {
      return false;
    }
  }
  return true;
}

std::optional<std::string> SerialForUuid(std::string_view uuid) {
  if (!IsCanonicalUuid(uuid))
    return std::nullopt;
  return std::string(uuid.substr(19U, 4U)) + std::string(uuid.substr(24U, 12U));
}

bool AllowedGroup(gid_t value, gid_t initial_group, gid_t target_group) {
  return value == initial_group || value == target_group;
}

bool SyncMetadata(int descriptor) {
  if (::fsync(descriptor) == 0)
    return true;
#ifdef __APPLE__
  // APFS may reject fsync on a directory. Linux/target still requires the
  // durability barrier for every file and both directories.
  return errno == EINVAL;
#else
  return false;
#endif
}

std::optional<mode_t> TargetFileMode(std::string_view name,
                                     std::set<std::string> &objects,
                                     std::set<std::string> &locks) {
  if (name == "generation" || name == "token.object" || name == "token.lock") {
    return 0660;
  }
  constexpr std::string_view object_suffix = ".object";
  constexpr std::string_view lock_suffix = ".lock";
  std::string_view base;
  bool object = false;
  if (name.size() == 36U + object_suffix.size() &&
      name.substr(name.size() - object_suffix.size()) == object_suffix) {
    base = name.substr(0U, 36U);
    object = true;
  } else if (name.size() == 36U + lock_suffix.size() &&
             name.substr(name.size() - lock_suffix.size()) == lock_suffix) {
    base = name.substr(0U, 36U);
  } else {
    return std::nullopt;
  }
  if (!IsCanonicalUuid(base))
    return std::nullopt;
  if (object)
    objects.emplace(base);
  else
    locks.emplace(base);
  return 0640;
}

#ifndef AOS_KAC_NO_VERIFIER_MAIN
bool WriteAll(int descriptor, const std::string &value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const ssize_t written =
        write(descriptor, value.data() + offset, value.size() - offset);
    if (written < 0) {
      if (errno == EINTR)
        continue;
      return false;
    }
    offset += static_cast<std::size_t>(written);
  }
  return true;
}

using ULong = unsigned long;
using Slot = ULong;
using Session = ULong;
using Object = ULong;
using Rv = ULong;
using Byte = unsigned char;
constexpr Rv kOk = 0;
constexpr ULong kSerialSession = 0x4U;
constexpr ULong kRwSession = 0x2U;
constexpr ULong kUser = 1U;
constexpr ULong kPrivateKeyClass = 3U;
constexpr ULong kAttributeClass = 0U;
constexpr ULong kAttributeLabel = 3U;
constexpr ULong kTokenInitialized = 0x00000400UL;
constexpr const char *kLibrary = "/usr/lib/softhsm/libsofthsm2.so";
constexpr const char *kCredentialName = "kuksa-jwt-pin";
constexpr const char *kTokenLabel = "aos-kuksa";

struct TokenInfo {
  Byte label[32];
  Byte manufacturer[32];
  Byte model[16];
  Byte serial[16];
  ULong flags;
  ULong remaining[21];
};

struct Attribute {
  ULong type;
  void *value;
  ULong size;
};

void Diagnostic(const char *stage, Rv result) {
  std::fprintf(stderr, "verifier-prepare: stage=%s rv=0x%lx\n", stage, result);
}

std::string TrimPadded(const Byte *value, std::size_t size) {
  std::string result(reinterpret_cast<const char *>(value), size);
  while (!result.empty() && result.back() == ' ')
    result.pop_back();
  return result;
}

std::optional<std::string> ReadPinCredential() {
  const char *directory = std::getenv("CREDENTIALS_DIRECTORY");
  if (directory == nullptr || *directory == '\0')
    return std::nullopt;
  std::ifstream input(std::string(directory) + "/" + kCredentialName,
                      std::ios::binary);
  if (!input)
    return std::nullopt;
  std::string pin;
  std::array<char, 257> buffer{};
  input.read(buffer.data(), buffer.size());
  const std::streamsize count = input.gcount();
  if (count <= 0 || count > 256 || !input.eof())
    return std::nullopt;
  pin.assign(buffer.data(), static_cast<std::size_t>(count));
  while (!pin.empty() && (pin.back() == '\n' || pin.back() == '\r'))
    pin.pop_back();
  if (pin.empty() || pin.size() > 256U) {
    if (!pin.empty())
      OPENSSL_cleanse(pin.data(), pin.size());
    return std::nullopt;
  }
  return pin;
}

class Pkcs11IdentityResolver final {
public:
  Pkcs11IdentityResolver() {
    library_ = ::dlopen(kLibrary, RTLD_NOW | RTLD_LOCAL);
    if (!library_)
      return;
    init_ = Symbol<Init>("C_Initialize");
    finish_ = Symbol<Finish>("C_Finalize");
    slots_ = Symbol<GetSlots>("C_GetSlotList");
    info_ = Symbol<GetInfo>("C_GetTokenInfo");
    open_ = Symbol<OpenSession>("C_OpenSession");
    login_ = Symbol<Login>("C_Login");
    find_init_ = Symbol<FindInit>("C_FindObjectsInit");
    find_ = Symbol<Find>("C_FindObjects");
    find_final_ = Symbol<FindFinal>("C_FindObjectsFinal");
    close_ = Symbol<CloseSession>("C_CloseSession");
    const Rv result = init_ && finish_ && slots_ && info_ && open_ && login_ &&
                              find_init_ && find_ && find_final_ && close_
                          ? init_(nullptr)
                          : ~kOk;
    ready_ = result == kOk;
    if (!ready_)
      Diagnostic("pkcs11-initialize", result);
  }

  ~Pkcs11IdentityResolver() {
    if (ready_)
      finish_(nullptr);
    if (library_)
      ::dlclose(library_);
  }

  std::optional<aos::kac::SoftHsmAccessIdentity> Resolve() {
    if (!ready_)
      return std::nullopt;
    ULong count = 0;
    Rv result = slots_(0U, nullptr, &count);
    if (result != kOk || count == 0U || count > 64U) {
      Diagnostic("get-slot-count", result);
      return std::nullopt;
    }
    std::vector<Slot> slots(count);
    result = slots_(0U, slots.data(), &count);
    if (result != kOk) {
      Diagnostic("get-slots", result);
      return std::nullopt;
    }
    slots.resize(count);

    aos::kac::SoftHsmAccessIdentity identity;
    std::optional<Slot> selected;
    for (Slot slot : slots) {
      TokenInfo info{};
      result = info_(slot, &info);
      if (result != kOk)
        continue;
      if ((info.flags & kTokenInitialized) == 0U ||
          TrimPadded(info.label, sizeof(info.label)) != kTokenLabel) {
        continue;
      }
      ++identity.matching_tokens;
      if (!selected) {
        selected = slot;
        identity.serial = TrimPadded(info.serial, sizeof(info.serial));
      }
    }
    if (identity.matching_tokens != 1U || !selected)
      return identity;

    auto pin = ReadPinCredential();
    if (!pin)
      return std::nullopt;
    Session session = 0;
    result = open_(*selected, kSerialSession | kRwSession, nullptr, nullptr,
                   &session);
    if (result != kOk) {
      Diagnostic("open-session", result);
      OPENSSL_cleanse(pin->data(), pin->size());
      return std::nullopt;
    }
    result = login_(session, kUser, reinterpret_cast<Byte *>(pin->data()),
                    pin->size());
    OPENSSL_cleanse(pin->data(), pin->size());
    if (result != kOk) {
      Diagnostic("login-user", result);
      close_(session);
      return std::nullopt;
    }

    ULong private_key_class = kPrivateKeyClass;
    std::array<char, 9> key_label{
        {'k', 'u', 'k', 's', 'a', '-', 'j', 'w', 't'}};
    std::array<Attribute, 2> attributes{{
        {kAttributeClass, &private_key_class, sizeof(private_key_class)},
        {kAttributeLabel, key_label.data(), key_label.size()},
    }};
    result = find_init_(session, attributes.data(), attributes.size());
    if (result != kOk) {
      Diagnostic("find-private-key-init", result);
      close_(session);
      return std::nullopt;
    }
    std::array<Object, 2> objects{};
    ULong found = 0;
    result = find_(session, objects.data(), objects.size(), &found);
    const Rv final_result = find_final_(session);
    close_(session);
    if (result != kOk || final_result != kOk) {
      Diagnostic(result != kOk ? "find-private-key" : "find-private-key-final",
                 result != kOk ? result : final_result);
      return std::nullopt;
    }
    identity.exact_private_key = found == 1U;
    return identity;
  }

private:
  using Init = Rv (*)(void *);
  using Finish = Rv (*)(void *);
  using GetSlots = Rv (*)(Byte, Slot *, ULong *);
  using GetInfo = Rv (*)(Slot, TokenInfo *);
  using OpenSession = Rv (*)(Slot, ULong, void *, void *, Session *);
  using Login = Rv (*)(Session, ULong, Byte *, ULong);
  using FindInit = Rv (*)(Session, Attribute *, ULong);
  using Find = Rv (*)(Session, Object *, ULong, ULong *);
  using FindFinal = Rv (*)(Session);
  using CloseSession = Rv (*)(Session);

  template <typename Type> Type Symbol(const char *name) {
    return reinterpret_cast<Type>(::dlsym(library_, name));
  }

  void *library_{nullptr};
  Init init_{nullptr};
  Finish finish_{nullptr};
  GetSlots slots_{nullptr};
  GetInfo info_{nullptr};
  OpenSession open_{nullptr};
  Login login_{nullptr};
  FindInit find_init_{nullptr};
  Find find_{nullptr};
  FindFinal find_final_{nullptr};
  CloseSession close_{nullptr};
  bool ready_{false};
};

#endif

} // namespace

namespace aos::kac {

namespace {
SoftHsmAccessResult RejectAccess(const char *stage) {
  std::fprintf(stderr, "verifier-prepare: stage=%s\n", stage);
  return SoftHsmAccessResult::kRejected;
}
} // namespace

SoftHsmAccessResult FinalizeSoftHsmAccess(std::string_view tokens_root,
                                          const SoftHsmAccessIdentity &identity,
                                          uid_t expected_owner,
                                          gid_t initial_group,
                                          gid_t target_group) {
  if (identity.matching_tokens != 1U || !identity.exact_private_key ||
      identity.serial.size() != 16U ||
      !std::all_of(identity.serial.begin(), identity.serial.end(),
                   IsLowerHex)) {
    return RejectAccess("validate-pkcs-identity");
  }

  const std::string root_path(tokens_root);
  Descriptor root(::open(root_path.c_str(),
                         O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
  if (!root)
    return SoftHsmAccessResult::kUnavailable;
  struct stat root_status{};
  if (::fstat(root.get(), &root_status) != 0 || !S_ISDIR(root_status.st_mode) ||
      root_status.st_uid != expected_owner) {
    return RejectAccess("validate-token-root");
  }

  std::vector<std::string> mapped_directories;
  const int scan_descriptor = ::dup(root.get());
  DIR *scan = scan_descriptor >= 0 ? ::fdopendir(scan_descriptor) : nullptr;
  if (!scan) {
    if (scan_descriptor >= 0)
      ::close(scan_descriptor);
    return SoftHsmAccessResult::kUnavailable;
  }
  bool valid = true;
  std::size_t directory_count = 0U;
  while (valid) {
    errno = 0;
    dirent *entry = ::readdir(scan);
    if (!entry) {
      if (errno != 0)
        valid = false;
      break;
    }
    const std::string name(entry->d_name);
    if (name == "." || name == "..")
      continue;
    if (++directory_count > kMaximumSoftHsmTokenDirectories ||
        !IsCanonicalUuid(name)) {
      valid = false;
      break;
    }
    struct stat status{};
    if (::fstatat(root.get(), name.c_str(), &status, AT_SYMLINK_NOFOLLOW) !=
            0 ||
        !S_ISDIR(status.st_mode) || status.st_uid != expected_owner ||
        !AllowedGroup(status.st_gid, initial_group, target_group)) {
      valid = false;
      break;
    }
    const auto serial = SerialForUuid(name);
    if (serial && *serial == identity.serial)
      mapped_directories.push_back(name);
  }
  ::closedir(scan);
  if (!valid || mapped_directories.size() != 1U)
    return RejectAccess("map-token-directory");

  const std::string &token_name = mapped_directories.front();
  Descriptor token(::openat(root.get(), token_name.c_str(),
                            O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW));
  if (!token)
    return SoftHsmAccessResult::kUnavailable;
  struct stat token_status{};
  if (::fstat(token.get(), &token_status) != 0 ||
      !S_ISDIR(token_status.st_mode) || token_status.st_uid != expected_owner ||
      !AllowedGroup(token_status.st_gid, initial_group, target_group)) {
    return RejectAccess("validate-token-directory-owner");
  }
  const mode_t token_mode = token_status.st_mode & 07777U;
  if (token_mode != 0700U && token_mode != kFinalTokenDirectoryMode) {
    return RejectAccess("validate-token-directory-mode");
  }

  std::vector<AccessFile> files;
  std::set<std::string> objects;
  std::set<std::string> locks;
  std::set<std::string> metadata;
  const int file_scan_descriptor = ::dup(token.get());
  DIR *file_scan =
      file_scan_descriptor >= 0 ? ::fdopendir(file_scan_descriptor) : nullptr;
  if (!file_scan) {
    if (file_scan_descriptor >= 0)
      ::close(file_scan_descriptor);
    return SoftHsmAccessResult::kUnavailable;
  }
  while (valid) {
    errno = 0;
    dirent *entry = ::readdir(file_scan);
    if (!entry) {
      if (errno != 0)
        valid = false;
      break;
    }
    const std::string name(entry->d_name);
    if (name == "." || name == "..")
      continue;
    if (files.size() >= kMaximumSoftHsmFiles) {
      valid = false;
      break;
    }
    auto target_mode = TargetFileMode(name, objects, locks);
    if (!target_mode) {
      valid = false;
      break;
    }
    if (name == "generation" || name == "token.object" ||
        name == "token.lock") {
      metadata.emplace(name);
    }
    Descriptor file(
        ::openat(token.get(), name.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW));
    struct stat status{};
    if (!file || ::fstat(file.get(), &status) != 0 ||
        !S_ISREG(status.st_mode) || status.st_uid != expected_owner ||
        !AllowedGroup(status.st_gid, initial_group, target_group) ||
        status.st_nlink != 1) {
      valid = false;
      break;
    }
    const mode_t mode = status.st_mode & 07777U;
    if (mode != 0600U && mode != *target_mode) {
      valid = false;
      break;
    }
    files.push_back({name, std::move(file), *target_mode, status.st_gid, mode});
  }
  ::closedir(file_scan);
  if (!valid ||
      metadata !=
          std::set<std::string>{"generation", "token.lock", "token.object"} ||
      objects.empty() || objects != locks) {
    return RejectAccess("validate-token-files");
  }

  bool changed = token_status.st_gid != target_group ||
                 token_mode != kFinalTokenDirectoryMode;
  for (const auto &file : files) {
    changed = changed || file.current_group != target_group ||
              file.current_mode != file.target_mode;
  }
  if (!changed)
    return SoftHsmAccessResult::kAlreadyCorrect;

  for (auto &file : files) {
    if (file.current_group != target_group &&
        ::fchown(file.descriptor.get(), static_cast<uid_t>(-1), target_group) !=
            0) {
      return SoftHsmAccessResult::kUnavailable;
    }
    if (file.current_mode != file.target_mode &&
        ::fchmod(file.descriptor.get(), file.target_mode) != 0) {
      return SoftHsmAccessResult::kUnavailable;
    }
    if (!SyncMetadata(file.descriptor.get()))
      return SoftHsmAccessResult::kUnavailable;
  }
  if (token_status.st_gid != target_group &&
      ::fchown(token.get(), static_cast<uid_t>(-1), target_group) != 0) {
    return SoftHsmAccessResult::kUnavailable;
  }
  if (token_mode != kFinalTokenDirectoryMode &&
      ::fchmod(token.get(), kFinalTokenDirectoryMode) != 0) {
    return SoftHsmAccessResult::kUnavailable;
  }
  if (!SyncMetadata(token.get()) || !SyncMetadata(root.get())) {
    return SoftHsmAccessResult::kUnavailable;
  }
  return SoftHsmAccessResult::kUpdated;
}

bool RemoveStaleTemporaryVerifier(std::string_view path) {
  const std::string temporary(path);
  struct stat status{};
  if (::lstat(temporary.c_str(), &status) != 0)
    return errno == ENOENT;
  if (!S_ISREG(status.st_mode) || status.st_uid != ::geteuid() ||
      status.st_nlink != 1) {
    return false;
  }
  return ::unlink(temporary.c_str()) == 0;
}

} // namespace aos::kac

#ifndef AOS_KAC_NO_VERIFIER_MAIN
int main() {
  Pkcs11IdentityResolver resolver;
  const auto identity = resolver.Resolve();
  const struct group *kac_group = ::getgrnam("aos-kac");
  if (!identity || kac_group == nullptr || kac_group->gr_gid == 0U)
    return 1;
  const auto access = aos::kac::FinalizeSoftHsmAccess(
      kTokensRoot, *identity, 0U, 0U, kac_group->gr_gid);
  if (access != aos::kac::SoftHsmAccessResult::kAlreadyCorrect &&
      access != aos::kac::SoftHsmAccessResult::kUpdated) {
    return 1;
  }

  aos::kac::Pkcs11Signer signer;
  if (!signer.Ready())
    return 1;
  const std::string probe = "aosedge-kuksa-verifier-self-test/v1";
  const auto signature = signer.Sign(probe);
  const auto public_key = signer.PublicKeyPem();
  if (!signature || !public_key || !signer.Verify(probe, *signature))
    return 1;

  if (!aos::kac::RemoveStaleTemporaryVerifier(kTemporary))
    return 1;
  const int descriptor =
      open(kTemporary, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0444);
  if (descriptor < 0)
    return 1;
  bool ok = WriteAll(descriptor, *public_key) && fsync(descriptor) == 0 &&
            fchmod(descriptor, 0444) == 0;
  if (close(descriptor) != 0)
    ok = false;
  if (!ok || rename(kTemporary, kVerifier) != 0) {
    unlink(kTemporary);
    return 1;
  }
  return 0;
}
#endif
