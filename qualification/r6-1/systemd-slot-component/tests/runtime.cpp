/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <core/common/tests/mocks/currentnodeinfoprovidermock.hpp>
#include <core/common/tests/utils/utils.hpp>

#include "runtime.hpp"

using namespace testing;

namespace aos::sm::launcher {

namespace {

constexpr auto cComponentType =
    "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider";

NodeInfo CreateNodeInfo() {
  NodeInfo nodeInfo;

  nodeInfo.mNodeID = "r61-qualification-node";
  nodeInfo.mOSInfo.mOS = "linux";
  nodeInfo.mCPUs.EmplaceBack();
  nodeInfo.mCPUs.Back().mArchInfo.mArchitecture = "arm64";

  return nodeInfo;
}

RuntimeConfig CreateConfig() {
  auto configObject = Poco::makeShared<Poco::JSON::Object>();
  configObject->set("qualificationMode", true);

  return RuntimeConfig{cRuntimeSystemdSlotComponent, cComponentType, true,
                       "/var/aos/workdirs/sm/runtimes/systemd-slot-component",
                       configObject};
}

InstanceInfo CreateInstance(const RuntimeInfo &runtimeInfo) {
  InstanceInfo instance;

  static_cast<InstanceIdent &>(instance) = InstanceIdent{
      "vehicle-data-provider", "oem", 0, UpdateItemTypeEnum::eService};
  instance.mVersion = "0.1.1";
  instance.mManifestDigest = "sha256:r61qualification";
  instance.mRuntimeID = runtimeInfo.mRuntimeID;

  return instance;
}

} // namespace

class SystemdSlotComponentRuntimeTest : public Test {
protected:
  void SetUp() override {
    mNodeInfo = CreateNodeInfo();
    EXPECT_CALL(mNodeInfoProvider, GetCurrentNodeInfo(_))
        .WillRepeatedly(
            DoAll(SetArgReferee<0>(mNodeInfo), Return(ErrorEnum::eNone)));
  }

  NiceMock<iamclient::CurrentNodeInfoProviderMock> mNodeInfoProvider;
  NodeInfo mNodeInfo;
};

TEST_F(SystemdSlotComponentRuntimeTest,
       RequiresExplicitComponentQualificationConfiguration) {
  SystemdSlotComponentRuntime runtime;
  auto config = CreateConfig();

  config.isComponent = false;

  const auto err = runtime.Init(config, mNodeInfoProvider);

  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, ReportsExactRuntimeInfo) {
  SystemdSlotComponentRuntime runtime;
  auto err = runtime.Init(CreateConfig(), mNodeInfoProvider);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);

  RuntimeInfo info;
  err = runtime.GetRuntimeInfo(info);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);

  EXPECT_EQ(info.mRuntimeType, String(cComponentType));
  EXPECT_EQ(info.mArchInfo.mArchitecture, String("arm64"));
  EXPECT_EQ(info.mOSInfo.mOS, String("linux"));
  EXPECT_EQ(info.mMaxInstances, 1U);
  EXPECT_FALSE(info.mRuntimeID.IsEmpty());
}

TEST_F(SystemdSlotComponentRuntimeTest,
       TracesOneNonRebootingInstanceLifecycle) {
  SystemdSlotComponentRuntime runtime;
  auto err = runtime.Init(CreateConfig(), mNodeInfoProvider);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);

  RuntimeInfo info;
  ASSERT_TRUE(runtime.GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info);

  err = runtime.Start();
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);

  InstanceStatus activeStatus;
  err = runtime.StartInstance(instance, activeStatus);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(activeStatus.mState, InstanceStateEnum::eActive);
  EXPECT_EQ(activeStatus.mRuntimeID, info.mRuntimeID);

  monitoring::InstanceMonitoringData monitoringData;
  err = runtime.GetInstanceMonitoringData(instance, monitoringData);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(monitoringData.mRuntimeID, info.mRuntimeID);

  InstanceStatus inactiveStatus;
  err = runtime.StopInstance(instance, inactiveStatus);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(inactiveStatus.mState, InstanceStateEnum::eInactive);

  err = runtime.Stop();
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_TRUE(runtime.Reboot().Is(ErrorEnum::eNotSupported));

  const std::vector<std::string> expectedTrace{"init", "runtime-start",
                                               "instance-start",
                                               "instance-stop", "runtime-stop"};
  EXPECT_EQ(runtime.GetTrace(), expectedTrace);
}

} // namespace aos::sm::launcher
