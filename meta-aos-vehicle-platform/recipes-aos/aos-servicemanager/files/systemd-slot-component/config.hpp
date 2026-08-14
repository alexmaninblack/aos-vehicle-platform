/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_CONFIG_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_CONFIG_HPP_

#include <cstdint>
#include <filesystem>
#include <string>

#include <core/common/tools/error.hpp>

#include <sm/launcher/runtimes/config.hpp>

namespace aos::sm::launcher {

/** Bootstrap configuration for the provider component runtime. */
struct SystemdSlotComponentConfig {
  std::filesystem::path mWorkingDir;
  std::string mUnit;
  uint32_t mLayoutVersion{};
};

/** Parses and validates the bootstrap runtime configuration. */
Error ParseConfig(const RuntimeConfig &config,
                  SystemdSlotComponentConfig &result);

} // namespace aos::sm::launcher

#endif
