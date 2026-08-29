/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <unistd.h>

#include "vissvehiclestate.hpp"

namespace aos::sm::launcher {

namespace {

class FakeVissTransport final : public Viss31MtlsTransportItf {
public:
  Error ReadSnapshot(const Viss31MtlsConfig &,
                     const std::array<const char *, 10> &,
                     Viss31Snapshot &snapshot,
                     std::chrono::milliseconds) override {
    snapshot = mSnapshot;
    return mError;
  }

  void Cancel() override { mCanceled = true; }

  Viss31Snapshot mSnapshot;
  Error mError;
  bool mCanceled{};
};

void Write(const std::filesystem::path &path, const std::string &value) {
  std::ofstream stream(path);
  ASSERT_TRUE(stream.is_open());
  stream << value;
}

Viss31MtlsConfig CreateConfig(const std::filesystem::path &directory) {
  Viss31MtlsConfig config;
  config.mEndpoint = "wss://10.0.0.1:6443";
  config.mServerName = "127.0.0.1";
  config.mRole = "PLATFORM_UPDATE_RUNTIME";
  config.mExpectedNodeID = "node-1";
  config.mCACredential = directory / "ca";
  config.mCertificateCredential = directory / "certificate";
  config.mPrivateKeyCredential = directory / "key";
  config.mBindingCredential = directory / "binding";
  Write(config.mCACredential, "test-ca");
  Write(config.mCertificateCredential, "test-certificate");
  Write(config.mPrivateKeyCredential, "test-key");
  Write(config.mBindingCredential,
        R"({"schemaVersion":1,"unitId":"unit-1","nodeId":"node-1","role":"PLATFORM_UPDATE_RUNTIME","clientCertificateSha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","assignmentGeneration":1})");
  return config;
}

void FillSafeSnapshot(Viss31Snapshot &snapshot,
                      std::chrono::steady_clock::time_point source,
                      std::chrono::steady_clock::time_point acquired) {
  snapshot.mValues = {
      {cSafeStopPaths[0], "101"}, {cSafeStopPaths[1], "SAFE_STOP"},
      {cSafeStopPaths[2], "STABLE"}, {cSafeStopPaths[3], "7"},
      {cSafeStopPaths[4], "3"}, {cSafeStopPaths[5], "false"},
      {cSafeStopPaths[6], "false"}, {cSafeStopPaths[7], "0.2"},
      {cSafeStopPaths[8], "0.0"}, {cSafeStopPaths[9], "100.0"},
  };
  snapshot.mSourceObservedAt = source;
  snapshot.mAcquiredAt = acquired;
}

} // namespace

TEST(Viss31VehicleStateProviderTest,
     PreservesSourceAndAcquisitionTimesForThePurePolicy) {
  const auto directory = std::filesystem::temp_directory_path() /
                         ("viss-state-provider-" + std::to_string(getpid()));
  std::filesystem::remove_all(directory);
  std::filesystem::create_directories(directory);
  const auto config = CreateConfig(directory);
  const auto acquired = std::chrono::steady_clock::now();
  const auto source = acquired - std::chrono::milliseconds{100};
  FakeVissTransport transport;
  FillSafeSnapshot(transport.mSnapshot, source, acquired);
  Viss31MtlsVehicleStateProvider provider(&transport);
  ASSERT_TRUE(provider.Init(config).IsNone());

  VehicleStateFrame frame;
  ASSERT_TRUE(provider.ReadFrame(frame, std::chrono::milliseconds{250})
                  .IsNone());
  EXPECT_EQ(frame.mFrameID, 101U);
  EXPECT_EQ(frame.mSourceObservedAt, source);
  EXPECT_EQ(frame.mAcquiredAt, acquired);
  EXPECT_EQ(frame.mActiveMode, "SAFE_STOP");
  EXPECT_EQ(frame.mBrakePercent, 100.0);

  provider.Cancel();
  EXPECT_TRUE(transport.mCanceled);
  std::filesystem::remove_all(directory);
}

TEST(Viss31VehicleStateProviderTest, RejectsWidenedSnapshotsAndWrongBindings) {
  const auto directory = std::filesystem::temp_directory_path() /
                         ("viss-state-provider-invalid-" +
                          std::to_string(getpid()));
  std::filesystem::remove_all(directory);
  std::filesystem::create_directories(directory);
  auto config = CreateConfig(directory);
  const auto now = std::chrono::steady_clock::now();
  FakeVissTransport transport;
  FillSafeSnapshot(transport.mSnapshot, now, now);
  transport.mSnapshot.mValues.emplace("Vehicle.Unreviewed", "1");
  Viss31MtlsVehicleStateProvider provider(&transport);
  ASSERT_TRUE(provider.Init(config).IsNone());
  VehicleStateFrame frame;
  EXPECT_TRUE(provider.ReadFrame(frame, std::chrono::milliseconds{250})
                  .Is(ErrorEnum::eInvalidArgument));

  FillSafeSnapshot(transport.mSnapshot, now, now);
  Write(config.mBindingCredential,
        R"({"schemaVersion":1,"unitId":"unit-1","nodeId":"another-node","role":"PLATFORM_UPDATE_RUNTIME","clientCertificateSha256":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef","assignmentGeneration":1})");
  EXPECT_TRUE(provider.ReadFrame(frame, std::chrono::milliseconds{250})
                  .Is(ErrorEnum::eInvalidArgument));
  std::filesystem::remove_all(directory);
}

} // namespace aos::sm::launcher
