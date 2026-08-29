/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "config.hpp"

#include <common/utils/exception.hpp>
#include <common/utils/filesystem.hpp>
#include <common/utils/json.hpp>

namespace aos::sm::launcher {

namespace {

constexpr auto cDefaultWorkingDir = "runtimes/systemd-slot-component";
constexpr auto cProviderUnit = "aos-vehicle-data-provider.service";
constexpr auto cHealthAdapter = "/usr/libexec/aos-vehicle-data-provider-health";
constexpr auto cLayoutVersion = 1U;
constexpr auto cDefaultMaxPayloadBytes = 512ULL * 1024ULL * 1024ULL;
constexpr auto cDefaultMinimumFreeBytes = 128ULL * 1024ULL * 1024ULL;
constexpr auto cDefaultStartTimeoutSeconds = 30U;
constexpr auto cDefaultStopTimeoutSeconds = 15U;
constexpr auto cSafeStopWaitSeconds = 480U;
constexpr auto cSafeStopReadTimeoutMilliseconds = 250U;
constexpr auto cSafeStopCancelTimeoutSeconds = 2U;
constexpr auto cVehicleStateRole = "PLATFORM_UPDATE_RUNTIME";
constexpr auto cVehicleStateEndpoint = "wss://10.0.0.1:6443";
constexpr auto cVehicleStateServerName = "127.0.0.1";
constexpr auto cCredentialDirectory = "/run/credentials/aos-sm.service/";

} // namespace

Error ParseConfig(const RuntimeConfig &config,
                  SystemdSlotComponentConfig &result) {
  try {
    const auto object =
        common::utils::CaseInsensitiveObjectWrapper(config.mConfig);

    result.mWorkingDir = object.GetValue<std::string>(
        "workingDir",
        common::utils::JoinPath(config.mWorkingDir, cDefaultWorkingDir));
    result.mUnit = object.GetValue<std::string>("unit", "");
    result.mHealthAdapter =
        object.GetValue<std::string>("healthAdapter", cHealthAdapter);
    result.mLayoutVersion = object.GetValue<uint32_t>("layoutVersion", 0);
    result.mMaxPayloadBytes =
        object.GetValue<uint64_t>("maxPayloadBytes", cDefaultMaxPayloadBytes);
    result.mMinimumFreeBytes =
        object.GetValue<uint64_t>("minimumFreeBytes", cDefaultMinimumFreeBytes);
    result.mStartTimeoutSeconds = object.GetValue<uint32_t>(
        "startTimeoutSeconds", cDefaultStartTimeoutSeconds);
    result.mStopTimeoutSeconds = object.GetValue<uint32_t>(
        "stopTimeoutSeconds", cDefaultStopTimeoutSeconds);
    result.mSafeStopWaitSeconds =
        object.GetValue<uint32_t>("safeStopWaitSeconds", 0);
    result.mSafeStopReadTimeoutMilliseconds = object.GetValue<uint32_t>(
        "safeStopReadTimeoutMilliseconds", 0);
    result.mSafeStopCancelTimeoutSeconds = object.GetValue<uint32_t>(
        "safeStopCancelTimeoutSeconds", 0);
    result.mVehicleState.mEndpoint =
        object.GetValue<std::string>("vehicleStateEndpoint", "");
    result.mVehicleState.mServerName =
        object.GetValue<std::string>("vehicleStateServerName", "");
    result.mVehicleState.mRole =
        object.GetValue<std::string>("vehicleStateRole", "");
    result.mVehicleState.mCACredential =
        object.GetValue<std::string>("vehicleStateCACredential", "");
    result.mVehicleState.mCertificateCredential = object.GetValue<std::string>(
        "vehicleStateCertificateCredential", "");
    result.mVehicleState.mPrivateKeyCredential = object.GetValue<std::string>(
        "vehicleStatePrivateKeyCredential", "");
    result.mVehicleState.mBindingCredential =
        object.GetValue<std::string>("vehicleStateBindingCredential", "");
  } catch (const std::exception &error) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(error));
  }

  if (!result.mWorkingDir.is_absolute() ||
      result.mWorkingDir.lexically_normal() != result.mWorkingDir ||
      result.mUnit != cProviderUnit ||
      result.mHealthAdapter != cHealthAdapter ||
      result.mLayoutVersion != cLayoutVersion || result.mMaxPayloadBytes == 0 ||
      result.mMaxPayloadBytes > 4ULL * 1024ULL * 1024ULL * 1024ULL ||
      result.mMinimumFreeBytes >
          16ULL * 1024ULL * 1024ULL * 1024ULL * 1024ULL ||
      result.mStartTimeoutSeconds == 0 || result.mStartTimeoutSeconds > 300 ||
      result.mStopTimeoutSeconds == 0 || result.mStopTimeoutSeconds > 300 ||
      result.mSafeStopWaitSeconds != cSafeStopWaitSeconds ||
      result.mSafeStopReadTimeoutMilliseconds !=
          cSafeStopReadTimeoutMilliseconds ||
      result.mSafeStopCancelTimeoutSeconds != cSafeStopCancelTimeoutSeconds ||
      result.mVehicleState.mEndpoint != cVehicleStateEndpoint ||
      result.mVehicleState.mServerName != cVehicleStateServerName ||
      result.mVehicleState.mRole != cVehicleStateRole ||
      result.mVehicleState.mCACredential !=
          std::string(cCredentialDirectory) + "viss-update-ca" ||
      result.mVehicleState.mCertificateCredential !=
          std::string(cCredentialDirectory) + "viss-update-certificate" ||
      result.mVehicleState.mPrivateKeyCredential !=
          std::string(cCredentialDirectory) + "viss-update-private-key" ||
      result.mVehicleState.mBindingCredential !=
          std::string(cCredentialDirectory) + "viss-update-binding") {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument,
              "invalid systemd slot component configuration"));
  }

  return ErrorEnum::eNone;
}

} // namespace aos::sm::launcher
