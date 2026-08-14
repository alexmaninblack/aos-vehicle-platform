/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <filesystem>
#include <fstream>
#include <sys/stat.h>
#include <unistd.h>

#include <gmock/gmock.h>
#include <gtest/gtest.h>

#include <core/common/tests/mocks/currentnodeinfoprovidermock.hpp>
#include <core/common/tests/mocks/ocispecmock.hpp>
#include <core/common/tests/utils/utils.hpp>
#include <core/sm/tests/mocks/instancestatusreceivermock.hpp>
#include <core/sm/tests/mocks/iteminfoprovidermock.hpp>

#include <sm/tests/mocks/systemdconnmock.hpp>

#include "providerarchive.hpp"
#include "providerprofile.hpp"
#include "runtime.hpp"

using namespace testing;

namespace aos::sm::launcher {

namespace {

constexpr auto cComponentType =
    "aos-vm-1.0.0-main-qemuarm64-vehicle-data-provider";

class ProviderProfileMock : public ProviderProfileItf {
public:
  MOCK_METHOD(Error, OfflineSelfTest, (const std::filesystem::path &),
              (override));
  MOCK_METHOD(Error, MarkUnavailable, (), (override));
  MOCK_METHOD(Error, StopProvider, (), (override));
  MOCK_METHOD(Error, StartProvider, (), (override));
  MOCK_METHOD(Error, CheckHealth, (), (override));
};

NodeInfo CreateNodeInfo() {
  NodeInfo nodeInfo;
  nodeInfo.mNodeID = "r61-bootstrap-node";
  nodeInfo.mOSInfo.mOS = "linux";
  nodeInfo.mCPUs.EmplaceBack();
  nodeInfo.mCPUs.Back().mArchInfo.mArchitecture = "arm64";
  return nodeInfo;
}

void WriteFile(const std::filesystem::path &path, const std::string &content,
               std::filesystem::perms permissions) {
  std::filesystem::create_directories(path.parent_path());
  std::ofstream stream(path);
  ASSERT_TRUE(stream.is_open());
  stream << content;
  stream.close();
  std::filesystem::permissions(path, permissions,
                               std::filesystem::perm_options::replace);
}

} // namespace

class SystemdSlotComponentRuntimeTest : public Test {
protected:
  void SetUp() override {
    mWorkingDir =
        std::filesystem::temp_directory_path() /
        ("r61-systemd-slot-component-test-" + std::to_string(getpid()));
    std::filesystem::remove_all(mWorkingDir);

    mNodeInfo = CreateNodeInfo();
    ON_CALL(mNodeInfoProvider, GetCurrentNodeInfo(_))
        .WillByDefault(
            DoAll(SetArgReferee<0>(mNodeInfo), Return(ErrorEnum::eNone)));
    ON_CALL(mStatusReceiver, OnInstancesStatusesReceived(_))
        .WillByDefault(Return(ErrorEnum::eNone));
    ON_CALL(mProfile, OfflineSelfTest(_))
        .WillByDefault(Return(ErrorEnum::eNone));
    ON_CALL(mProfile, MarkUnavailable())
        .WillByDefault(Return(ErrorEnum::eNone));
    ON_CALL(mProfile, StopProvider()).WillByDefault(Return(ErrorEnum::eNone));
    ON_CALL(mProfile, StartProvider()).WillByDefault(Return(ErrorEnum::eNone));
    ON_CALL(mProfile, CheckHealth()).WillByDefault(Return(ErrorEnum::eNone));
  }

  void TearDown() override { std::filesystem::remove_all(mWorkingDir); }

