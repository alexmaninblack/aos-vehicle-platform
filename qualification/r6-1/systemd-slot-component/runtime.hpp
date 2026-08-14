/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_RUNTIME_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_RUNTIME_HPP_

#include <string>
#include <vector>

#include <core/common/iamclient/itf/currentnodeinfoprovider.hpp>
#include <core/sm/launcher/itf/runtime.hpp>

#include <sm/launcher/runtimes/config.hpp>

namespace aos::sm::launcher {

/** Qualification-only plugin name. */
static constexpr auto cRuntimeSystemdSlotComponent = "systemd-slot-component";

/**
 * Minimal runtime used only to qualify the Service Manager lifecycle seam.
 *
 * This probe intentionally has no systemd, archive, slot, persistence,
 * health, apply, or rollback implementation. It must never be included in a
 * production bootstrap image.
 */
class SystemdSlotComponentRuntime final : public RuntimeItf {
public:
  /**
   * Initializes the qualification runtime.
   *
   * @param config Service Manager runtime configuration.
   * @param currentNodeInfoProvider current Node information provider.
   * @return Error.
   */
  Error Init(const RuntimeConfig &config,
             iamclient::CurrentNodeInfoProviderItf &currentNodeInfoProvider);

  Error Start() override;
  Error Stop() override;
  Error GetRuntimeInfo(RuntimeInfo &runtimeInfo) const override;
  Error StartInstance(const InstanceInfo &instance,
                      InstanceStatus &status) override;
  Error StopInstance(const InstanceIdent &instance,
                     InstanceStatus &status) override;
  Error Reboot() override;
  Error GetInstanceMonitoringData(
      const InstanceIdent &instanceIdent,
      monitoring::InstanceMonitoringData &monitoringData) override;

  /** Returns the deterministic in-memory operation trace for qualification. */
  const std::vector<std::string> &GetTrace() const;

private:
  void SetStatus(const InstanceIdent &instance,
                 const StaticString<cVersionLen> &version,
                 const StaticString<oci::cDigestLen> &manifestDigest,
                 InstanceStateEnum state, InstanceStatus &status) const;

  RuntimeInfo mRuntimeInfo;
  StaticString<cIDLen> mNodeID;
  InstanceIdent mActiveInstance;
  StaticString<cVersionLen> mActiveVersion;
  StaticString<oci::cDigestLen> mActiveManifestDigest;
  std::vector<std::string> mTrace;
  bool mStarted{};
  bool mHasActiveInstance{};
};

} // namespace aos::sm::launcher

#endif
