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
constexpr auto cLayoutVersion = 1U;

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
    result.mLayoutVersion = object.GetValue<uint32_t>("layoutVersion", 0);
  } catch (const std::exception &error) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(error));
  }

  if (!result.mWorkingDir.is_absolute() ||
      result.mWorkingDir.lexically_normal() != result.mWorkingDir ||
      result.mUnit != cProviderUnit ||
      result.mLayoutVersion != cLayoutVersion) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument,
              "invalid systemd slot component configuration"));
  }

  return ErrorEnum::eNone;
}

} // namespace aos::sm::launcher