  RuntimeConfig CreateConfig(uint64_t minimumFreeBytes = 1) const {
    auto config = Poco::makeShared<Poco::JSON::Object>();
    config->set("workingDir", mWorkingDir.string());
    config->set("unit", "aos-vehicle-data-provider.service");
    config->set("healthAdapter",
                "/usr/libexec/aos-vehicle-data-provider-health");
    config->set("layoutVersion", 1);
    config->set("maxPayloadBytes", 1024 * 1024);
    config->set("minimumFreeBytes", minimumFreeBytes);
    config->set("startTimeoutSeconds", 30);
    config->set("stopTimeoutSeconds", 15);

    return {cRuntimeSystemdSlotComponent, cComponentType, true,
            mWorkingDir.parent_path().string(), config};
  }

  Error Init(SystemdSlotComponentRuntime &runtime,
             const RuntimeConfig &config) {
    return runtime.Init(config, mNodeInfoProvider, mItemInfoProvider, mOCISpec,
                        mStatusReceiver, mSystemdConn);
  }

  InstanceInfo CreateInstance(const RuntimeInfo &runtimeInfo,
                              const std::string &version,
                              const std::string &digest) const {
    InstanceInfo instance;
    static_cast<InstanceIdent &>(instance) =
        InstanceIdent{"vehicle-data-provider", "aos-vm-main", 0,
                      UpdateItemTypeEnum::eComponent};
    instance.mVersion = version.c_str();
    instance.mManifestDigest = digest.c_str();
    instance.mRuntimeID = runtimeInfo.mRuntimeID;
    return instance;
  }

  std::filesystem::path
  CreatePayload(const std::string &name, const std::string &version,
                const std::string &architecture = "arm64") const {
    const auto root = mWorkingDir.parent_path() / ("r61-payload-" + name);
    std::filesystem::remove_all(root);
    std::filesystem::create_directories(root / "bin");
    std::filesystem::create_directories(root / "config");
    WriteFile(root / "component.json",
              "{\n"
              "  \"schemaVersion\": 1,\n"
              "  \"component\": \"vehicle-data-provider\",\n"
              "  \"version\": \"" +
                  version +
                  "\",\n"
                  "  \"architecture\": \"" +
                  architecture +
                  "\",\n"
                  "  \"os\": \"linux\",\n"
                  "  \"runtimeInterface\": 1,\n"
                  "  \"entrypoint\": \"bin/vehicle-data-provider\",\n"
                  "  \"configuration\": \"config/provider.json\"\n"
                  "}\n",
              std::filesystem::perms::owner_read |
                  std::filesystem::perms::owner_write |
                  std::filesystem::perms::group_read |
                  std::filesystem::perms::others_read);
    WriteFile(root / "bin/vehicle-data-provider", "#!/bin/sh\nexit 0\n",
              std::filesystem::perms::owner_read |
                  std::filesystem::perms::owner_write |
                  std::filesystem::perms::owner_exec |
                  std::filesystem::perms::group_read |
                  std::filesystem::perms::group_exec |
                  std::filesystem::perms::others_read |
                  std::filesystem::perms::others_exec);
    WriteFile(root / "config/provider.json", "{}\n",
              std::filesystem::perms::owner_read |
                  std::filesystem::perms::owner_write |
                  std::filesystem::perms::group_read |
                  std::filesystem::perms::others_read);
    return root;
  }

  void ExpectPayload(const InstanceInfo &instance,
                     const std::filesystem::path &payload,
                     size_t layerSize = 256) {
    EXPECT_CALL(mItemInfoProvider,
                GetBlobPath(String(instance.mManifestDigest), _))
        .WillOnce(Invoke([](const String &, String &path) {
          return path.Assign("/tmp/provider-manifest.json");
        }));
    EXPECT_CALL(mOCISpec, LoadImageManifest(_, _))
        .WillOnce(
            Invoke([layerSize](const String &, oci::ImageManifest &manifest) {
              manifest.mSchemaVersion = oci::cSchemaVersion;
              return manifest.mLayers.EmplaceBack(
                  imagemanager::cProviderLayerMediaType,
                  "sha256:provider-layer", layerSize);
            }));
    EXPECT_CALL(mItemInfoProvider,
                GetLayerPath(String("sha256:provider-layer"), _))
        .WillOnce(Invoke([payload](const String &, String &path) {
          return path.Assign(payload.c_str());
        }));
  }

