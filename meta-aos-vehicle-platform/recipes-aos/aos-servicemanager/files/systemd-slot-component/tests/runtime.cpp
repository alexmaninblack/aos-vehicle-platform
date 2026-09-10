/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <future>
#include <thread>
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
#include <sm/utils/systemdconn.hpp>

#include "providerarchive.hpp"
#include "providerprofile.hpp"
#include "runtime.hpp"
#include "safestop.hpp"

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

class AlwaysSafeVehicleStateProvider : public VehicleStateProviderItf {
public:
  Error ReadFrame(VehicleStateFrame &frame,
                  std::chrono::milliseconds) override {
    const auto now = std::chrono::steady_clock::now();
    const auto frameID = ++mFrame;
    frame = {frameID,
             "SAFE_STOP",
             "STABLE",
             1,
             1,
             false,
             false,
             0.0,
             0.0,
             100.0,
             now,
             now};
    return ErrorEnum::eNone;
  }

  void Cancel() override {}

private:
  std::atomic_uint64_t mFrame{};
};

class ScriptedVehicleStateProvider : public VehicleStateProviderItf {
public:
  Error ReadFrame(VehicleStateFrame &frame,
                  std::chrono::milliseconds) override {
    if (mCanceled) {
      return ErrorEnum::eWrongState;
    }
    const auto read = ++mReads;
    const auto safe = mUnsafeBegin == 0 || read < mUnsafeBegin ||
                      (mUnsafeEnd != 0 && read > mUnsafeEnd);
    const auto now = std::chrono::steady_clock::now();
    const auto frameID = mFixedFrame ? 1 : ++mFrame;
    frame = {frameID,
             safe ? "SAFE_STOP" : "AUTOPILOT",
             "STABLE",
             1,
             1,
             false,
             false,
             0.0,
             0.0,
             100.0,
             now,
             now};
    if (!safe) {
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
    return ErrorEnum::eNone;
  }

  void Cancel() override { mCanceled = true; }

  void SetUnsafeRange(uint64_t begin, uint64_t end = 0) {
    mUnsafeBegin = begin;
    mUnsafeEnd = end;
  }

  void SetFixedFrame(bool fixed) { mFixedFrame = fixed; }

  uint64_t Reads() const { return mReads; }

private:
  std::atomic_uint64_t mFrame{};
  std::atomic_uint64_t mReads{};
  std::atomic_uint64_t mUnsafeBegin{};
  std::atomic_uint64_t mUnsafeEnd{};
  std::atomic_bool mCanceled{};
  std::atomic_bool mFixedFrame{};
};

class MissingCredentialVehicleStateProvider : public VehicleStateProviderItf {
public:
  Error ReadFrame(VehicleStateFrame &,
                  std::chrono::milliseconds) override {
    ++mReads;
    return Error(
        ErrorEnum::eNotFound,
        "PLATFORM_UPDATE_RUNTIME systemd credential is unavailable");
  }

  void Cancel() override { mCanceled = true; }

  uint64_t Reads() const { return mReads; }
  bool Canceled() const { return mCanceled; }

private:
  std::atomic_uint64_t mReads{};
  std::atomic_bool mCanceled{};
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

  void TearDown() override {
    if (!mPreserveWorkingDir) {
      std::filesystem::remove_all(mWorkingDir);
    }
  }

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
    config->set("safeStopWaitSeconds", 480);
    config->set("safeStopReadTimeoutMilliseconds", 250);
    config->set("safeStopCancelTimeoutSeconds", 2);
    config->set("vehicleStateEndpoint", "wss://10.0.0.1:6443");
    config->set("vehicleStateServerName", "127.0.0.1");
    config->set("vehicleStateRole", "PLATFORM_UPDATE_RUNTIME");
    config->set("vehicleStateCACredential",
                "/run/credentials/aos-sm.service/viss-update-ca");
    config->set("vehicleStateCertificateCredential",
                "/run/credentials/aos-sm.service/viss-update-certificate");
    config->set("vehicleStatePrivateKeyCredential",
                "/run/credentials/aos-sm.service/viss-update-private-key");
    config->set("vehicleStateBindingCredential",
                "/run/credentials/aos-sm.service/viss-update-binding");

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
        InstanceIdent{runtimeInfo.mRuntimeType, "aos-vm-main", 0,
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
    for (const auto &directory : {root, root / "bin", root / "config"}) {
      std::filesystem::permissions(
          directory, std::filesystem::perms::owner_all |
                         std::filesystem::perms::group_read |
                         std::filesystem::perms::group_exec |
                         std::filesystem::perms::others_read |
                         std::filesystem::perms::others_exec,
          std::filesystem::perm_options::replace);
    }
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
                     size_t layerSize = 256,
                     const char *mediaType =
                         imagemanager::cProviderLayerMediaType) {
    EXPECT_CALL(mItemInfoProvider,
                GetBlobPath(String(instance.mManifestDigest), _))
        .WillOnce(Invoke([](const String &, String &path) {
          return path.Assign("/tmp/provider-manifest.json");
        }));
    EXPECT_CALL(mOCISpec, LoadImageManifest(_, _))
        .WillOnce(
            Invoke([layerSize, mediaType](const String &,
                                          oci::ImageManifest &manifest) {
              manifest.mSchemaVersion = oci::cSchemaVersion;
              return manifest.mLayers.EmplaceBack(
                  mediaType, "sha256:provider-layer", layerSize);
            }));
    EXPECT_CALL(mItemInfoProvider,
                GetLayerPath(String("sha256:provider-layer"), _))
        .WillOnce(Invoke([payload](const String &, String &path) {
          return path.Assign(payload.c_str());
        }));
  }

