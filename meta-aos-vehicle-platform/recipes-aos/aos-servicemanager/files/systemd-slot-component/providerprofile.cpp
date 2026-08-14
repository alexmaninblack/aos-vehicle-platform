/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "providerprofile.hpp"

#include <common/utils/utils.hpp>

namespace aos::sm::launcher {

Error ProviderProfile::Init(const SystemdSlotComponentConfig &config,
                            sm::utils::SystemdConnItf &systemdConn) {
  mConfig = config;
  mSystemdConn = &systemdConn;

  auto [units, err] = mSystemdConn->ListUnits();
  (void)units;
  if (!err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  return ErrorEnum::eNone;
}

Error ProviderProfile::OfflineSelfTest(const std::filesystem::path &slot) {
  return RunAdapter("offline", slot);
}

Error ProviderProfile::MarkUnavailable() { return RunAdapter("unavailable"); }

Error ProviderProfile::StopProvider() {
  return mSystemdConn->StopUnit(
      mConfig.mUnit, "replace",
      static_cast<int64_t>(mConfig.mStopTimeoutSeconds) * Time::cSeconds);
}

Error ProviderProfile::StartProvider() {
  if (auto err = mSystemdConn->ResetFailedUnit(mConfig.mUnit); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  return mSystemdConn->StartUnit(
      mConfig.mUnit, "replace",
      static_cast<int64_t>(mConfig.mStartTimeoutSeconds) * Time::cSeconds);
}

Error ProviderProfile::CheckHealth() { return RunAdapter("active"); }

Error ProviderProfile::RunAdapter(const std::string &operation,
                                  const std::filesystem::path &slot) const {
  std::vector<std::string> arguments{mConfig.mHealthAdapter.string(),
                                     operation};
  if (!slot.empty()) {
    arguments.push_back(slot.string());
  }

  auto [output, err] = common::utils::ExecCommand(arguments);
  (void)output;
  if (!err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  return ErrorEnum::eNone;
}

} // namespace aos::sm::launcher