  void WriteInterruptedTransaction(const std::string &phase,
                                   const InstanceInfo &candidate,
                                   const InstanceInfo &previous) const {
    WriteFile(mWorkingDir / "state/transaction.json",
              "{\n"
              "  \"schemaVersion\": 1,\n"
              "  \"phase\": \"" +
                  phase +
                  "\",\n"
                  "  \"candidateSlot\": \"b\",\n"
                  "  \"candidateItemId\": \"" +
                  candidate.mItemID.CStr() +
                  "\",\n"
                  "  \"candidateSubjectId\": \"" +
                  candidate.mSubjectID.CStr() +
                  "\",\n"
                  "  \"candidateInstance\": 0,\n"
                  "  \"candidateVersion\": \"" +
                  candidate.mVersion.CStr() +
                  "\",\n"
                  "  \"candidateManifestDigest\": \"" +
                  candidate.mManifestDigest.CStr() +
                  "\",\n"
                  "  \"candidateRuntimeId\": \"" +
                  candidate.mRuntimeID.CStr() +
                  "\",\n"
                  "  \"candidatePreinstalled\": false,\n"
                  "  \"hasPrevious\": true,\n"
                  "  \"previousSlot\": \"a\",\n"
                  "  \"previousItemId\": \"" +
                  previous.mItemID.CStr() +
                  "\",\n"
                  "  \"previousSubjectId\": \"" +
                  previous.mSubjectID.CStr() +
                  "\",\n"
                  "  \"previousInstance\": 0,\n"
                  "  \"previousVersion\": \"" +
                  previous.mVersion.CStr() +
                  "\",\n"
                  "  \"previousManifestDigest\": \"" +
                  previous.mManifestDigest.CStr() +
                  "\",\n"
                  "  \"previousRuntimeId\": \"" +
                  previous.mRuntimeID.CStr() +
                  "\",\n"
                  "  \"previousPreinstalled\": false\n"
                  "}\n",
              std::filesystem::perms::owner_read |
                  std::filesystem::perms::owner_write);
  }

  std::unique_ptr<SystemdSlotComponentRuntime>
  StartEmptyRuntime(const RuntimeConfig &config) {
    auto runtime = std::make_unique<SystemdSlotComponentRuntime>(&mProfile);
    EXPECT_TRUE(Init(*runtime, config).IsNone());
    EXPECT_TRUE(runtime->Start().IsNone());
    return runtime;
  }

