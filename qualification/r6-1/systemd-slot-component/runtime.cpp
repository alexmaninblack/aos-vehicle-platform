/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "runtime.hpp"

#include <memory>

#include <sm/launcher/runtimes/utils/utils.hpp>

namespace aos::sm::launcher {

namespace {

constexpr size_t cMaxInstances = 1;

} // namespace

Error SystemdSlotComponentRuntime::Init(
    const RuntimeConfig &config,
    iamclient::CurrentNodeInfoProviderItf &currentNodeInfoProvider) {
  if (config.mPlugin != cRuntimeSystemdSlotComponent || !config.isComponent ||
      config.mType.empty() || config.mWorkingDir.empty() || !config.mConfig ||
      !config.mConfig->has("qualificationMode") ||
      !config.mConfig->getValue<bool>("qualificationMode")) {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                "invalid qualification runtime configuration"));
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

  mTrace.emplace_back("init");

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Start() {
  mStarted = true;
  mTrace.emplace_back("runtime-start");

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Stop() {
  mHasActiveInstance = false;
  mStarted = false;
  mTrace.emplace_back("runtime-stop");

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::GetRuntimeInfo(
    RuntimeInfo &runtimeInfo) const {
  runtimeInfo = mRuntimeInfo;

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::StartInstance(const InstanceInfo &instance,
                                                 InstanceStatus &status) {
  if (!mStarted || mHasActiveInstance ||
      instance.mRuntimeID != mRuntimeInfo.mRuntimeID) {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eWrongState,
                                "qualification runtime cannot start instance"));
  }

  mActiveInstance = instance;
  mActiveVersion = instance.mVersion;
  mActiveManifestDigest = instance.mManifestDigest;
  mHasActiveInstance = true;
  SetStatus(instance, instance.mVersion, instance.mManifestDigest,
            InstanceStateEnum::eActive, status);
  mTrace.emplace_back("instance-start");

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::StopInstance(const InstanceIdent &instance,
                                                InstanceStatus &status) {
  if (!mStarted || !mHasActiveInstance || instance != mActiveInstance) {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eWrongState,
                                "qualification runtime cannot stop instance"));
  }

  SetStatus(instance, mActiveVersion, mActiveManifestDigest,
            InstanceStateEnum::eInactive, status);
  mHasActiveInstance = false;
  mTrace.emplace_back("instance-stop");

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Reboot() {
  return AOS_ERROR_WRAP(
      Error(ErrorEnum::eNotSupported,
            "qualification runtime does not reboot the Node"));
}

Error SystemdSlotComponentRuntime::GetInstanceMonitoringData(
    const InstanceIdent &instanceIdent,
    monitoring::InstanceMonitoringData &monitoringData) {
  if (!mStarted || !mHasActiveInstance || instanceIdent != mActiveInstance) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eNotFound, "qualification runtime instance is not active"));
  }

  monitoringData.mInstanceIdent = instanceIdent;
  monitoringData.mRuntimeID = mRuntimeInfo.mRuntimeID;

  return ErrorEnum::eNone;
}

const std::vector<std::string> &SystemdSlotComponentRuntime::GetTrace() const {
  return mTrace;
}

void SystemdSlotComponentRuntime::SetStatus(
    const InstanceIdent &instance, const StaticString<cVersionLen> &version,
    const StaticString<oci::cDigestLen> &manifestDigest,
    InstanceStateEnum state, InstanceStatus &status) const {
  static_cast<InstanceIdent &>(status) = instance;
  status.mVersion = version;
  status.mManifestDigest = manifestDigest;
  status.mRuntimeID = mRuntimeInfo.mRuntimeID;
  status.mNodeID = mNodeID;
  status.mState = state;
  status.mError = ErrorEnum::eNone;
}

} // namespace aos::sm::launcher
