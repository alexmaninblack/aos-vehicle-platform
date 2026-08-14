/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "runtime.hpp"

#include <filesystem>
#include <memory>
#include <system_error>
#include <utility>

#include <core/common/tools/logger.hpp>

#include <sm/launcher/runtimes/utils/utils.hpp>

namespace aos::sm::launcher {

namespace {

constexpr size_t cMaxInstances = 1;

Error EnsureDirectory(const std::filesystem::path &path,
                      std::filesystem::perms permissions) {
  std::error_code error;
  const auto status = std::filesystem::symlink_status(path, error);

  if (error && error != std::errc::no_such_file_or_directory) {
    return AOS_ERROR_WRAP(
        Error(error.value(), "cannot inspect component store directory"));
  }

  if (std::filesystem::is_symlink(status) ||
      (std::filesystem::exists(status) &&
       !std::filesystem::is_directory(status))) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe component store directory"));
  }

  std::filesystem::create_directories(path, error);
  if (error) {
    return AOS_ERROR_WRAP(
        Error(error.value(), "cannot create component store directory"));
  }

  std::filesystem::permissions(path, permissions,
                               std::filesystem::perm_options::replace, error);
  if (error) {
    return AOS_ERROR_WRAP(
        Error(error.value(), "cannot set component store permissions"));
  }

  return ErrorEnum::eNone;
}

} // namespace

Error SystemdSlotComponentRuntime::Init(
    const RuntimeConfig &config,
    iamclient::CurrentNodeInfoProviderItf &currentNodeInfoProvider,
    imagemanager::ItemInfoProviderItf &itemInfoProvider,
    oci::OCISpecItf &ociSpec, InstanceStatusReceiverItf &statusReceiver,
    sm::utils::SystemdConnItf &systemdConn) {
  if (config.mPlugin != cRuntimeSystemdSlotComponent || !config.isComponent ||
      config.mType.empty() || !config.mConfig) {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                "invalid systemd slot component runtime"));
  }

  if (auto err = ParseConfig(config, mConfig); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  auto nodeInfo = std::make_unique<NodeInfo>();
  if (auto err = currentNodeInfoProvider.GetCurrentNodeInfo(*nodeInfo);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  if (auto err = utils::CreateRuntimeInfo(config.mType, *nodeInfo,
                                          cMaxInstances, mRuntimeInfo);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  if (auto err = mNodeID.Assign(nodeInfo->mNodeID); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  mItemInfoProvider = &itemInfoProvider;
  mOCISpec = &ociSpec;
  mStatusReceiver = &statusReceiver;
  mSystemdConn = &systemdConn;

  return EnsureEmptyStore();
}

Error SystemdSlotComponentRuntime::Start() {
  std::lock_guard lock{mMutex};

  if (auto err = EnsureEmptyStore(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  mStarted = true;

  LOG_INF()
      << "Vehicle data provider component runtime started with an empty store"
      << Log::Field("runtimeType", mRuntimeInfo.mRuntimeType);

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Stop() {
  std::lock_guard lock{mMutex};
  mStarted = false;

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::GetRuntimeInfo(
    RuntimeInfo &runtimeInfo) const {
  std::lock_guard lock{mMutex};
  runtimeInfo = mRuntimeInfo;

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::StartInstance(const InstanceInfo &instance,
                                                 InstanceStatus &status) {
  std::lock_guard lock{mMutex};

  if (!mStarted || instance.mRuntimeID != mRuntimeInfo.mRuntimeID) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eWrongState, "component runtime is not ready"));
  }

  const auto error = Error(ErrorEnum::eNotSupported,
                           "atomic component lifecycle is deferred to R6.1-3");
  FillFailedStatus(instance, error, status);
  mStatusReceiver->OnInstancesStatusesReceived(
      Array<InstanceStatus>{&status, 1});

  return AOS_ERROR_WRAP(error);
}

Error SystemdSlotComponentRuntime::StopInstance(const InstanceIdent &instance,
                                                InstanceStatus &status) {
  std::lock_guard lock{mMutex};

  const auto error = Error(ErrorEnum::eNotFound,
                           "no vehicle data provider component is active");
  FillFailedStatus(instance, error, status);
  mStatusReceiver->OnInstancesStatusesReceived(
      Array<InstanceStatus>{&status, 1});

  return AOS_ERROR_WRAP(error);
}

Error SystemdSlotComponentRuntime::Reboot() {
  return AOS_ERROR_WRAP(
      Error(ErrorEnum::eNotSupported,
            "provider component updates do not reboot the Node"));
}

Error SystemdSlotComponentRuntime::GetInstanceMonitoringData(
    const InstanceIdent &instanceIdent,
    monitoring::InstanceMonitoringData &monitoringData) {
  (void)instanceIdent;
  (void)monitoringData;

  return AOS_ERROR_WRAP(Error(ErrorEnum::eNotFound,
                              "no vehicle data provider component is active"));
}

Error SystemdSlotComponentRuntime::EnsureEmptyStore() const {
  constexpr auto cReadableDirectory =
      std::filesystem::perms::owner_all | std::filesystem::perms::group_read |
      std::filesystem::perms::group_exec | std::filesystem::perms::others_read |
      std::filesystem::perms::others_exec;
  constexpr auto cPrivateDirectory = std::filesystem::perms::owner_all;

  for (const auto &item :
       {std::pair{mConfig.mWorkingDir, cReadableDirectory},
        std::pair{mConfig.mWorkingDir / "slots", cReadableDirectory},
        std::pair{mConfig.mWorkingDir / "state", cPrivateDirectory},
        std::pair{mConfig.mWorkingDir / "credentials", cPrivateDirectory}}) {
    if (auto err = EnsureDirectory(item.first, item.second); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
  }

  std::error_code error;
  const auto activeStatus =
      std::filesystem::symlink_status(mConfig.mWorkingDir / "active", error);
  if (error && error != std::errc::no_such_file_or_directory) {
    return AOS_ERROR_WRAP(
        Error(error.value(), "cannot inspect active component slot"));
  }
  if (std::filesystem::exists(activeStatus) ||
      std::filesystem::is_symlink(activeStatus)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eWrongState,
              "bootstrap runtime refuses an active component before R6.1-3"));
  }

  return ErrorEnum::eNone;
}

void SystemdSlotComponentRuntime::FillFailedStatus(
    const InstanceInfo &instance, const Error &error,
    InstanceStatus &status) const {
  FillFailedStatus(static_cast<const InstanceIdent &>(instance), error, status);
  status.mVersion = instance.mVersion;
  status.mManifestDigest = instance.mManifestDigest;
  status.mPreinstalled = instance.mPreinstalled;
}

void SystemdSlotComponentRuntime::FillFailedStatus(
    const InstanceIdent &instance, const Error &error,
    InstanceStatus &status) const {
  static_cast<InstanceIdent &>(status) = instance;
  status.mRuntimeID = mRuntimeInfo.mRuntimeID;
  status.mNodeID = mNodeID;
  status.mType = UpdateItemTypeEnum::eComponent;
  status.mState = InstanceStateEnum::eFailed;
  status.mError = error;
}

} // namespace aos::sm::launcher
