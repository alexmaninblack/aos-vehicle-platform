// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using aos::kac::IamDecision;
using aos::kac::IamResult;
using aos::kac::Permission;

void Check(bool value, const char* message) {
  if (!value) throw std::runtime_error(message);
}

class FakeClock final : public aos::kac::Clock {
 public:
  std::int64_t RealtimeSeconds() const override { return wall; }
  std::int64_t BoottimeSeconds() const override { return boot; }
  bool SynchronizedThisBoot() const override { return synchronized; }
  std::int64_t wall{1'800'000'000};
  std::int64_t boot{100};
  bool synchronized{true};
};

class FakeIam final : public aos::kac::IamClient {
 public:
  IamResult GetPermissions(std::string_view secret) override {
    ++calls;
    last_secret = std::string(secret);
    return result;
  }
  IamResult result{IamResult::Status::kAllowed,
                   IamDecision{"brake:subject:0",
                               {{"Vehicle.Speed", "r"}, {"Vehicle.Brake.Pedal", "rw"}}}};
  int calls{0};
  std::string last_secret;
};

class FakeSigner final : public aos::kac::Signer {
 public:
  bool Ready() const override { return ready; }
  std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) override {
    ++calls;
    last_input = std::string(input);
    if (clock != nullptr) clock->boot += elapsed_seconds;
    if (!ready || fail) return std::nullopt;
    return std::vector<std::uint8_t>(signature_size, 0x5aU);
  }
  bool ready{true};
  bool fail{false};
  FakeClock* clock{nullptr};
  std::int64_t elapsed_seconds{0};
  std::size_t signature_size{256U};
  int calls{0};
  std::string last_input;
};

void EstablishTime(aos::kac::Core& core, FakeClock& clock) {
  const auto first = core.Handle({aos::kac::Operation::kStatus, {}});
  Check(first.json.find("TIME_UNTRUSTED") != std::string::npos, "initial stable gate");
  clock.wall += 10;
  clock.boot += 10;
  const auto ready = core.Handle({aos::kac::Operation::kStatus, {}});
  Check(ready.json.find("\"status\":\"ready\"") != std::string::npos, "ready gate");
}

void TestProtocol() {
  Check(aos::kac::ParseRequestFrame(
            "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"status\"}\n")
            .has_value(),
        "status accepted");
  const auto issue = aos::kac::ParseRequestFrame(
      "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"issue\",\"aosSecret\":\"opaque\"}\n");
  Check(issue && issue->aos_secret == "opaque", "issue accepted");
  Check(!aos::kac::ParseRequestFrame(
             "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"status\",\"operation\":\"issue\"}\n"),
        "duplicate rejected");
  Check(!aos::kac::ParseRequestFrame(
             "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"status\",\"resource\":\"kuksa\"}\n"),
        "unknown rejected");
  Check(!aos::kac::ParseRequestFrame(
             "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"status\",\"aosSecret\":\"x\"}\n"),
        "status credential rejected");
  Check(!aos::kac::ParseRequestFrame(
             "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"issue\"}\n"),
        "missing credential rejected");
  Check(!aos::kac::ParseRequestFrame(
             "{\"protocol\":\"wrong\",\"operation\":\"status\"}\n"),
        "wrong protocol rejected");
  Check(!aos::kac::ParseRequestFrame(
             "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"status\"}\n{}\n"),
        "extra frame rejected");
  const std::string invalid_utf8 =
      "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"issue\",\"aosSecret\":\"" +
      std::string(1, static_cast<char>(0xff)) + "\"}\n";
  Check(!aos::kac::ParseRequestFrame(invalid_utf8), "invalid utf8 rejected");
}

void TestIamAndClaims() {
  FakeIam iam;
  FakeSigner signer;
  FakeClock clock;
  aos::kac::Core core(iam, signer, clock);
  EstablishTime(core, clock);
  const auto response = core.Handle({aos::kac::Operation::kIssue, "secret-not-logged"});
  Check(iam.calls == 1 && iam.last_secret == "secret-not-logged", "fresh IAM lookup");
  Check(signer.calls == 1, "sign once");
  const std::string expected_payload =
      R"({"sub":"brake:subject:0","iss":"aosedge-kuksa-auth-compat","aud":["kuksa.val"],"iat":1800000010,"exp":1800000310,"scope":"actuate:Vehicle.Brake.Pedal read:Vehicle.Speed"})";
  const std::string expected_input =
      aos::kac::Base64Url(R"({"alg":"RS256","typ":"JWT"})") + "." +
      aos::kac::Base64Url(expected_payload);
  Check(signer.last_input == expected_input, "pinned JWT claims");
  Check(response.json.find("\"status\":\"issued\"") != std::string::npos, "issued");
  Check(response.json.find("1800000310") != std::string::npos, "ttl exact");
  Check(response.json.find("1800000190") != std::string::npos, "renew exact");
  core.Handle({aos::kac::Operation::kIssue, "renew"});
  Check(iam.calls == 2, "renew gets fresh IAM");
}