  NiceMock<iamclient::CurrentNodeInfoProviderMock> mNodeInfoProvider;
  NiceMock<imagemanager::ItemInfoProviderMock> mItemInfoProvider;
  NiceMock<oci::OCISpecMock> mOCISpec;
  NiceMock<InstanceStatusReceiverMock> mStatusReceiver;
  NiceMock<sm::utils::SystemdConnMock> mSystemdConn;
  NiceMock<ProviderProfileMock> mProfile;
  std::filesystem::path mWorkingDir;
  NodeInfo mNodeInfo;
};

TEST_F(SystemdSlotComponentRuntimeTest, RequiresTheFixedBootstrapContract) {
  SystemdSlotComponentRuntime runtime(&mProfile);
  auto config = CreateConfig();
  config.mConfig->set("layoutVersion", 2);

  const auto err = Init(runtime, config);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, StartsWithAnEmptyPersistentStore) {
  auto runtime = StartEmptyRuntime(CreateConfig());

  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  EXPECT_EQ(info.mRuntimeType, String(cComponentType));
  EXPECT_EQ(info.mArchInfo.mArchitecture, String("arm64"));
  EXPECT_EQ(info.mMaxInstances, 1U);
  EXPECT_TRUE(std::filesystem::is_directory(mWorkingDir / "slots"));
  EXPECT_TRUE(std::filesystem::is_directory(mWorkingDir / "state"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_TRUE(runtime->Reboot().Is(ErrorEnum::eNotSupported));
}

TEST_F(SystemdSlotComponentRuntimeTest, InstallsFirstReleaseAtomically) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:release020");
  const auto payload = CreatePayload("020", "0.2.0");
  ExpectPayload(instance, payload);

  {
    InSequence sequence;
    EXPECT_CALL(mProfile, OfflineSelfTest(mWorkingDir / "slots/a"));
    EXPECT_CALL(mProfile, MarkUnavailable());
    EXPECT_CALL(mProfile, StopProvider());
    EXPECT_CALL(mProfile, StartProvider());
    EXPECT_CALL(mProfile, CheckHealth());
  }

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActive);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_TRUE(std::filesystem::is_regular_file(mWorkingDir /
                                               "slots/a/.aos-instance.json"));
  EXPECT_TRUE(
      std::filesystem::is_regular_file(mWorkingDir / "state/installed.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       FailedCandidateRollsBackToPreviousRelease) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());

  const auto first = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(first, CreatePayload("020", "0.2.0"));
  InstanceStatus firstStatus;
  ASSERT_TRUE(runtime->StartInstance(first, firstStatus).IsNone());

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(candidate, CreatePayload("030", "0.3.0"));
  EXPECT_CALL(mProfile, CheckHealth())
      .WillOnce(Return(ErrorEnum::eFailed))
      .WillOnce(Return(ErrorEnum::eNone));

  InstanceStatus candidateStatus;
  const auto err = runtime->StartInstance(candidate, candidateStatus);
  EXPECT_TRUE(err.Is(ErrorEnum::eFailed)) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(candidateStatus.mState, InstanceStateEnum::eFailed);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "slots/b"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/last-failure.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       OfflineSelfTestFailureDoesNotSwitchFirstInstall) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:offlinefail");
  ExpectPayload(instance, CreatePayload("offlinefail", "0.2.0"));
  EXPECT_CALL(mProfile, OfflineSelfTest(mWorkingDir / "slots/a"))
      .WillOnce(Return(ErrorEnum::eFailed));
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eFailed)) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eFailed);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       FirstInstallHealthFailureLeavesNoActiveProvider) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:healthfail");
  ExpectPayload(instance, CreatePayload("healthfail", "0.2.0"));
  EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eFailed)) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eFailed);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/last-failure.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       CandidateStartFailureRestoresPreviousRelease) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(previous, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:startfail");
  ExpectPayload(candidate, CreatePayload("startfail", "0.3.0"));
  EXPECT_CALL(mProfile, StartProvider())
      .WillOnce(Return(ErrorEnum::eFailed))
      .WillOnce(Return(ErrorEnum::eNone));

  const auto err = runtime->StartInstance(candidate, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eFailed)) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eFailed);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest, UpdatesFromSlotAToSlotB) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());

  const auto first = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(first, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(first, status).IsNone());

  const auto second = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(second, CreatePayload("030", "0.3.0"));
  ASSERT_TRUE(runtime->StartInstance(second, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActive);
  EXPECT_EQ(status.mVersion, String("0.3.0"));
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/b"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "slots/a"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "slots/b"));
}