  void ExpectComponentPayload(const InstanceInfo &instance,
                              const std::filesystem::path &payload,
                              size_t layerSize = 256) {
    const auto archive = payload.parent_path() /
                         (payload.filename().string() + ".tar.gz");
    std::filesystem::remove(archive);
    const auto command =
        "tar --format=ustar -czf '" + archive.string() + "' -C '" +
        payload.string() + "' component.json bin config";
    ASSERT_EQ(std::system(command.c_str()), 0);

    EXPECT_CALL(mItemInfoProvider,
                GetBlobPath(String(instance.mManifestDigest), _))
        .WillOnce(Invoke([](const String &, String &path) {
          return path.Assign("/tmp/provider-manifest.json");
        }));
    EXPECT_CALL(mOCISpec, LoadImageManifest(_, _))
        .WillOnce(Invoke([layerSize](const String &,
                                    oci::ImageManifest &manifest) {
          manifest.mSchemaVersion = oci::cSchemaVersion;
          return manifest.mLayers.EmplaceBack(
              imagemanager::cProviderComponentLayerMediaType,
              "sha256:provider-layer", layerSize);
        }));
    EXPECT_CALL(mItemInfoProvider,
                GetBlobPath(String("sha256:provider-layer"), _))
        .WillOnce(Invoke([archive](const String &, String &path) {
          return path.Assign(archive.c_str());
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
    auto runtime = std::make_unique<SystemdSlotComponentRuntime>(
        &mProfile, &mVehicleState);
    EXPECT_TRUE(Init(*runtime, config).IsNone());
    EXPECT_TRUE(runtime->Start().IsNone());
    return runtime;
  }

  std::unique_ptr<SystemdSlotComponentRuntime>
  StartRuntime(const RuntimeConfig &config,
               VehicleStateProviderItf &vehicleState) {
    auto runtime = std::make_unique<SystemdSlotComponentRuntime>(
        &mProfile, &vehicleState);
    EXPECT_TRUE(Init(*runtime, config).IsNone());
    EXPECT_TRUE(runtime->Start().IsNone());
    return runtime;
  }

  void WaitForTransactionCompletion(
      std::chrono::seconds timeout = std::chrono::seconds{5}) const {
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (std::filesystem::exists(mWorkingDir / "state/transaction.json") &&
           std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
    ASSERT_FALSE(
        std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  }

  template <typename Provider>
  void WaitForReads(const Provider &provider, uint64_t minimum,
                    std::chrono::seconds timeout =
                        std::chrono::seconds{2}) const {
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (provider.Reads() < minimum &&
           std::chrono::steady_clock::now() < deadline) {
      std::this_thread::sleep_for(std::chrono::milliseconds{1});
    }
    ASSERT_GE(provider.Reads(), minimum);
  }

  void QueuePreviousForRestart(bool remove, bool stoppedPrevious = false) {
    ScriptedVehicleStateProvider unsafe;
    unsafe.SetUnsafeRange(1);
    auto runtime = StartEmptyRuntime(CreateConfig());
    RuntimeInfo info;
    ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
    const auto previous = CreateInstance(info, "0.2.0", "sha256:queued-previous");
    ExpectPayload(previous, CreatePayload("queued-previous", "0.2.0"));
    InstanceStatus status;
    ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
    WaitForTransactionCompletion();
    if (stoppedPrevious) {
      ASSERT_FALSE(remove);
      ASSERT_TRUE(runtime->StopInstance(previous, status).IsNone());
    }
    ASSERT_TRUE(runtime->Stop().IsNone());
    runtime.reset();

    runtime = StartRuntime(CreateConfig(), unsafe);
    if (remove) {
      auto stop = std::async(std::launch::async, [&]() {
        return runtime->StopInstance(previous, status);
      });
      WaitForReads(unsafe, 2);
      ASSERT_TRUE(runtime->Stop().IsNone());
      ASSERT_EQ(stop.wait_for(std::chrono::seconds{2}), std::future_status::ready);
      EXPECT_FALSE(stop.get().IsNone());
    } else {
      const auto candidate = CreateInstance(info, "0.3.0", "sha256:queued-candidate");
      ExpectPayload(candidate, CreatePayload("queued-candidate", "0.3.0"));
      ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
      WaitForReads(unsafe, 2);
      ASSERT_TRUE(runtime->Stop().IsNone());
    }
    runtime.reset();
    ASSERT_TRUE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  }

  std::string StateText(const char *name) const {
    std::ifstream stream(mWorkingDir / "state" / name);
    EXPECT_TRUE(stream.is_open());
    return std::string(std::istreambuf_iterator<char>(stream), {});
  }

  NiceMock<iamclient::CurrentNodeInfoProviderMock> mNodeInfoProvider;
  NiceMock<imagemanager::ItemInfoProviderMock> mItemInfoProvider;
  NiceMock<oci::OCISpecMock> mOCISpec;
  NiceMock<InstanceStatusReceiverMock> mStatusReceiver;
  NiceMock<sm::utils::SystemdConnMock> mSystemdConn;
  NiceMock<ProviderProfileMock> mProfile;
  AlwaysSafeVehicleStateProvider mVehicleState;
  std::filesystem::path mWorkingDir;
  NodeInfo mNodeInfo;
  bool mPreserveWorkingDir{};
};

TEST_F(SystemdSlotComponentRuntimeTest,
       RealProviderFirstInstallThroughProductionProfile) {
  const char *payloadValue = std::getenv("R61_REAL_PROVIDER_PAYLOAD_020");
  if (payloadValue == nullptr) {
    GTEST_SKIP() << "real provider qualification is not requested";
  }
  ASSERT_EQ(getuid(), 0);

  std::filesystem::remove_all(mWorkingDir);
  mWorkingDir =
      "/var/aos/workdirs/sm/runtimes/systemd-slot-component";
  mPreserveWorkingDir = true;
  ASSERT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  ASSERT_TRUE(std::filesystem::is_empty(mWorkingDir / "slots"));

  auto config = CreateConfig(64 * 1024 * 1024);
  config.mConfig->set("maxPayloadBytes", 128 * 1024 * 1024);
  sm::utils::SystemdConn systemdConn;
  SystemdSlotComponentRuntime runtime;
  const auto initError =
      runtime.Init(config, mNodeInfoProvider, mItemInfoProvider, mOCISpec,
                   mStatusReceiver, systemdConn);
  ASSERT_TRUE(initError.IsNone()) << tests::utils::ErrorToStr(initError);
  ASSERT_TRUE(runtime.Start().IsNone());

  RuntimeInfo info;
  ASSERT_TRUE(runtime.GetRuntimeInfo(info).IsNone());
  const auto instance =
      CreateInstance(info, "0.2.0", "sha256:r61-real-provider-020");
  ExpectPayload(instance, payloadValue, 32 * 1024 * 1024);

  InstanceStatus status;
  const auto error = runtime.StartInstance(instance, status);
  ASSERT_TRUE(error.IsNone()) << tests::utils::ErrorToStr(error);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion(std::chrono::seconds{60});
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       RealProviderUpdateAndRollbackThroughProductionProfile) {
  const char *updateValue = std::getenv("R61_REAL_PROVIDER_PAYLOAD_030");
  const char *badValue = std::getenv("R61_REAL_PROVIDER_PAYLOAD_040_BAD");
  if (updateValue == nullptr || badValue == nullptr) {
    GTEST_SKIP() << "real provider qualification is not requested";
  }
  ASSERT_EQ(getuid(), 0);

  std::filesystem::remove_all(mWorkingDir);
  mWorkingDir =
      "/var/aos/workdirs/sm/runtimes/systemd-slot-component";
  mPreserveWorkingDir = true;
  ASSERT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));

  auto config = CreateConfig(64 * 1024 * 1024);
  config.mConfig->set("maxPayloadBytes", 128 * 1024 * 1024);
  sm::utils::SystemdConn systemdConn;
  SystemdSlotComponentRuntime runtime;
  const auto initError =
      runtime.Init(config, mNodeInfoProvider, mItemInfoProvider, mOCISpec,
                   mStatusReceiver, systemdConn);
  ASSERT_TRUE(initError.IsNone()) << tests::utils::ErrorToStr(initError);
  ASSERT_TRUE(runtime.Start().IsNone());

  RuntimeInfo info;
  ASSERT_TRUE(runtime.GetRuntimeInfo(info).IsNone());
  const auto update =
      CreateInstance(info, "0.3.0", "sha256:r61-real-provider-030");
  ExpectPayload(update, updateValue, 32 * 1024 * 1024);
  InstanceStatus status;
  auto error = runtime.StartInstance(update, status);
  ASSERT_TRUE(error.IsNone()) << tests::utils::ErrorToStr(error);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion(std::chrono::seconds{60});
  ASSERT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/b"));

  const auto downgrade =
      CreateInstance(info, "0.2.0", "sha256:r61-real-provider-downgrade");
  error = runtime.StartInstance(downgrade, status);
  EXPECT_TRUE(error.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(error);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/b"));

  const auto bad =
      CreateInstance(info, "0.4.0", "sha256:r61-real-provider-bad");
  ExpectPayload(bad, badValue, 32 * 1024 * 1024);
  error = runtime.StartInstance(bad, status);
  EXPECT_TRUE(error.IsNone()) << tests::utils::ErrorToStr(error);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion(std::chrono::seconds{60});
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/last-failure.json"));
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/b"));
}

TEST_F(SystemdSlotComponentRuntimeTest, RequiresTheFixedBootstrapContract) {
  SystemdSlotComponentRuntime runtime(&mProfile, &mVehicleState);
  auto config = CreateConfig();
  config.mConfig->set("layoutVersion", 2);

  const auto err = Init(runtime, config);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument))
      << tests::utils::ErrorToStr(err);
}

TEST_F(SystemdSlotComponentRuntimeTest, AcceptsOnlyExplicitDemoFreshnessProfile) {
  auto config = CreateConfig();
  SystemdSlotComponentConfig parsed;
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mSafeStopFreshnessProfile, "standard");
  EXPECT_EQ(parsed.mSafeStopReadTimeoutMilliseconds, 250U);
  config.mConfig->set("safeStopFreshnessProfile", "demo-5s");
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mSafeStopFreshnessProfile, "demo-5s");
  EXPECT_EQ(parsed.mSafeStopReadTimeoutMilliseconds, 1000U);
  EXPECT_EQ(config.mConfig->getValue<uint32_t>("safeStopReadTimeoutMilliseconds"), 250U);
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mSafeStopReadTimeoutMilliseconds, 1000U);
  config.mConfig->set("safeStopReadTimeoutMilliseconds", 1000);
  EXPECT_TRUE(ParseConfig(config, parsed).Is(ErrorEnum::eInvalidArgument));
  config.mConfig->set("safeStopReadTimeoutMilliseconds", 250);
  config.mConfig->set("safeStopFreshnessProfile", "unlimited");
  EXPECT_TRUE(ParseConfig(config, parsed).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(SystemdSlotComponentRuntimeTest, FactoryDemoInputsRespectPersistentRole) {
  auto config = CreateConfig();
  SystemdSlotComponentConfig parsed;
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mVehicleState.mCACredential,
            "/run/credentials/aos-sm.service/viss-update-ca");
  config.mConfig->set("demoLocalSourceInputs", true);
  config.mConfig->set("safeStopFreshnessProfile", "demo-5s");
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mSafeStopFreshnessProfile, "standard");
  EXPECT_EQ(parsed.mSafeStopReadTimeoutMilliseconds, 250U);
  const auto inputs = mWorkingDir / "demo-inputs";
  const auto mode = std::filesystem::perms::owner_read |
                    std::filesystem::perms::owner_write;
  EXPECT_EQ(parsed.mVehicleState.mCACredential, inputs / "viss-update-ca");
  EXPECT_EQ(parsed.mVehicleState.mBindingCredential, inputs / "viss-update-binding");
  WriteFile(inputs / "role", "test\n", mode);
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mSafeStopFreshnessProfile, "demo-5s");
  EXPECT_EQ(parsed.mSafeStopReadTimeoutMilliseconds, 1000U);
  WriteFile(inputs / "role", "production\n", mode);
  ASSERT_TRUE(ParseConfig(config, parsed).IsNone());
  EXPECT_EQ(parsed.mSafeStopFreshnessProfile, "standard");
  EXPECT_EQ(parsed.mSafeStopReadTimeoutMilliseconds, 250U);
  WriteFile(inputs / "role", "unknown\n", mode);
  EXPECT_TRUE(ParseConfig(config, parsed).Is(ErrorEnum::eInvalidArgument));
  std::filesystem::remove(inputs / "role");
  std::filesystem::create_symlink("viss-update-binding", inputs / "role");
  EXPECT_TRUE(ParseConfig(config, parsed).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(SystemdSlotComponentRuntimeTest, StartsWithAnEmptyPersistentStore) {
  InstanceStatus factoryStatus;
  EXPECT_CALL(mStatusReceiver, OnInstancesStatusesReceived(_))
      .WillOnce(Invoke([&factoryStatus](const Array<InstanceStatus> &statuses) {
        EXPECT_EQ(statuses.Size(), 1U);
        factoryStatus = statuses[0];
        return ErrorEnum::eNone;
      }));

  auto runtime = StartEmptyRuntime(CreateConfig());

  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  EXPECT_EQ(info.mRuntimeType, String(cComponentType));
  EXPECT_EQ(info.mArchInfo.mArchitecture, String("arm64"));
  EXPECT_EQ(info.mMaxInstances, 1U);
  EXPECT_TRUE(std::filesystem::is_directory(mWorkingDir / "slots"));
  EXPECT_TRUE(std::filesystem::is_directory(mWorkingDir / "state"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_EQ(factoryStatus.mItemID, String(cComponentType));
  EXPECT_EQ(factoryStatus.mSubjectID, String("aos-vm-main"));
  EXPECT_EQ(factoryStatus.mVersion, String("0.0.0"));
  EXPECT_EQ(factoryStatus.mRuntimeID, info.mRuntimeID);
  EXPECT_EQ(factoryStatus.mState, InstanceStateEnum::eActive);
  EXPECT_EQ(factoryStatus.mType, UpdateItemTypeEnum::eComponent);
  EXPECT_TRUE(factoryStatus.mPreinstalled);

  InstanceInfo factoryHandshake;
  static_cast<InstanceIdent &>(factoryHandshake) =
      static_cast<const InstanceIdent &>(factoryStatus);
  factoryHandshake.mVersion = factoryStatus.mVersion;
  factoryHandshake.mManifestDigest = factoryStatus.mManifestDigest;
  factoryHandshake.mRuntimeID = factoryStatus.mRuntimeID;
  factoryHandshake.mPreinstalled = factoryStatus.mPreinstalled;
  InstanceStatus handshakeStatus;
  ASSERT_TRUE(runtime->StartInstance(factoryHandshake, handshakeStatus).IsNone());
  EXPECT_EQ(handshakeStatus.mState, InstanceStateEnum::eActive);
  EXPECT_TRUE(handshakeStatus.mPreinstalled);
  EXPECT_FALSE(
      std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  EXPECT_FALSE(
      std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_TRUE(runtime->Reboot().Is(ErrorEnum::eNotSupported));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       FactoryPlaceholderDoesNotConflictWithResumedFirstInstall) {
  ScriptedVehicleStateProvider unavailable;
  unavailable.SetUnsafeRange(1);
  auto runtime = StartRuntime(CreateConfig(), unavailable);
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto candidate = CreateInstance(info, "7.0.0", "sha256:factory-wait");
  ExpectPayload(candidate, CreatePayload("factory-wait", "7.0.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  WaitForReads(unavailable, 2);
  ASSERT_TRUE(runtime->Stop().IsNone());
  runtime.reset();

  ScriptedVehicleStateProvider resumed;
  resumed.SetUnsafeRange(1);
  runtime = StartRuntime(CreateConfig(), resumed);
  WaitForReads(resumed, 2);
  auto factory = CreateInstance(info, "0.0.0", "");
  factory.mPreinstalled = true;
  ASSERT_TRUE(runtime->StartInstance(factory, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActive);
  EXPECT_TRUE(status.mPreinstalled);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);

  const auto competing = CreateInstance(info, "8.0.0", "sha256:competing");
  EXPECT_TRUE(runtime->StartInstance(competing, status).Is(ErrorEnum::eWrongState));
  EXPECT_EQ(status.mState, InstanceStateEnum::eFailed);
  EXPECT_EQ(status.mVersion, String("8.0.0"));
  EXPECT_FALSE(status.mError.IsNone());
  // A terminal error for a different request does not cancel the first one.
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);

  std::atomic_bool retired{};
  EXPECT_CALL(mStatusReceiver, OnInstancesStatusesReceived(_))
      .WillRepeatedly(Invoke([&retired](const Array<InstanceStatus> &statuses) {
        for (const auto &item : statuses) {
          if (item.mPreinstalled && item.mVersion == String("0.0.0") &&
              item.mState == InstanceStateEnum::eInactive) {
            retired = true;
          }
        }
        return ErrorEnum::eNone;
      }));
  resumed.SetUnsafeRange(0);
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());
  EXPECT_TRUE(retired);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       FactoryPlaceholderIsInactiveAfterInstalledRecovery) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto candidate = CreateInstance(info, "8.0.0", "sha256:factory-installed");
  ExpectPayload(candidate, CreatePayload("factory-installed", "8.0.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());
  runtime.reset();

  runtime = StartEmptyRuntime(CreateConfig());
  auto factory = CreateInstance(info, "0.0.0", "");
  factory.mPreinstalled = true;
  ASSERT_TRUE(runtime->StartInstance(factory, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eInactive);
  EXPECT_TRUE(status.mPreinstalled);
  EXPECT_TRUE(status.mError.IsNone());
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActive);
  EXPECT_EQ(status.mVersion, String("8.0.0"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       WaitingIsNonDestructiveAndCandidateRetriesAreDeterministic) {
  ScriptedVehicleStateProvider vehicleState;
  vehicleState.SetFixedFrame(true);
  auto runtime = StartRuntime(CreateConfig(), vehicleState);
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto candidate =
      CreateInstance(info, "0.2.0", "sha256:waiting-release020");
  ExpectPayload(candidate, CreatePayload("waiting020", "0.2.0"));
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  EXPECT_CALL(mProfile, StartProvider()).Times(0);

  InstanceStatus status;
  const auto startError = runtime->StartInstance(candidate, status);
  ASSERT_TRUE(startError.IsNone()) << tests::utils::ErrorToStr(startError);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForReads(vehicleState, 2);
  EXPECT_TRUE(
      std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));

  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);

  const auto different =
      CreateInstance(info, "0.3.0", "sha256:different-while-waiting");
  EXPECT_TRUE(runtime->StartInstance(different, status)
                  .Is(ErrorEnum::eWrongState));
  ASSERT_TRUE(runtime->Stop().IsNone());
  EXPECT_TRUE(
      std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       MissingVehicleStateCredentialsKeepPlatformUpdateWaitingAndNonDestructive) {
  MissingCredentialVehicleStateProvider vehicleState;
  auto runtime = StartRuntime(CreateConfig(), vehicleState);
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto candidate =
      CreateInstance(info, "0.2.0", "sha256:missing-safe-stop-credentials");
  ExpectPayload(candidate,
                CreatePayload("missing-safe-stop-credentials", "0.2.0"));
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  EXPECT_CALL(mProfile, StartProvider()).Times(0);
  EXPECT_CALL(mProfile, CheckHealth()).Times(0);

  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForReads(vehicleState, 1);
  EXPECT_TRUE(
      std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(
      std::filesystem::exists(mWorkingDir / "state/installed.json"));
  ASSERT_TRUE(runtime->Stop().IsNone());
  EXPECT_TRUE(vehicleState.Canceled());
  EXPECT_TRUE(
      std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       SafeStopLossBeforeApplyReturnsToWaitingThenInstalls) {
  ScriptedVehicleStateProvider vehicleState;
  vehicleState.SetUnsafeRange(13, 13);
  auto runtime = StartRuntime(CreateConfig(), vehicleState);
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto candidate =
      CreateInstance(info, "0.2.0", "sha256:pre-apply-loss");
  ExpectPayload(candidate, CreatePayload("pre-apply-loss", "0.2.0"));
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(1);

  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  WaitForTransactionCompletion();
  EXPECT_GE(vehicleState.Reads(), 29U);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       SafeStopLossAfterPreviousStopRollsBackReplacement) {
  auto initial = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(initial->GetRuntimeInfo(info).IsNone());
  const auto previous =
      CreateInstance(info, "0.2.0", "sha256:loss-previous");
  ExpectPayload(previous, CreatePayload("loss-previous", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(initial->StartInstance(previous, status).IsNone());
  WaitForTransactionCompletion();
  ASSERT_TRUE(initial->Stop().IsNone());
  initial.reset();

  ScriptedVehicleStateProvider vehicleState;
  vehicleState.SetUnsafeRange(15, 15);
  auto runtime = StartRuntime(CreateConfig(), vehicleState);
  const auto candidate =
      CreateInstance(info, "0.3.0", "sha256:loss-candidate");
  ExpectPayload(candidate, CreatePayload("loss-candidate", "0.3.0"));
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(2);
  EXPECT_CALL(mProfile, StopProvider()).Times(2);
  EXPECT_CALL(mProfile, StartProvider()).Times(1);

  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  WaitForTransactionCompletion();
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir /
                                      "state/last-failure.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       RestartWhileWaitingDiscardsSamplesAndCollectsANewWindow) {
  ScriptedVehicleStateProvider unavailable;
  unavailable.SetUnsafeRange(1);
  auto waiting = StartRuntime(CreateConfig(), unavailable);
  RuntimeInfo info;
  ASSERT_TRUE(waiting->GetRuntimeInfo(info).IsNone());
  const auto candidate =
      CreateInstance(info, "0.2.0", "sha256:restart-waiting");
  ExpectPayload(candidate, CreatePayload("restart-waiting", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(waiting->StartInstance(candidate, status).IsNone());
  WaitForReads(unavailable, 2);
  ASSERT_TRUE(waiting->Stop().IsNone());
  waiting.reset();

  auto recovered = StartEmptyRuntime(CreateConfig());
  WaitForTransactionCompletion();
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

class SystemdSlotComponentWaitingRecoveryTest
    : public SystemdSlotComponentRuntimeTest,
      public WithParamInterface<bool> {};

TEST_P(SystemdSlotComponentWaitingRecoveryTest,
       ColdBootStartsInactiveCommittedPrevious) {
  QueuePreviousForRestart(GetParam());
  const auto installed = StateText("installed.json");
  const auto transaction = StateText("transaction.json");
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  {
    InSequence sequence;
    EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));
    EXPECT_CALL(mProfile, StartProvider()).WillOnce(Return(ErrorEnum::eNone));
    EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eNone));
  }
  ScriptedVehicleStateProvider unsafe;
  unsafe.SetUnsafeRange(1);
  auto recovered = StartRuntime(CreateConfig(), unsafe);
  WaitForReads(unsafe, 2);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_EQ(StateText("installed.json"), installed);
  EXPECT_EQ(StateText("transaction.json"), transaction);
  ASSERT_TRUE(recovered->Stop().IsNone());
}

TEST_P(SystemdSlotComponentWaitingRecoveryTest,
       HealthyPreviousDoesNotRestart) {
  QueuePreviousForRestart(GetParam());
  const auto transaction = StateText("transaction.json");
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  EXPECT_CALL(mProfile, StartProvider()).Times(0);
  EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eNone));
  ScriptedVehicleStateProvider unsafe;
  unsafe.SetUnsafeRange(1);
  auto recovered = StartRuntime(CreateConfig(), unsafe);
  WaitForReads(unsafe, 2);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_EQ(StateText("transaction.json"), transaction);
  ASSERT_TRUE(recovered->Stop().IsNone());
}

TEST_P(SystemdSlotComponentWaitingRecoveryTest,
       StartFailurePreservesWaitingState) {
  QueuePreviousForRestart(GetParam());
  const auto installed = StateText("installed.json");
  const auto transaction = StateText("transaction.json");
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  {
    InSequence sequence;
    EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));
    EXPECT_CALL(mProfile, StartProvider()).WillOnce(Return(ErrorEnum::eFailed));
  }
  ScriptedVehicleStateProvider unsafe;
  unsafe.SetUnsafeRange(1);
  SystemdSlotComponentRuntime recovered(&mProfile, &unsafe);
  ASSERT_TRUE(Init(recovered, CreateConfig()).IsNone());
  EXPECT_FALSE(recovered.Start().IsNone());
  EXPECT_EQ(unsafe.Reads(), 0U);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_EQ(StateText("installed.json"), installed);
  EXPECT_EQ(StateText("transaction.json"), transaction);
}

TEST_P(SystemdSlotComponentWaitingRecoveryTest,
       HealthRecheckFailurePreservesWaitingState) {
  QueuePreviousForRestart(GetParam());
  const auto installed = StateText("installed.json");
  const auto transaction = StateText("transaction.json");
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  {
    InSequence sequence;
    EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));
    EXPECT_CALL(mProfile, StartProvider()).WillOnce(Return(ErrorEnum::eNone));
    EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));
  }
  ScriptedVehicleStateProvider unsafe;
  unsafe.SetUnsafeRange(1);
  SystemdSlotComponentRuntime recovered(&mProfile, &unsafe);
  ASSERT_TRUE(Init(recovered, CreateConfig()).IsNone());
  EXPECT_FALSE(recovered.Start().IsNone());
  EXPECT_EQ(unsafe.Reads(), 0U);
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_EQ(StateText("installed.json"), installed);
  EXPECT_EQ(StateText("transaction.json"), transaction);
}

TEST_P(SystemdSlotComponentWaitingRecoveryTest, MissingActiveIsNotRecreated) {
  QueuePreviousForRestart(GetParam());
  const auto installed = StateText("installed.json");
  const auto transaction = StateText("transaction.json");
  std::filesystem::remove(mWorkingDir / "active");
  EXPECT_CALL(mProfile, StartProvider()).Times(0);
  EXPECT_CALL(mProfile, CheckHealth()).Times(0);
  ScriptedVehicleStateProvider unsafe;
  SystemdSlotComponentRuntime recovered(&mProfile, &unsafe);
  ASSERT_TRUE(Init(recovered, CreateConfig()).IsNone());
  EXPECT_FALSE(recovered.Start().IsNone());
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_EQ(StateText("installed.json"), installed);
  EXPECT_EQ(StateText("transaction.json"), transaction);
}

INSTANTIATE_TEST_SUITE_P(QueuedRemoveAndReplace,
                        SystemdSlotComponentWaitingRecoveryTest, Bool());

TEST_F(SystemdSlotComponentRuntimeTest,
       IntentionallyStoppedPreviousRemainsStopped) {
  QueuePreviousForRestart(false, true);
  const auto stopped = StateText("stopped.json");
  const auto transaction = StateText("transaction.json");
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(0);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);
  EXPECT_CALL(mProfile, StartProvider()).Times(0);
  EXPECT_CALL(mProfile, CheckHealth()).Times(0);
  ScriptedVehicleStateProvider unsafe;
  unsafe.SetUnsafeRange(1);
  auto recovered = StartRuntime(CreateConfig(), unsafe);
  WaitForReads(unsafe, 2);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_EQ(StateText("stopped.json"), stopped);
  EXPECT_EQ(StateText("transaction.json"), transaction);
  ASSERT_TRUE(recovered->Stop().IsNone());
}

TEST_F(SystemdSlotComponentRuntimeTest, InstallsFirstReleaseAtomically) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:release020");
  const auto payload = CreatePayload("020", "0.2.0");
  ExpectComponentPayload(instance, payload);
  EXPECT_CALL(mProfile, StopProvider()).Times(0);

  {
    InSequence sequence;
    EXPECT_CALL(mProfile, OfflineSelfTest(mWorkingDir / "slots/a"));
    EXPECT_CALL(mProfile, MarkUnavailable());
    EXPECT_CALL(mProfile, StartProvider());
    EXPECT_CALL(mProfile, CheckHealth());
  }

  InstanceStatus status;
  const auto err = runtime->StartInstance(instance, status);
  ASSERT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();
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
  WaitForTransactionCompletion();

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(candidate, CreatePayload("030", "0.3.0"));
  EXPECT_CALL(mProfile, CheckHealth())
      .WillOnce(Return(ErrorEnum::eFailed))
      .WillOnce(Return(ErrorEnum::eNone));

  InstanceStatus candidateStatus;
  const auto err = runtime->StartInstance(candidate, candidateStatus);
  EXPECT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(candidateStatus.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();
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
  EXPECT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();
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
  WaitForTransactionCompletion();

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:startfail");
  ExpectPayload(candidate, CreatePayload("startfail", "0.3.0"));
  EXPECT_CALL(mProfile, StartProvider())
      .WillOnce(Return(ErrorEnum::eFailed))
      .WillOnce(Return(ErrorEnum::eNone));

  const auto err = runtime->StartInstance(candidate, status);
  EXPECT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       UnavailableMarkFailureDoesNotDiscardRestoredRelease) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(previous, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
  WaitForTransactionCompletion();

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:startfail");
  ExpectPayload(candidate, CreatePayload("startfail", "0.3.0"));
  EXPECT_CALL(mProfile, MarkUnavailable())
      .WillOnce(Return(ErrorEnum::eNone))
      .WillOnce(Return(ErrorEnum::eFailed));
  EXPECT_CALL(mProfile, StartProvider())
      .WillOnce(Return(ErrorEnum::eFailed))
      .WillOnce(Return(ErrorEnum::eNone));

  const auto err = runtime->StartInstance(candidate, status);
  EXPECT_TRUE(err.IsNone()) << tests::utils::ErrorToStr(err);
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path("slots/a"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_TRUE(
      std::filesystem::exists(mWorkingDir / "state/last-failure.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest, UpdatesFromSlotAToSlotB) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());

  const auto first = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(first, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(first, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();

  const auto second = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(second, CreatePayload("030", "0.3.0"));
  ASSERT_TRUE(runtime->StartInstance(second, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eActivating);
  WaitForTransactionCompletion();
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
  WaitForTransactionCompletion();

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
  WaitForTransactionCompletion();

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
  WaitForTransactionCompletion();

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
  WaitForTransactionCompletion();

  EXPECT_CALL(mProfile, MarkUnavailable()).Times(1);
  EXPECT_CALL(mProfile, StopProvider()).Times(1);
  InstanceStatus stopped;
  ASSERT_TRUE(runtime->StopInstance(instance, stopped).IsNone());
  EXPECT_EQ(stopped.mState, InstanceStateEnum::eInactive);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/stopped.json"));
}

class SystemdSlotComponentStopStartTest
    : public SystemdSlotComponentRuntimeTest,
      public WithParamInterface<std::tuple<bool, bool>> {};

TEST_P(SystemdSlotComponentStopStartTest,
       NativeCompletionBarrierPreservesRollbackAcrossRestart) {
  const auto [restart, failHealth] = GetParam();
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:stop-start-old");
  ExpectPayload(previous, CreatePayload("stop-start-old", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());
  runtime.reset();

  ScriptedVehicleStateProvider source;
  source.SetUnsafeRange(1);
  runtime = StartRuntime(CreateConfig(), source);
  auto stop = std::async(std::launch::async, [&]() {
    return runtime->StopInstance(previous, status);
  });
  WaitForReads(source, 2);
  EXPECT_EQ(stop.wait_for(std::chrono::milliseconds{5}),
            std::future_status::timeout);
  // Status remains available: the completion barrier must not own mMutex.
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "active"));
  source.SetUnsafeRange(0);
  ASSERT_EQ(stop.wait_for(std::chrono::seconds{2}), std::future_status::ready);
  ASSERT_TRUE(stop.get().IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eInactive);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/transaction.json"));

  if (restart) {
    ASSERT_TRUE(runtime->Stop().IsNone());
    runtime.reset();
    EXPECT_CALL(mProfile, StartProvider()).Times(0);
    runtime = StartEmptyRuntime(CreateConfig());
    EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
    Mock::VerifyAndClearExpectations(&mProfile);
  }

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:stop-start-new");
  ExpectPayload(candidate, CreatePayload("stop-start-new", "0.3.0"));
  if (failHealth) {
    EXPECT_CALL(mProfile, CheckHealth())
        .WillOnce(Return(ErrorEnum::eFailed))
        .WillOnce(Return(ErrorEnum::eNone));
  }
  // No wait/retry between successful native StopInstance and StartInstance.
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  WaitForTransactionCompletion();
  EXPECT_EQ(std::filesystem::read_symlink(mWorkingDir / "active"),
            std::filesystem::path(failHealth ? "slots/a" : "slots/b"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/stopped.json"));
  ASSERT_TRUE(runtime->Stop().IsNone());
}

INSTANTIATE_TEST_SUITE_P(NativeStopStart, SystemdSlotComponentStopStartTest,
                        Combine(Bool(), Bool()));

TEST_F(SystemdSlotComponentRuntimeTest, StopCancellationNeverReturnsSuccess) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto previous = CreateInstance(info, "0.2.0", "sha256:stop-cancel");
  ExpectPayload(previous, CreatePayload("stop-cancel", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(previous, status).IsNone());
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());
  runtime.reset();
  ScriptedVehicleStateProvider source;
  source.SetUnsafeRange(1);
  runtime = StartRuntime(CreateConfig(), source);
  auto stop = std::async(std::launch::async, [&]() {
    return runtime->StopInstance(previous, status);
  });
  WaitForReads(source, 2);
  ASSERT_TRUE(runtime->Stop().IsNone());
  ASSERT_EQ(stop.wait_for(std::chrono::seconds{2}), std::future_status::ready);
  EXPECT_FALSE(stop.get().IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eFailed);
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest, StopMissingComponentIsIdempotent) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto instance = CreateInstance(info, "0.2.0", "sha256:release020");

  InstanceStatus status;
  ASSERT_TRUE(runtime->StopInstance(instance, status).IsNone());
  EXPECT_EQ(status.mState, InstanceStateEnum::eInactive);
  EXPECT_TRUE(status.mError.IsNone());
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
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  WriteInterruptedTransaction(GetParam(), candidate, previous);
  if (std::string(GetParam()) == "switched" ||
      std::string(GetParam()) == "candidate-started") {
    std::filesystem::remove(mWorkingDir / "active");
    std::filesystem::create_symlink("slots/b", mWorkingDir / "active");
  }

  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(
      &mProfile, &mVehicleState);
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
  WaitForTransactionCompletion();
  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  ExpectPayload(candidate, CreatePayload("030", "0.3.0"));
  ASSERT_TRUE(runtime->StartInstance(candidate, status).IsNone());
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());

  WriteInterruptedTransaction("candidate-started", candidate, previous);
  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(
      &mProfile, &mVehicleState);
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
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());

  const auto candidate = CreateInstance(info, "0.3.0", "sha256:release030");
  WriteInterruptedTransaction("switched", candidate, previous);
  std::filesystem::remove(mWorkingDir / "active");
  std::filesystem::create_symlink("slots/b", mWorkingDir / "active");
  EXPECT_CALL(mProfile, CheckHealth()).WillOnce(Return(ErrorEnum::eFailed));

  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(
      &mProfile, &mVehicleState);
  ASSERT_TRUE(Init(*recovered, CreateConfig()).IsNone());
  const auto err = recovered->Start();
  EXPECT_TRUE(err.Is(ErrorEnum::eFailed)) << tests::utils::ErrorToStr(err);
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/last-failure.json"));
}

TEST_F(SystemdSlotComponentRuntimeTest,
       CorruptedTransactionStateStopsProviderAndRemovesActiveSelection) {
  auto runtime = StartEmptyRuntime(CreateConfig());
  RuntimeInfo info;
  ASSERT_TRUE(runtime->GetRuntimeInfo(info).IsNone());
  const auto installed = CreateInstance(info, "0.2.0", "sha256:release020");
  ExpectPayload(installed, CreatePayload("020", "0.2.0"));
  InstanceStatus status;
  ASSERT_TRUE(runtime->StartInstance(installed, status).IsNone());
  WaitForTransactionCompletion();
  ASSERT_TRUE(runtime->Stop().IsNone());

  WriteFile(mWorkingDir / "state/transaction.json", "{not-json\n",
            std::filesystem::perms::owner_read |
                std::filesystem::perms::owner_write);
  EXPECT_CALL(mProfile, MarkUnavailable()).Times(1);
  EXPECT_CALL(mProfile, StopProvider()).Times(1);

  auto recovered = std::make_unique<SystemdSlotComponentRuntime>(
      &mProfile, &mVehicleState);
  ASSERT_TRUE(Init(*recovered, CreateConfig()).IsNone());
  const auto error = recovered->Start();
  EXPECT_FALSE(error.IsNone());
  EXPECT_FALSE(std::filesystem::exists(mWorkingDir / "active"));
  EXPECT_TRUE(std::filesystem::exists(mWorkingDir / "state/installed.json"));
  EXPECT_TRUE(
      std::filesystem::exists(mWorkingDir / "state/transaction.json"));
}

INSTANTIATE_TEST_SUITE_P(AllTransactionPhases, SystemdSlotComponentRecoveryTest,
                         Values("prepared", "unavailable", "previous-stopped",
                                "switched", "candidate-started"));

} // namespace aos::sm::launcher