void TestMapping() {
  auto mapped = aos::kac::MapPermissions(
      {{"Vehicle.Speed", "r"}, {"Vehicle.Brake.Pedal", "rw"}});
  Check(mapped && (*mapped)[0] == "actuate:Vehicle.Brake.Pedal" &&
            (*mapped)[1] == "read:Vehicle.Speed",
        "exact mapping");
  for (const char* mode : {"w", "provide", "create", "rx"}) {
    Check(!aos::kac::MapPermissions({{"Vehicle.Speed", mode}}), "mode rejected");
  }
  Check(!aos::kac::MapPermissions({{"Vehicle.*", "r"}}), "wildcard rejected");
  Check(!aos::kac::MapPermissions({{"Vehicle..Speed", "r"}}), "malformed rejected");
  Check(!aos::kac::MapPermissions(
            {{"Vehicle.Speed", "r"}, {"Vehicle.Speed", "rw"}}),
        "duplicate path rejected");
}

void TestEnvelopes() {
  FakeIam iam;
  FakeSigner signer;
  FakeClock clock;
  aos::kac::Core core(iam, signer, clock);
  const auto rejected = core.Reject(aos::kac::RejectionCode::kDenied);
  Check(rejected.json.find("\"retryable\":false") != std::string::npos, "terminal envelope");
  Check(rejected.json.find("secret") == std::string::npos, "redacted envelope");
  const auto busy = core.Reject(aos::kac::RejectionCode::kBusy);
  Check(busy.retryable && busy.json.find("BUSY") != std::string::npos, "retry envelope");

  iam.result = {IamResult::Status::kUnsupported, {}};
  EstablishTime(core, clock);
  const auto unsupported = core.Handle({aos::kac::Operation::kIssue, "opaque"});
  Check(unsupported.json.find("POLICY_UNSUPPORTED") != std::string::npos,
        "oversize IAM authority envelope");
}

void TestTime() {
  FakeIam iam;
  FakeSigner signer;
  FakeClock clock;
  aos::kac::Core core(iam, signer, clock);
  EstablishTime(core, clock);
  clock.wall += 5;
  const auto boundary = core.Handle({aos::kac::Operation::kStatus, {}});
  Check(boundary.json.find("\"status\":\"ready\"") != std::string::npos, "+5 accepted");
  clock.wall += 1;
  const auto over = core.Handle({aos::kac::Operation::kStatus, {}});
  Check(over.json.find("TIME_UNTRUSTED") != std::string::npos, "+6 rejected");
  clock.synchronized = false;
  const auto offline_boot = core.Handle({aos::kac::Operation::kStatus, {}});
  Check(offline_boot.json.find("TIME_UNTRUSTED") != std::string::npos, "cold offline denied");
}

void TestRestart() {
  FakeIam iam;
  FakeSigner signer;
  FakeClock clock;
  aos::kac::Core restarted(iam, signer, clock);
  const auto response = restarted.Handle({aos::kac::Operation::kIssue, "new-instance-secret"});
  Check(response.json.find("TIME_UNTRUSTED") != std::string::npos, "restart empty time state");
  Check(iam.calls == 0, "no cached authority");
}

void TestSignerFailure() {
  FakeIam iam;
  FakeSigner signer;
  FakeClock clock;
  signer.ready = false;
  aos::kac::Core core(iam, signer, clock);
  core.Handle({aos::kac::Operation::kStatus, {}});
  clock.wall += 10;
  clock.boot += 10;
  const auto response = core.Handle({aos::kac::Operation::kIssue, "opaque"});
  Check(response.json.find("SIGNER_UNAVAILABLE") != std::string::npos, "protected signer required");
  Check(iam.calls == 0, "signer fail closed before IAM");

  FakeSigner slow_signer;
  FakeClock slow_clock;
  slow_signer.clock = &slow_clock;
  slow_signer.elapsed_seconds = 4;
  aos::kac::Core slow_core(iam, slow_signer, slow_clock);
  EstablishTime(slow_core, slow_clock);
  const auto slow = slow_core.Handle({aos::kac::Operation::kIssue, "opaque"});
  Check(slow.json.find("SIGNER_UNAVAILABLE") != std::string::npos,
        "sign operation deadline");

  FakeSigner boundary_signer;
  FakeClock boundary_clock;
  boundary_signer.clock = &boundary_clock;
  boundary_signer.elapsed_seconds = 3;
  aos::kac::Core boundary_core(iam, boundary_signer, boundary_clock);
  EstablishTime(boundary_core, boundary_clock);
  const auto boundary = boundary_core.Handle({aos::kac::Operation::kIssue, "opaque"});
  Check(boundary.json.find("\"status\":\"issued\"") != std::string::npos,
        "sign deadline boundary");

  FakeSigner oversize_signer;
  FakeClock oversize_clock;
  oversize_signer.signature_size = aos::kac::kMaxJwtBytes;
  aos::kac::Core oversize_core(iam, oversize_signer, oversize_clock);
  EstablishTime(oversize_core, oversize_clock);
  const auto oversize = oversize_core.Handle({aos::kac::Operation::kIssue, "opaque"});
  Check(oversize.json.find("POLICY_UNSUPPORTED") != std::string::npos,
        "oversize JWT rejected without trimming");
}