TEST_F(SystemdSlotComponentRuntimeTest, RepeatedDigestIsIdempotent) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(instance, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(instance, status).IsNone());

  EXPECT_CALL(mItemInfoProvider, GetBlobPath(_, _)).Times(0);
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  ASSERT_TRUE(runtime->StartInstance(instance, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActive);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsMultiLayerManifest) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:multilayer");
  EXPECT_CALL(mItemInfoProvider, GetBlobPath(_, _))
      .WillOnce(Invoke([](const String &, String &path) {
        return path.Assign("/tmp/provider-manifest.json");
      }));
  EXPECT_CALL(mOCISpec, LoadImageManifest(_, _))
      .WillOnce(Invoke([](const String &, oci::ImageManifest &manifest) {
        auto err = manifest.mLayers.EmplaceBack(oci::cMediaTypeLayerTarGZip,
                                                "sha256:layer-one", 128);
        if (!err.IsNone()) {
          return err;
        }
        return manifest.mLayers.EmplaceBack(oci::cMediaTypeLayerTarGZip,
                                            "sha256:layer-two", 128);
      }));
  EXPECT_CALL(mItemInfoProvider, GetLayerPath(_, _)).Times(0);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsGroupWritablePayload) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:writable");
  const auto payload = CreatePayload("writable", "0.2.0");
  std::filesystem::permissions(payload / "config/provider.json",
                               std::filesystem::perms::group_write,
                               std::filesystem::perm_options::add);
  ExpectPayload(instance, payload);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsBootstrapOwnedMetadata) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:reserved");
  const auto payload = CreatePayload("reserved", "0.2.0");
  WriteFile(payload / ".aos-instance.json", "{}\n",
            std::filesystem::perms::owner_read |
                std::filesystem::perms::owner_write);
  ExpectPayload(instance, payload);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsSpecialPayloadFile) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:special");
  const auto payload = CreatePayload("special", "0.2.0");
  ASSERT_EQ(mkfifo((payload / "unexpected-fifo").c_str(), 0644), 0);
  ExpectPayload(instance, payload);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsUnexpectedExecutable) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:extraexec");
  const auto payload = CreatePayload("extraexec", "0.2.0");
  WriteFile(payload / "bin/unexpected", "#!/bin/sh\nexit 0\n",
            std::filesystem::perms::owner_read |
                std::filesystem::perms::owner_write |
                std::filesystem::perms::owner_exec);
  ExpectPayload(instance, payload);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsControlCharacterInPath) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:controlpath");
  const auto payload = CreatePayload("controlpath", "0.2.0");
  WriteFile(payload / "bad\nname", "bad\n",
            std::filesystem::perms::owner_read |
                std::filesystem::perms::owner_write);
  ExpectPayload(instance, payload);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsUnsafePayloadSymlink) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:unsafe");
  const auto payload = CreatePayload("unsafe", "0.2.0");
  std::filesystem::create_symlink("/etc/passwd", payload / "escape");
  ExpectPayload(instance, payload);

  EXPECT_CALL(mProfile, OfflineSelfTest(_)).Times(0);
  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsWrongArchitecture) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:wrongarch");
  ExpectPayload(instance, CreatePayload("wrongarch", "0.2.0", "amd64"));

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsInsufficientStorageReserve) {
  constexpr uint64_t cImpossibleReserve =
      16ULL * 1024ULL * 1024ULL * 1024ULL * 1024ULL;
  auto runtime = StartEmptyRuntime(CreateConfig(cImpossibleReserve));
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:nospace");
  ExpectPayload(instance, CreatePayload("nospace", "0.2.0"));

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eNoMemory)) << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsOversizedManifestLayer) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:oversized");
  EXPECT_CALL(mItemInfoProvider, GetBlobPath(_, _))
      .WillOnce(Invoke([](const String &, String &path) {
        return path.Assign("/tmp/provider-manifest.json");
      }));
  EXPECT_CALL(mOCISpec, LoadImageManifest(_, _))
      .WillOnce(Invoke([](const String &, oci::ImageManifest &manifest) {
        manifest.mSchemaVersion = oci::cSchemaVersion;
        return manifest.mLayers.EmplaceBack(
            imagemanager::cProviderLayerMediaType, "sha256:provider-layer",
            2 * 1024 * 1024);
      }));
  EXPECT_CALL(mItemInfoProvider, GetLayerPath(_, _)).Times(0);

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsDowngradeWithoutSwitching) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto current = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(current, CreatePayload("030", "0.3.0"));
  InstanceStatus currentStatus;
  ASSERT_TRUE(runtime->StartInstance(current, currentStatus).IsNone());

  const auto downgrade = CreateInstance(info, "0.2.0", "sha256:release020");
  EXPECT_CALL(mItemInfoProvider, GetBlobPath(_, _)).Times(0);
  InstanceStatus status;
  const auto err = runtime->StartInstance(downgrade, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest, RejectsSameVersionWithDifferentDigest) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto current = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(current, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(current, status).IsNone());

  const auto ambiguous = CreateInstance(info, "0.2.0", "sha256:different020");
  EXPECT_CALL(mItemInfoProvider, GetBlobPath(_, _)).Times(0);
  const auto err = runtime->StartInstance(ambiguous, status);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest, StopMakesTheComponentUnavailable) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(instance, CreatePayload("020", "0.2.0"));
  InstanceStatus active;
  ASSERT_TRUE(runtime->StartInstance(instance, active).IsNone());

  EXPECT_CALL(mProfile, MarkUnavailable()).Times(1);
  EXPECT_CALL(mProfile, StopProvider()).Times(1);
  InstanceStatus stopped;
  ASSERT_TRUE(runtime->StopInstance(instance, stopped).IsNone());
  EXPECT_EQ(stopped.mState, InstanceStateEnum::eInactive);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
}

