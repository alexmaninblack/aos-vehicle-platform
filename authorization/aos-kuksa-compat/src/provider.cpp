// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/provider.hpp"

#include "kac/core.hpp"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <charconv>
#include <cstring>
#include <sstream>

namespace aos::kac::provider {
namespace {

constexpr std::string_view kDirectory = "/var/lib/aos-kuksa-provider";
constexpr std::string_view kDestination = "kuksa-token";
constexpr std::string_view kTemporary = ".kuksa-token.tmp";

std::optional<std::vector<std::uint8_t>> Decode(std::string_view input) {
  if (input.empty() || input.find('=') != std::string_view::npos) return std::nullopt;
  if (input.size() % 4U == 1U) return std::nullopt;
  auto value = [](char c) -> int {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '-') return 62;
    if (c == '_') return 63;
    return -1;
  };
  std::vector<std::uint8_t> output;
  std::uint32_t accumulator = 0;
  unsigned bits = 0;
  for (char c : input) {
    const int decoded = value(c);
    if (decoded < 0) return std::nullopt;
    accumulator = (accumulator << 6U) | static_cast<unsigned>(decoded);
    bits += 6U;
    if (bits >= 8U) {
      bits -= 8U;
      output.push_back(static_cast<std::uint8_t>((accumulator >> bits) & 0xffU));
    }
  }
  if (bits != 0U && (accumulator & ((1U << bits) - 1U)) != 0U) return std::nullopt;
  return output;
}

std::optional<std::int64_t> ParseInteger(std::string_view text) {
  if (text.empty() || text.front() == '+' ||
      (text.size() > 1U && text.front() == '0')) return std::nullopt;
  std::int64_t result = 0;
  const auto parsed = std::from_chars(text.data(), text.data() + text.size(), result);
  if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size()) {
    return std::nullopt;
  }
  return result;
}

std::optional<std::pair<std::int64_t, std::int64_t>> ParseExactPayload(
    std::string_view payload) {
  constexpr std::string_view prefix =
      R"({"sub":"aos-vdp","iss":"aosedge-vdp-provider","aud":["kuksa.val"],"iat":)";
  constexpr std::string_view middle = R"(,"exp":)";
  const std::string suffix = std::string(R"(,"scope":")") + std::string(kScope) + "\"}";
  if (payload.size() < prefix.size() + suffix.size() ||
      payload.substr(0, prefix.size()) != prefix ||
      payload.substr(payload.size() - suffix.size()) != suffix) return std::nullopt;
  payload.remove_prefix(prefix.size());
  payload.remove_suffix(suffix.size());
  const auto separator = payload.find(middle);
  if (separator == std::string_view::npos ||
      payload.find(middle, separator + middle.size()) != std::string_view::npos) {
    return std::nullopt;
  }
  auto issued = ParseInteger(payload.substr(0, separator));
  auto expires = ParseInteger(payload.substr(separator + middle.size()));
  if (!issued || !expires) return std::nullopt;
  return std::pair{*issued, *expires};
}

bool SyncDirectory(int fd) { return ::fsync(fd) == 0; }

}  // namespace

std::string Payload(std::int64_t issued_at) {
  std::ostringstream output;
  output << R"({"sub":"aos-vdp","iss":"aosedge-vdp-provider","aud":["kuksa.val"],"iat":)"
         << issued_at << R"(,"exp":)" << issued_at + kLifetimeSeconds
         << R"(,"scope":")" << kScope << "\"}";
  return output.str();
}

std::optional<std::string> CreateToken(std::int64_t issued_at, Signer& signer) {
  if (!signer.Ready() || issued_at < 0) return std::nullopt;
  const std::string signing_input = Base64Url(kHeader) + "." + Base64Url(Payload(issued_at));
  auto signature = signer.Sign(signing_input);
  if (!signature || signature->size() != 256U) return std::nullopt;
  const std::string bytes(reinterpret_cast<const char*>(signature->data()), signature->size());
  std::string token = signing_input + "." + Base64Url(bytes);
  if (token.empty() || token.size() > kMaximumJwtBytes) return std::nullopt;
  return token;
}

bool ValidateToken(std::string_view token, std::int64_t now, const Signer& signer) {
  if (!signer.Ready() || token.empty() || token.size() > kMaximumJwtBytes || now < 0) {
    return false;
  }
  const auto first = token.find('.');
  const auto second = first == std::string_view::npos ? first : token.find('.', first + 1U);
  if (first == std::string_view::npos || second == std::string_view::npos ||
      token.find('.', second + 1U) != std::string_view::npos) return false;
  const auto header = Decode(token.substr(0, first));
  const auto payload = Decode(token.substr(first + 1U, second - first - 1U));
  const auto signature = Decode(token.substr(second + 1U));
  if (!header || !payload || !signature || signature->size() != 256U) return false;
  if (std::string_view(reinterpret_cast<const char*>(header->data()), header->size()) != kHeader) {
    return false;
  }
  const std::string_view payload_text(reinterpret_cast<const char*>(payload->data()), payload->size());
  auto times = ParseExactPayload(payload_text);
  if (!times) return false;
  const auto [issued, expires] = *times;
  if (issued < 0 || issued > now + kMaximumFutureSeconds ||
      expires != issued + kLifetimeSeconds || expires <= now) return false;
  return signer.Verify(token.substr(0, second), *signature);
}