void TestOfflineLocal() {
  FakeIam iam;
  FakeSigner signer;
  FakeClock clock;
  aos::kac::Core core(iam, signer, clock);
  EstablishTime(core, clock);
  const auto response = core.Handle({aos::kac::Operation::kIssue, "local-secret"});
  Check(response.json.find("\"status\":\"issued\"") != std::string::npos,
        "no cloud/backend input");
}

void TestBounds() {
  const std::string prefix =
      "{\"protocol\":\"aos-kuksa-auth-compat/v1\",\"operation\":\"issue\",\"aosSecret\":\"x\"";
  const std::string suffix = "}\n";
  std::string maximum_frame = prefix;
  maximum_frame.append(aos::kac::kMaxRequestBytes - prefix.size() - suffix.size(), ' ');
  maximum_frame += suffix;
  Check(maximum_frame.size() == aos::kac::kMaxRequestBytes &&
            aos::kac::ParseRequestFrame(maximum_frame).has_value(),
        "maximum frame accepted");
  maximum_frame.insert(maximum_frame.size() - suffix.size(), 1U, ' ');
  Check(!aos::kac::ParseRequestFrame(maximum_frame), "frame max plus one rejected");
  std::vector<Permission> permissions;
  for (std::size_t index = 0; index < aos::kac::kMaxPermissions; ++index) {
    permissions.push_back({"Vehicle.Signal" + std::to_string(index), "r"});
  }
  Check(aos::kac::MapPermissions(permissions).has_value(), "64 permissions accepted");
  permissions.push_back({"Vehicle.Signal64", "r"});
  Check(!aos::kac::MapPermissions(permissions), "65 permissions rejected");
  Check(aos::kac::IsExactVssLeafPath("V." + std::string(510, 'A')), "512-byte path accepted");
  Check(!aos::kac::IsExactVssLeafPath("V." + std::string(511, 'A')), "513-byte path rejected");
  Check(aos::kac::IsRetryable(aos::kac::RejectionCode::kIamUnavailable), "retryable IAM");
  Check(!aos::kac::IsRetryable(aos::kac::RejectionCode::kInternalError), "terminal internal");

  aos::kac::TokenBucket peer_rate(4.0, 12.0, 100.0);
  for (int count = 0; count < 4; ++count) {
    Check(peer_rate.Consume(100.0), "peer burst accepted");
  }
  Check(!peer_rate.Consume(100.0), "peer burst plus one rejected");
  Check(!peer_rate.Consume(104.999), "peer refill before boundary rejected");
  Check(peer_rate.Consume(105.0), "peer refill boundary accepted");

  aos::kac::TokenBucket global_rate(10.0, 30.0, 200.0);
  for (int count = 0; count < 10; ++count) {
    Check(global_rate.Consume(200.0), "global burst accepted");
  }
  Check(!global_rate.Consume(200.0), "global burst plus one rejected");
  Check(!global_rate.Consume(201.999), "global refill before boundary rejected");
  Check(global_rate.Consume(202.0), "global refill boundary accepted");

  aos::kac::ConcurrencyGate concurrency(4);
  for (int count = 0; count < 4; ++count) {
    Check(concurrency.TryAcquire(), "concurrency slot accepted");
  }
  Check(!concurrency.TryAcquire(), "fifth concurrent request rejected");
  concurrency.Release();
  Check(concurrency.TryAcquire(), "released concurrency slot reused");
}

void TestPackageSeam() {
  Check(aos::kac::kFixedResource == "kuksa", "fixed resource");
  Check(aos::kac::kJwtTtlSeconds == 300 && aos::kac::kRenewAfterSeconds == 180,
        "migration contract constants");
}

}  // namespace

int main() {
  const std::vector<std::pair<const char*, void (*)()>> tests = {
      {"UT-KAC-001", TestProtocol},       {"UT-KAC-002", TestIamAndClaims},
      {"UT-KAC-003", TestMapping},        {"UT-KAC-004", TestEnvelopes},
      {"UT-KAC-005", TestTime},           {"UT-KAC-006", TestRestart},
      {"UT-KAC-007", TestSignerFailure},  {"UT-KAC-008", TestOfflineLocal},
      {"UT-KAC-009", TestBounds},         {"UT-KAC-010", TestPackageSeam},
  };
  try {
    for (const auto& [name, test] : tests) {
      test();
      std::cout << name << " PASS\n";
    }
  } catch (const std::exception& error) {
    std::cerr << "KAC test failure\n";
    return 1;
  }
  std::cout << tests.size() << " KAC tests passed\n";
  return 0;
}
