/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_PROVIDERPROFILE_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_PROVIDERPROFILE_HPP_

#include <filesystem>

#include <core/common/tools/error.hpp>

#include <sm/utils/itf/systemdconn.hpp>

#include "config.hpp"

namespace aos::sm::launcher {

/** Fixed bootstrap-owned provider control boundary. */
class ProviderProfileItf {
public:
  virtual ~ProviderProfileItf() = default;

  virtual Error OfflineSelfTest(const std::filesystem::path &slot) = 0;
  virtual Error MarkUnavailable() = 0;
  virtual Error StopProvider() = 0;
  virtual Error StartProvider() = 0;
  virtual Error CheckHealth() = 0;
};

/** Production profile backed by the fixed health adapter and systemd unit. */
class ProviderProfile final : public ProviderProfileItf {
public:
  Error Init(const SystemdSlotComponentConfig &config,
             sm::utils::SystemdConnItf &systemdConn);

  Error OfflineSelfTest(const std::filesystem::path &slot) override;
  Error MarkUnavailable() override;
  Error StopProvider() override;
  Error StartProvider() override;
  Error CheckHealth() override;

private:
  Error RunAdapter(const std::string &operation,
                   const std::filesystem::path &slot = {}) const;

  SystemdSlotComponentConfig mConfig;
  sm::utils::SystemdConnItf *mSystemdConn{};
};

} // namespace aos::sm::launcher

#endif
