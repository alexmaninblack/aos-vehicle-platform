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
      result.mStopTimeoutSeconds == 0 || result.mStopTimeoutSeconds > 300) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument,
              "invalid systemd slot component configuration"));
  }

  return ErrorEnum::eNone;
}

} // namespace aos::sm::launcher