class SystemdSlotComponentRecoveryTest
    : public SystemdSlotComponentRuntimeTest,
      public WithParamInterface<const char *> {};

TEST_P(SystemdSlotComponentRecoveryTest,
       RestoresPreviousReleaseAtEveryDurableBoundary) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(previous, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
  ASSERT_TRUE(runtime->Stop().IsNone());

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  WriteInterruptedTransaction(GetParam(), candidate, previous);
  if (std::string(GetParam()) == "switched" ||
      std::string(GetParam()) == "candidate-started") {
    std::filesystem::remove(mWorkingDir / "active");
    std::filesystem::create_symlink("slots/b", mWorkingDir / "active");
  }

  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(&mProfile);
  ASSERT_TRUE(Init(*recovered, CreateConfig()).IsNone());
  const auto err = recovered->Start();
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));

  std::ifstream installed(mWorkingDir / "state/installed.json");
  ASSERT_TRUE(installed.is_open());
  const std::string installedContent(
      (std::istreambuf_iterator<char>(installed)),
      std::istreambuf_iterator<char>());
  EXPECT_THAT(installedContent, HasSubstr("0.2.0"));
  EXPECT_THAT(installedContent, Not(HasSubstr("0.3.0")));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       ClearsStaleTransactionAfterCommittedCandidate) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(previous, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(candidate, CreatePayload("030", "0.3.0"));
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  ASSERT_TRUE(runtime->Stop().IsNone());

  WriteInterruptedTransaction("candidate-started", candidate, previous);
  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(&mProfile);
  ASSERT_TRUE(Init(*recovered, CreateConfig()).IsNone());
  const auto err = recovered->Start();
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/b"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       FailedPreviousHealthLeavesComponentFailSafe) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(previous, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
  ASSERT_TRUE(runtime->Stop().IsNone());

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  WriteInterruptedTransaction("switched", candidate, previous);
  std::filesystem::remove(mWorkingDir / "active");
  std::filesystem::create_symlink("slots/b", mWorkingDir / "active");
  EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));

  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(&mProfile);
  ASSERT_TRUE(Init(*recovered, CreateConfig()).IsNone());
  const auto err = recovered->Start();
  EXPECT_TRUE(err.Is(ErrorEnum::eFailed)) << tests::utils::ErrorToStr(err);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/last-failure.json"));
}

INSTANTIATE_TEST_SUITE_P(AllTransactionPhases, SystemdSlotComponentRecoveryTest,
                         Values("prepared", "unavailable", "previous-stopped",
                                "switched", "candidate-started"));

} // namespace aos::sm::launcher
