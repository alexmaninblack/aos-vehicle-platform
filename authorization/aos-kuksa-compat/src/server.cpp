// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

#include <grp.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <unordered_map>

namespace aos::kac {
namespace {

constexpr const char* kSocketPath = "/run/aos-kuksa-auth-compat/request.sock";
constexpr const char* kClientGroup = "aos-kuksa-clients";
constexpr int kBacklog = 8;
constexpr unsigned kMaximumConcurrent = 4;

double SteadySeconds() {
  return std::chrono::duration<double>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

class RateLimiter {
 public:
  bool Admit(uid_t uid) {
    std::lock_guard<std::mutex> guard(lock_);
    const double now = SteadySeconds();
    auto [entry, inserted] = per_peer_.try_emplace(uid, 4.0, 12.0, now);
    (void)inserted;
    if (!entry->second.CanConsume(now) || !global_.CanConsume(now)) return false;
    return entry->second.Consume(now) && global_.Consume(now);
  }

 private:
  std::mutex lock_;
  TokenBucket global_{10.0, 30.0, SteadySeconds()};
  std::unordered_map<uid_t, TokenBucket> per_peer_;
};

bool SendAll(int descriptor, const std::string& value) {
  std::size_t offset = 0;
  while (offset < value.size()) {
    const ssize_t sent = send(descriptor, value.data() + offset, value.size() - offset, MSG_NOSIGNAL);
    if (sent < 0) {
      if (errno == EINTR) continue;
      return false;
    }
    if (sent == 0) return false;
    offset += static_cast<std::size_t>(sent);
  }
  return true;
}

std::optional<std::string> ReadFrame(int descriptor) {
  struct timeval timeout {2, 0};
  if (setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) {
    return std::nullopt;
  }
  std::string frame;
  frame.reserve(1024);
  char buffer[2048];
  while (frame.size() <= kMaxRequestBytes) {
    const ssize_t received = recv(descriptor, buffer, sizeof(buffer), 0);
    if (received <= 0) return std::nullopt;
    frame.append(buffer, static_cast<std::size_t>(received));
    const auto line_feed = frame.find('\n');
    if (line_feed != std::string::npos) {
      if (line_feed + 1U != frame.size()) return std::nullopt;
      return frame;
    }
  }
  return std::nullopt;
}

class ActiveRequest {
 public:
  explicit ActiveRequest(ConcurrencyGate& gate) : gate_(gate) {}
  ~ActiveRequest() { gate_.Release(); }

 private:
  ConcurrencyGate& gate_;
};

int StartupFailure(const char* stage, int error) {
  std::fprintf(stderr,
               "aos-kuksa-auth-compat: startup stage=%s failed errno=%d\n",
               stage, error);
  return 1;
}

int ListenerFailure(int listener, const char* stage, int error) {
  close(listener);
  unlink(kSocketPath);
  return StartupFailure(stage, error);
}

}  // namespace

int RunServer(Core& core) {
  const group* group = getgrnam(kClientGroup);
  if (group == nullptr) return StartupFailure("client-group", errno);
  const int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (listener < 0) return StartupFailure("socket", errno);
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  if (std::strlen(kSocketPath) >= sizeof(address.sun_path)) {
    return ListenerFailure(listener, "socket-path", ENAMETOOLONG);
  }
  std::strncpy(address.sun_path, kSocketPath, sizeof(address.sun_path) - 1U);
  unlink(kSocketPath);
  if (bind(listener, reinterpret_cast<const sockaddr*>(&address), sizeof(address)) != 0)
    return ListenerFailure(listener, "bind", errno);
  if (chmod(kSocketPath, 0660) != 0)
    return ListenerFailure(listener, "chmod", errno);
  if (chown(kSocketPath, static_cast<uid_t>(-1), group->gr_gid) != 0)
    return ListenerFailure(listener, "chown", errno);
  if (listen(listener, kBacklog) != 0)
    return ListenerFailure(listener, "listen", errno);

  static ConcurrencyGate active{kMaximumConcurrent};
  static RateLimiter rates;
  for (;;) {
    const int connection = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC);
    if (connection < 0) {
      if (errno == EINTR) continue;
      const int error = errno;
      close(listener);
      unlink(kSocketPath);
      return StartupFailure("accept", error);
    }
    ucred credentials{};
    socklen_t size = sizeof(credentials);
    bool reserved = false;
    if (getsockopt(connection, SOL_SOCKET, SO_PEERCRED, &credentials, &size) == 0) {
      reserved = active.TryAcquire();
      if (reserved && !rates.Admit(credentials.uid)) {
        active.Release();
        reserved = false;
      }
    }
    if (!reserved) {
      const auto busy = core.Reject(RejectionCode::kBusy);
      SendAll(connection, busy.json);
      close(connection);
      continue;
    }
    try {
      std::thread([connection, &core]() {
        ActiveRequest request_guard(active);
        const auto started = std::chrono::steady_clock::now();
        const auto frame = ReadFrame(connection);
        Response response;
        if (!frame) {
          response = core.Reject(RejectionCode::kInvalidRequest);
        } else {
          const auto request = ParseRequestFrame(*frame);
          response = request ? core.Handle(*request) : core.Reject(RejectionCode::kInvalidRequest);
        }
        if (std::chrono::steady_clock::now() - started > std::chrono::seconds(8)) {
          response = core.Reject(RejectionCode::kInternalError);
        }
        if (response.json.size() <= kMaxResponseBytes) SendAll(connection, response.json);
        shutdown(connection, SHUT_RDWR);
        close(connection);
      }).detach();
    } catch (...) {
      active.Release();
      const auto busy = core.Reject(RejectionCode::kBusy);
      SendAll(connection, busy.json);
      close(connection);
    }
  }
}

}  // namespace aos::kac
