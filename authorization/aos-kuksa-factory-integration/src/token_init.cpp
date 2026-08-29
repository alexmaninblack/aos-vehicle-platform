// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "factory/integration.hpp"

#include <dlfcn.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <array>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <optional>
#include <vector>

namespace aos::factory {
namespace {

constexpr std::string_view kPinPath = "/var/aos/iam/.kuksa-jwt-pin";
constexpr std::string_view kPinTemporary = "/var/aos/iam/.kuksa-jwt-pin.tmp";
constexpr std::string_view kLibrary = "/usr/lib/softhsm/libsofthsm2.so";
constexpr std::string_view kTokenLabel = "aos-kuksa";

class NativePinStore final : public PinStore {
 public:
  std::optional<PinState> Inspect() override {
    struct stat status {};
    if (::lstat(std::string(kPinPath).c_str(), &status) != 0) {
      if (errno == ENOENT) return PinState{};
      return std::nullopt;
    }
    PinState state{true, S_ISREG(status.st_mode), status.st_uid == 0,
                   static_cast<unsigned>(status.st_mode & 0777U), {}};
    if (!state.regular) return state;
    const int fd = ::open(std::string(kPinPath).c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return std::nullopt;
    char buffer[257]{};
    const ssize_t count = ::read(fd, buffer, sizeof(buffer));
    const ssize_t extra = count >= 0 ? ::read(fd, buffer, 1U) : -1;
    ::close(fd);
    if (count <= 0 || extra != 0) return state;
    state.value.assign(buffer, static_cast<std::size_t>(count));
    while (!state.value.empty() &&
           (state.value.back() == '\n' || state.value.back() == '\r')) state.value.pop_back();
    return state;
  }

  std::optional<std::string> Generate() override {
    std::ifstream random("/dev/urandom", std::ios::binary);
    std::array<unsigned char, 32> bytes{};
    if (!random.read(reinterpret_cast<char*>(bytes.data()), bytes.size())) return std::nullopt;
    static constexpr char alphabet[] =
        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
    std::string pin;
    pin.reserve(bytes.size());
    for (unsigned char value : bytes) pin.push_back(alphabet[value % (sizeof(alphabet) - 1U)]);
    return pin;
  }

  bool Publish(std::string_view pin) override {
    if (pin.empty() || pin.size() > 256U) return false;
    const int fd = ::open(std::string(kPinTemporary).c_str(),
        O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (fd < 0) return false;
    bool ok = ::fchmod(fd, 0600) == 0 && ::fchown(fd, 0, 0) == 0;
    std::size_t offset = 0;
    while (ok && offset < pin.size()) {
      const ssize_t count = ::write(fd, pin.data() + offset, pin.size() - offset);
      if (count <= 0) ok = false;
      else offset += static_cast<std::size_t>(count);
    }
    ok = ok && ::fsync(fd) == 0;
    if (::close(fd) != 0) ok = false;
    if (ok) ok = ::rename(std::string(kPinTemporary).c_str(), std::string(kPinPath).c_str()) == 0;
    if (!ok) ::unlink(std::string(kPinTemporary).c_str());
    return ok;
  }
};

// Minimal PKCS#11 ABI used to avoid command-line PIN delivery.  All function
// addresses come from the one pinned SoftHSM library and every call is finite.
using ULong = unsigned long;
using Slot = ULong;
using Session = ULong;
using Rv = ULong;
using Byte = unsigned char;
constexpr Rv kOk = 0;
constexpr ULong kSerialSession = 0x4U;
constexpr ULong kRwSession = 0x2U;
constexpr ULong kUserSo = 0U;
constexpr ULong kUser = 1U;

struct TokenInfo {
  Byte label[32];
  Byte manufacturer[32];
  Byte model[16];
  Byte serial[16];
  ULong flags;
  ULong remaining[21];
};

class NativeTokenStore final : public TokenStore {
 public:
  NativeTokenStore() {
    library_ = ::dlopen(std::string(kLibrary).c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!library_) return;
    init_ = Symbol<Init>("C_Initialize");
    finish_ = Symbol<Finish>("C_Finalize");
    slots_ = Symbol<GetSlots>("C_GetSlotList");
    info_ = Symbol<GetInfo>("C_GetTokenInfo");
    init_token_ = Symbol<InitToken>("C_InitToken");
    open_ = Symbol<OpenSession>("C_OpenSession");
    login_ = Symbol<Login>("C_Login");
    init_pin_ = Symbol<InitPin>("C_InitPIN");
    close_ = Symbol<CloseSession>("C_CloseSession");
    ready_ = init_ && finish_ && slots_ && info_ && init_token_ && open_ && login_ &&
             init_pin_ && close_ && init_(nullptr) == kOk;
  }
  ~NativeTokenStore() override {
    if (ready_) finish_(nullptr);
    if (library_) ::dlclose(library_);
  }

  std::optional<TokenState> Inspect(std::optional<std::string_view> pin) override {
    if (!ready_) return std::nullopt;
    auto slots = Slots(false);
    if (!slots) return std::nullopt;
    TokenState result;
    for (Slot slot : *slots) {
      TokenInfo info{};
      if (info_(slot, &info) != kOk) continue;
      std::string label(reinterpret_cast<char*>(info.label), sizeof(info.label));
      while (!label.empty() && label.back() == ' ') label.pop_back();
      if (label != kTokenLabel) continue;
      ++result.matching_tokens;
      if (pin && LoginUser(slot, *pin)) result.user_pin_valid = true;
    }
    return result;
  }

  bool Initialize(std::string_view user_pin, std::string_view so_pin) override {
    if (!ready_ || user_pin.empty() || so_pin.empty()) return false;
    auto slots = Slots(false);
    if (!slots) return false;
    std::vector<Slot> candidates;
    for (Slot slot : *slots) {
      TokenInfo info{};
      if (info_(slot, &info) != kOk) candidates.push_back(slot);
    }
    if (candidates.size() != 1U) return false;
    std::array<Byte, 32> label{};
    label.fill(' ');
    std::memcpy(label.data(), kTokenLabel.data(), kTokenLabel.size());
    if (init_token_(candidates[0], Bytes(so_pin), so_pin.size(), label.data()) != kOk) return false;
    Session session = 0;
    if (open_(candidates[0], kSerialSession | kRwSession, nullptr, nullptr, &session) != kOk) return false;
    bool ok = login_(session, kUserSo, Bytes(so_pin), so_pin.size()) == kOk &&
              init_pin_(session, Bytes(user_pin), user_pin.size()) == kOk;
    if (ok) {
      // Verify the user credential through a new session rather than trusting
      // initialization return codes alone.
      close_(session);
      return LoginUser(candidates[0], user_pin);
    }
    close_(session);
    return false;
  }

 private:
  using Init = Rv (*)(void*);
  using Finish = Rv (*)(void*);
  using GetSlots = Rv (*)(Byte, Slot*, ULong*);
  using GetInfo = Rv (*)(Slot, TokenInfo*);
  using InitToken = Rv (*)(Slot, Byte*, ULong, Byte*);
  using OpenSession = Rv (*)(Slot, ULong, void*, void*, Session*);
  using Login = Rv (*)(Session, ULong, Byte*, ULong);
  using InitPin = Rv (*)(Session, Byte*, ULong);
  using CloseSession = Rv (*)(Session);

  template <typename Type>
  Type Symbol(const char* name) { return reinterpret_cast<Type>(::dlsym(library_, name)); }
  static Byte* Bytes(std::string_view value) {
    return reinterpret_cast<Byte*>(const_cast<char*>(value.data()));
  }
  std::optional<std::vector<Slot>> Slots(bool present) {
    ULong count = 0;
    if (slots_(present ? 1 : 0, nullptr, &count) != kOk || count == 0 || count > 64U) {
      return std::nullopt;
    }
    std::vector<Slot> result(count);
    if (slots_(present ? 1 : 0, result.data(), &count) != kOk) return std::nullopt;
    result.resize(count);
    return result;
  }
  bool LoginUser(Slot slot, std::string_view pin) {
    Session session = 0;
    if (open_(slot, kSerialSession | kRwSession, nullptr, nullptr, &session) != kOk) return false;
    const bool ok = login_(session, kUser, Bytes(pin), pin.size()) == kOk;
    close_(session);
    return ok;
  }

  void* library_{nullptr};
  Init init_{nullptr}; Finish finish_{nullptr}; GetSlots slots_{nullptr};
  GetInfo info_{nullptr}; InitToken init_token_{nullptr}; OpenSession open_{nullptr};
  Login login_{nullptr}; InitPin init_pin_{nullptr}; CloseSession close_{nullptr};
  bool ready_{false};
};

}  // namespace

InitResult InitializeToken(PinStore& pins, TokenStore& tokens) {
  auto pin = pins.Inspect();
  if (!pin) return InitResult::kUnavailable;
  if (pin->exists) {
    if (!pin->regular || !pin->root_owned || pin->mode != 0600U ||
        pin->value.empty() || pin->value.size() > 256U) return InitResult::kRejected;
    auto token = tokens.Inspect(pin->value);
    if (!token) return InitResult::kUnavailable;
    return token->matching_tokens == 1U && token->user_pin_valid
               ? InitResult::kValidated : InitResult::kRejected;
  }
  auto token = tokens.Inspect(std::nullopt);
  if (!token) return InitResult::kUnavailable;
  if (token->matching_tokens != 0U) return InitResult::kRejected;
  auto user_pin = pins.Generate();
  auto so_pin = pins.Generate();
  if (!user_pin || !so_pin || *user_pin == *so_pin) return InitResult::kUnavailable;
  if (!tokens.Initialize(*user_pin, *so_pin)) return InitResult::kUnavailable;
  if (!pins.Publish(*user_pin)) return InitResult::kUnavailable;
  return InitResult::kCreated;
}

}  // namespace aos::factory

#ifndef AOS_FACTORY_NO_MAIN
int main() {
  aos::factory::NativePinStore pins;
  aos::factory::NativeTokenStore tokens;
  const auto result = aos::factory::InitializeToken(pins, tokens);
  return result == aos::factory::InitResult::kCreated ||
                 result == aos::factory::InitResult::kValidated ? 0 : 1;
}
#endif