Result Prepare(std::int64_t now, Signer& signer, Store& store) {
  if (!signer.Ready() || now < 0) return Result::kUnavailable;
  auto existing = store.Read();
  if (!existing) return Result::kUnavailable;
  if (existing->exists) {
    if (!existing->regular || !existing->root_owned || existing->mode != 0600U) {
      return Result::kRejected;
    }
    if (ValidateToken(existing->bytes, now, signer)) return Result::kReused;
    // Only an exact signed expired token may be replaced.  Testing one second
    // before its issue time distinguishes expiry from every malformed token.
    bool exact_expired = false;
    const auto first = existing->bytes.find('.');
    const auto second = first == std::string::npos ? first : existing->bytes.find('.', first + 1U);
    if (first != std::string::npos && second != std::string::npos) {
      auto decoded = Decode(std::string_view(existing->bytes).substr(first + 1U, second - first - 1U));
      if (decoded) {
        auto times = ParseExactPayload(std::string_view(
            reinterpret_cast<const char*>(decoded->data()), decoded->size()));
        if (times && times->second <= now && times->first >= 0) {
          exact_expired = ValidateToken(existing->bytes, times->first, signer);
        }
      }
    }
    if (!exact_expired) return Result::kRejected;
  }
  auto token = CreateToken(now, signer);
  if (!token || !store.ReplaceAtomically(*token)) return Result::kUnavailable;
  return Result::kCreated;
}

FixedStore::FixedStore() {
  directory_fd_ = ::open(std::string(kDirectory).c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
}

FixedStore::~FixedStore() {
  if (directory_fd_ >= 0) ::close(directory_fd_);
}

std::optional<ExistingToken> FixedStore::Read() {
  if (directory_fd_ < 0) return std::nullopt;
  const int fd = ::openat(directory_fd_, std::string(kDestination).c_str(),
                          O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) {
    if (errno == ENOENT) return ExistingToken{};
    return std::nullopt;
  }
  struct stat status {};
  if (::fstat(fd, &status) != 0) { ::close(fd); return std::nullopt; }
  ExistingToken token{true, S_ISREG(status.st_mode), status.st_uid == 0,
                      static_cast<unsigned>(status.st_mode & 0777U), {}};
  char buffer[4096];
  ssize_t count = 0;
  while ((count = ::read(fd, buffer, sizeof(buffer))) > 0) {
    if (token.bytes.size() + static_cast<std::size_t>(count) > kMaximumJwtBytes) {
      ::close(fd); return token;
    }
    token.bytes.append(buffer, static_cast<std::size_t>(count));
  }
  const bool ok = count == 0;
  ::close(fd);
  return ok ? std::optional<ExistingToken>(std::move(token)) : std::nullopt;
}

bool FixedStore::ReplaceAtomically(std::string_view bytes) {
  if (directory_fd_ < 0 || bytes.empty() || bytes.size() > kMaximumJwtBytes) return false;
  struct stat stale {};
  if (::fstatat(directory_fd_, std::string(kTemporary).c_str(), &stale, AT_SYMLINK_NOFOLLOW) == 0) {
    if (!S_ISREG(stale.st_mode) || stale.st_uid != 0 ||
        ::unlinkat(directory_fd_, std::string(kTemporary).c_str(), 0) != 0) return false;
  } else if (errno != ENOENT) return false;
  const int fd = ::openat(directory_fd_, std::string(kTemporary).c_str(),
      O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (fd < 0) return false;
  bool ok = ::fchmod(fd, 0600) == 0 && ::fchown(fd, 0, 0) == 0;
  std::size_t offset = 0;
  while (ok && offset < bytes.size()) {
    const ssize_t count = ::write(fd, bytes.data() + offset, bytes.size() - offset);
    if (count <= 0) ok = false;
    else offset += static_cast<std::size_t>(count);
  }
  ok = ok && ::fsync(fd) == 0;
  if (::close(fd) != 0) ok = false;
  if (ok) ok = ::renameat(directory_fd_, std::string(kTemporary).c_str(),
                          directory_fd_, std::string(kDestination).c_str()) == 0;
  if (ok) ok = SyncDirectory(directory_fd_);
  if (!ok) ::unlinkat(directory_fd_, std::string(kTemporary).c_str(), 0);
  return ok;
}

}  // namespace aos::kac::provider
