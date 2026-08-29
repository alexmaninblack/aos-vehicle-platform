// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

#include <openssl/evp.h>
#include <openssl/rand.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <sstream>

namespace aos::kac {
namespace {

constexpr std::string_view kJwtHeader = R"({"alg":"RS256","typ":"JWT"})";

std::string BytesAsString(const std::vector<std::uint8_t>& bytes) {
  return std::string(reinterpret_cast<const char*>(bytes.data()), bytes.size());
}

}  // namespace

bool TimeGate::Trusted(const Clock& clock) {
  if (!clock.SynchronizedThisBoot()) {
    Reset();
    return false;
  }
  const auto wall = clock.RealtimeSeconds();
  const auto boot = clock.BoottimeSeconds();
  if (!stable_since_boot_) {
    stable_since_boot_ = boot;
    baseline_wall_ = wall;
    baseline_boot_ = boot;
    return false;
  }
  if (boot < *stable_since_boot_) {
    Reset();
    return false;
  }
  const auto wall_elapsed = wall - *baseline_wall_;
  const auto boot_elapsed = boot - *baseline_boot_;
  if (std::llabs(wall_elapsed - boot_elapsed) > kMaximumClockDeviationSeconds) {
    Reset();
    return false;
  }
  return boot - *stable_since_boot_ >= kStableWindowSeconds;
}

void TimeGate::Reset() {
  stable_since_boot_.reset();
  baseline_wall_.reset();
  baseline_boot_.reset();
}

std::string RejectionCodeName(RejectionCode code) {
  switch (code) {
    case RejectionCode::kInvalidRequest: return "INVALID_REQUEST";
    case RejectionCode::kDenied: return "DENIED";
    case RejectionCode::kPolicyUnsupported: return "POLICY_UNSUPPORTED";
    case RejectionCode::kIamUnavailable: return "IAM_UNAVAILABLE";
    case RejectionCode::kSignerUnavailable: return "SIGNER_UNAVAILABLE";
    case RejectionCode::kTimeUntrusted: return "TIME_UNTRUSTED";
    case RejectionCode::kBusy: return "BUSY";
    case RejectionCode::kInternalError: return "INTERNAL_ERROR";
  }
  return "INTERNAL_ERROR";
}

bool IsRetryable(RejectionCode code) {
  return code == RejectionCode::kIamUnavailable ||
         code == RejectionCode::kSignerUnavailable ||
         code == RejectionCode::kTimeUntrusted || code == RejectionCode::kBusy;
}

TokenBucket::TokenBucket(double capacity, double per_minute, double now_seconds)
    : tokens_(capacity), capacity_(capacity), per_second_(per_minute / 60.0),
      updated_seconds_(now_seconds) {}

bool TokenBucket::CanConsume(double now_seconds) {
  if (now_seconds < updated_seconds_) return false;
  tokens_ = std::min(
      capacity_, tokens_ + (now_seconds - updated_seconds_) * per_second_);
  updated_seconds_ = now_seconds;
  return tokens_ >= 1.0;
}

bool TokenBucket::Consume(double now_seconds) {
  if (!CanConsume(now_seconds)) return false;
  tokens_ -= 1.0;
  return true;
}

bool ConcurrencyGate::TryAcquire() {
  unsigned current = active_.load();
  while (current < maximum_) {
    if (active_.compare_exchange_weak(current, current + 1U)) return true;
  }
  return false;
}

void ConcurrencyGate::Release() {
  unsigned current = active_.load();
  while (current != 0U) {
    if (active_.compare_exchange_weak(current, current - 1U)) return;
  }
}

std::string Base64Url(std::string_view bytes) {
  if (bytes.empty()) return {};
  std::string output(4U * ((bytes.size() + 2U) / 3U), '\0');
  const int encoded = EVP_EncodeBlock(
      reinterpret_cast<unsigned char*>(output.data()),
      reinterpret_cast<const unsigned char*>(bytes.data()),
      static_cast<int>(bytes.size()));
  if (encoded < 0) return {};
  output.resize(static_cast<std::size_t>(encoded));
  while (!output.empty() && output.back() == '=') output.pop_back();
  std::replace(output.begin(), output.end(), '+', '-');
  std::replace(output.begin(), output.end(), '/', '_');
  return output;
}

bool IsExactVssLeafPath(std::string_view path) {
  if (path.empty() || path.size() > kMaxPathBytes || path.front() == '.' ||
      path.back() == '.' || path.find('*') != std::string_view::npos) {
    return false;
  }
  bool start = true;
  for (const unsigned char value : path) {
    if (value == '.') {
      if (start) return false;
      start = true;
      continue;
    }
    if (start) {
      if (!(std::isalpha(value) || value == '_')) return false;
      start = false;
    } else if (!(std::isalnum(value) || value == '_')) {
      return false;
    }
  }
  return !start;
}

std::optional<std::vector<std::string>> MapPermissions(
    const std::vector<Permission>& permissions) {
  if (permissions.empty() || permissions.size() > kMaxPermissions) return std::nullopt;
  std::vector<std::string> scopes;
  std::vector<std::string_view> paths;
  scopes.reserve(permissions.size());
  paths.reserve(permissions.size());
  for (const auto& permission : permissions) {
    if (!IsExactVssLeafPath(permission.path)) return std::nullopt;
    paths.emplace_back(permission.path);
    if (permission.mode == "r") {
      scopes.emplace_back("read:" + permission.path);
    } else if (permission.mode == "rw") {
      scopes.emplace_back("actuate:" + permission.path);
    } else {
      return std::nullopt;
    }
  }
  std::sort(paths.begin(), paths.end());
  if (std::adjacent_find(paths.begin(), paths.end()) != paths.end()) return std::nullopt;
  std::sort(scopes.begin(), scopes.end());
  if (std::adjacent_find(scopes.begin(), scopes.end()) != scopes.end()) return std::nullopt;
  return scopes;
}

std::string Core::CorrelationId() {
  std::array<unsigned char, 16> random{};
  if (RAND_bytes(random.data(), static_cast<int>(random.size())) != 1) {
    return "kac-" + std::to_string(correlation_counter_.fetch_add(1U) + 1U);
  }
  return "kac-" + Base64Url(std::string_view(
                      reinterpret_cast<const char*>(random.data()), random.size()));
}

Response Core::Reject(RejectionCode code) {
  const bool retryable = IsRetryable(code);
  std::ostringstream output;
  output << "{\"protocol\":\"" << kProtocol
         << "\",\"status\":\"rejected\",\"correlationId\":\""
         << CorrelationId() << "\",\"code\":\"" << RejectionCodeName(code)
         << "\",\"retryable\":" << (retryable ? "true" : "false") << "}\n";
  return Response{output.str(), retryable};
}

bool Core::TrustedTime() {
  std::lock_guard<std::mutex> guard(time_lock_);
  return time_gate_.Trusted(clock_);
}

Response Core::Ready() {
  if (!TrustedTime()) return Reject(RejectionCode::kTimeUntrusted);
  if (!signer_.Ready()) return Reject(RejectionCode::kSignerUnavailable);
  std::ostringstream output;
  output << "{\"protocol\":\"" << kProtocol
         << "\",\"status\":\"ready\",\"correlationId\":\""
         << CorrelationId() << "\"}\n";
  return Response{output.str(), false};
}

Response Core::Issue(std::string_view secret) {
  if (!TrustedTime()) return Reject(RejectionCode::kTimeUntrusted);
  if (!signer_.Ready()) return Reject(RejectionCode::kSignerUnavailable);

  const auto iam = iam_.GetPermissions(secret);
  if (iam.status == IamResult::Status::kUnavailable) {
    return Reject(RejectionCode::kIamUnavailable);
  }
  if (iam.status == IamResult::Status::kUnsupported) {
    return Reject(RejectionCode::kPolicyUnsupported);
  }
  if (iam.status == IamResult::Status::kDenied || iam.decision.instance_subject.empty()) {
    return Reject(RejectionCode::kDenied);
  }
  if (!TrustedTime()) return Reject(RejectionCode::kTimeUntrusted);
  const auto scopes = MapPermissions(iam.decision.permissions);
  if (!scopes) return Reject(RejectionCode::kPolicyUnsupported);

  std::ostringstream scope;
  for (std::size_t index = 0; index < scopes->size(); ++index) {
    if (index != 0) scope << ' ';
    scope << (*scopes)[index];
  }
  const auto issued_at = clock_.RealtimeSeconds();
  const auto expires_at = issued_at + kJwtTtlSeconds;
  const auto renew_after = issued_at + kRenewAfterSeconds;
  std::ostringstream payload;
  payload << "{\"sub\":\"" << JsonEscape(iam.decision.instance_subject)
          << "\",\"iss\":\"" << kIssuer << "\",\"aud\":[\"" << kAudience
          << "\"],\"iat\":" << issued_at << ",\"exp\":" << expires_at
          << ",\"scope\":\"" << JsonEscape(scope.str()) << "\"}";

  const std::string signing_input = Base64Url(kJwtHeader) + "." + Base64Url(payload.str());
  const auto sign_started = clock_.BoottimeSeconds();
  const auto signature = signer_.Sign(signing_input);
  const auto sign_finished = clock_.BoottimeSeconds();
  if (!signature || sign_finished < sign_started ||
      sign_finished - sign_started > kSignOperationTimeoutSeconds) {
    return Reject(RejectionCode::kSignerUnavailable);
  }
  const std::string token = signing_input + "." + Base64Url(BytesAsString(*signature));
  if (token.size() > kMaxJwtBytes) return Reject(RejectionCode::kPolicyUnsupported);

  std::ostringstream output;
  output << "{\"protocol\":\"" << kProtocol
         << "\",\"status\":\"issued\",\"correlationId\":\""
         << CorrelationId() << "\",\"token\":\"" << token
         << "\",\"expiresAtUnixSeconds\":" << expires_at
         << ",\"renewAfterUnixSeconds\":" << renew_after << "}\n";
  if (output.str().size() > kMaxResponseBytes) {
    return Reject(RejectionCode::kPolicyUnsupported);
  }
  return Response{output.str(), false};
}

Response Core::Handle(const Request& request) {
  if (request.operation == Operation::kStatus) return Ready();
  return Issue(request.aos_secret);
}

std::int64_t SystemClock::RealtimeSeconds() const {
  struct timespec value {};
  if (clock_gettime(CLOCK_REALTIME, &value) != 0) return 0;
  return value.tv_sec;
}

std::int64_t SystemClock::BoottimeSeconds() const {
  struct timespec value {};
  if (clock_gettime(CLOCK_BOOTTIME, &value) != 0) return 0;
  return value.tv_sec;
}

bool SystemClock::SynchronizedThisBoot() const {
  std::ifstream synchronized("/run/systemd/timesync/synchronized");
  return synchronized.good();
}

}  // namespace aos::kac
