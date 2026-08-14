/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <filesystem>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <core/common/tests/mocks/currentnodeinfoprovidermock.hpp>
#include <core/common/tests/mocks/ocispecmock.hpp>
#include <core/common/tests/utils/utils.hpp>
#include <core/sm/tests/mocks/instancestatusreceivermock.hpp>
#include <core/sm/tests/mocks/iteminfoprovidermock.hpp>

#include <sm/tests/mocks/systemdconnmock.hpp>

#include "runtime.hpp"

using namespace testing;

namespace aos::sm::launcher {

namespace {

constexpr auto cComponentType =
    "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider";

NodeInfo CreateNodeInfo() {
  NodeInfo nodeInfo;
  nodeInfo.mNodeID = "r61-bootstrap-node";
  nodeInfo.mOSInfo.mOS = "linux";
  nodeInfo.mCPUs.EmplaceBack();
  nodeInfo.mCPUs.Back().mArchInfo.mArchitecture = "arm64";

  return nodeInfo;
}

} // namespace

class SystemdSlotComponentRuntimeTest : public Test {
protected:
  void SetUp() override {
    mWorkingDir = std::filesystem::temp_directory_path() /
                  "r61-systemd-slot-component-test";
    std::filesystem::remove_all(mWorkingDir);

    mNodeInfo = CreateNodeInfo();
    EXPECT_CALL(mNodeInfoProvider, GetCurrentNodeInfo(_))
        .WillRepeatedly(
            DoAll(SetArgReferee<0>(mNodeInfo), Return(ErrorEnum::eNone)));
  }

  void TearDown() override { std::filesystem::remove_all(mWorkingDir); }

  RuntimeConfig CreateConfig() const {
    auto config = Poco::makeShared<Poco::JSON::Object>();
    config->set("workingDir", mWorkingDir.string());
    config->set("unit", "aos-vehicle-data-provider.service");
    config->set("layoutVersion", 1);

    return {cRuntimeSystemdSlotComponent, cComponentType, true,
            mWorkingDir.parent_path().string(), config};
  }

  Error Init(SystemdSlotComponentRuntime &runtime,
             const RuntimeConfig &config) {
    return runtime.Init(config, mNodeInfoProvider, mItemInfoProvider, mOCISpec,
                        mStatusReceiver, mSystemdConn);
  }

  NiceMock<iamclient::CurrentNodeInfoProviderMock> mNodeInfoProvider;
  NiceMock<imagemanager::ItemInfoProviderMock> mItemInfoProvider;
  NiceMock<oci::OCISpecMock> mOCISpec;
  NiceMock<InstanceStatusReceiverMock> mStatusReceiver;
  NiceMock<sm::utils::SystemdConnMock> mSystemdConn;
  std::filesystem::path mWorkingDir;
  NodeInfo mNodeInfo;
};

TEST_F(SystemdSlotComponentRuntimeTest, RequiresTheFixedBootstrapContract) {
  SystemdSlotComponentRuntime runtime;
  auto config = CreateConfig();
  config.mConfig->set("layoutVersion", 2);

  const auto err = Init(runtime, config);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, StartsWithAnEmptyPersistentStore) {
  SystemdSlotComponentRuntime runtime;
  auto err = Init(runtime, CreateConfig());
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  ASSERT_TRUE(runtime.Start().IsNone());

  RuntimeInfo info;
  ASSERT_TRUE(runtime.GetRuntimeInfo(info).IsNone());
  EXPECT_EQ(info.mRuntimeType, String(cComponentType));
  EXPECT_EQ(info.mArchInfo.mArchitecture, String("arm64"));
  EXPECT_EQ(info.mMaxInstances, 1U);
  EXPECT_TRUE(std::filesystem::is_directory(mWorkingDir / "slots"));
  EXPECT_TRUE(std::filesystem::is_directory(mWorkingDir / "state"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));

  EXPECT_TRUE(runtime.Stop().IsNone());
}

TEST_F(SystemdSlotComponentRuntimeTest,
       RejectsActivationBeforeAtomicLifecycleExists) {
  SystemdSlotComponentRuntime runtime;
  ASSERT_TRUE(Init(runtime, CreateConfig()).IsNone());
  ASSERT_TRUE(runtime.Start().IsNone());

  RuntimeInfo info;
  ASSERT_TRUE(runtime.GetRuntimeInfo(info).IsNone());

  InstanceInfo instance;
  static_cast<InstanceIdent &>(instance) =
      InstanceIdent{"vehicle-data-provider", "aos-vm-main", 0,
                    UpdateItemTypeEnum::eComponent};
  instance.mVersion = "0.2.0";
  instance.mManifestDigest = "sha256:r61bootstrap";
  instance.mRuntimeID = info.mRuntimeID;

  EXPECT_CALL(mStatusReceiver, OnInstancesStatusesReceived(_)).Times(1);

  InstanceStatus status;
  const auto err = runtime.StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eNotSupported))
      << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eFailed);
  EXPECT_EQ(status.mRuntimeID, info.mRuntimeID);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_TRUE(runtime.Reboot().Is(ErrorEnum::eNotSupported));
}

} // namespace aos::sm::launcher
