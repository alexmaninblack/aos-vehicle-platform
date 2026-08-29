// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <atomic>
#include <cstdint>
#include <map>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aos::kac {

inline constexpr std::string_view kProtocol = "aos-kuksa-auth-compat/v1";
inline constexpr std::string_view kFixedResource = "kuksa";
inline constexpr std::string_view kIssuer = "aosedge-kuksa-auth-compat";
inline constexpr std::string_view kAudience = "kuksa.val";
inline constexpr std::size_t kMaxRequestBytes = 16U * 1024U;
inline constexpr std::size_t kMaxResponseBytes = 32U * 1024U;
inline constexpr std::size_t kMaxJwtBytes = 16U * 1024U;
inline constexpr std::size_t kMaxPermissions = 64U;
inline constexpr std::size_t kMaxPathBytes = 512U;
inline constexpr std::int64_t kJwtTtlSeconds = 300;
inline constexpr std::int64_t kRenewAfterSeconds = 180;
inline constexpr std::int64_t kStableWindowSeconds = 10;
inline constexpr std::int64_t kMaximumClockDeviationSeconds = 5;
inline constexpr std::int64_t kSignOperationTimeoutSeconds = 3;

enum class Operation { kStatus, kIssue };

enum class RejectionCode {
  kInvalidRequest,
  kDenied,
  kPolicyUnsupported,
  kIamUnavailable,
  kSignerUnavailable,
  kTimeUntrusted,
  kBusy,
  kInternalError,
};

struct Request {
  Operation operation{Operation::kStatus};
  std::string aos_secret;
};

struct Permission {
  std::string path;
  std::string mode;
};

struct IamDecision {
  std::string instance_subject;
  std::vector<Permission> permissions;
};

struct IamResult {
  enum class Status { kAllowed, kDenied, kUnsupported, kUnavailable }
      status{Status::kUnavailable};
  IamDecision decision;
};

class IamClient {
 public:
  virtual ~IamClient() = default;
  virtual IamResult GetPermissions(std::string_view secret) = 0;
};

class Signer {
 public:
  virtual ~Signer() = default;
  virtual bool Ready() const = 0;
  virtual std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) = 0;
};

class Clock {
 public:
  virtual ~Clock() = default;
  virtual std::int64_t RealtimeSeconds() const = 0;
  virtual std::int64_t BoottimeSeconds() const = 0;
  virtual bool SynchronizedThisBoot() const = 0;
};

class TimeGate {
 public:
  bool Trusted(const Clock& clock);
  void Reset();

 private:
  std::optional<std::int64_t> stable_since_boot_;
  std::optional<std::int64_t> baseline_wall_;
  std::optional<std::int64_t> baseline_boot_;
};

struct Response {
  std::string json;
  bool retryable{false};
};

class TokenBucket {
 public:
  TokenBucket(double capacity, double per_minute, double now_seconds);
  bool CanConsume(double now_seconds);
  bool Consume(double now_seconds);

 private:
  double tokens_;
  double capacity_;
  double per_second_;
  double updated_seconds_;
};

class ConcurrencyGate {
 public:
  explicit ConcurrencyGate(unsigned maximum) : maximum_(maximum) {}
  bool TryAcquire();
  void Release();

 private:
  const unsigned maximum_;
  std::atomic<unsigned> active_{0};
};

std::optional<Request> ParseRequestFrame(std::string_view frame);
std::string RejectionCodeName(RejectionCode code);
bool IsRetryable(RejectionCode code);
std::string JsonEscape(std::string_view value);
std::string Base64Url(std::string_view bytes);
bool IsExactVssLeafPath(std::string_view path);
std::optional<std::vector<std::string>> MapPermissions(
    const std::vector<Permission>& permissions);

class Core {
 public:
  Core(IamClient& iam, Signer& signer, Clock& clock)
      : iam_(iam), signer_(signer), clock_(clock) {}

  Response Handle(const Request& request);
  Response Reject(RejectionCode code);

 private:
  std::string CorrelationId();
  bool TrustedTime();
  Response Ready();
  Response Issue(std::string_view secret);

  IamClient& iam_;
  Signer& signer_;
  Clock& clock_;
  TimeGate time_gate_;
  std::atomic<std::uint64_t> correlation_counter_{0};
  std::mutex time_lock_;
};

class SystemClock final : public Clock {
 public:
  std::int64_t RealtimeSeconds() const override;
  std::int64_t BoottimeSeconds() const override;
  bool SynchronizedThisBoot() const override;
};

class GrpcIamClient final : public IamClient {
 public:
  GrpcIamClient();
  ~GrpcIamClient() override;
  GrpcIamClient(const GrpcIamClient&) = delete;
  GrpcIamClient& operator=(const GrpcIamClient&) = delete;
  IamResult GetPermissions(std::string_view secret) override;

 private:
  class Impl;
  Impl* impl_;
};

class Pkcs11Signer final : public Signer {
 public:
  Pkcs11Signer();
  ~Pkcs11Signer() override;
  Pkcs11Signer(const Pkcs11Signer&) = delete;
  Pkcs11Signer& operator=(const Pkcs11Signer&) = delete;
  bool Ready() const override;
  std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) override;
  bool Verify(std::string_view input, const std::vector<std::uint8_t>& signature) const;
  std::optional<std::string> PublicKeyPem() const;

 private:
  class Impl;
  Impl* impl_;
};

int RunServer(Core& core);

}  // namespace aos::kac
