/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_RUNTIME_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_RUNTIME_HPP_

#include <mutex>

#include <core/common/iamclient/itf/currentnodeinfoprovider.hpp>
#include <core/common/ocispec/itf/ocispec.hpp>
#include <core/sm/imagemanager/itf/iteminfoprovider.hpp>
#include <core/sm/launcher/itf/instancestatusreceiver.hpp>
#include <core/sm/launcher/itf/runtime.hpp>

#include <sm/launcher/runtimes/config.hpp>
#include <sm/utils/itf/systemdconn.hpp>

#include "config.hpp"

namespace aos::sm::launcher {

/** Service Manager plugin name owned by the OEM bootstrap image. */
inline constexpr auto cRuntimeSystemdSlotComponent = "systemd-slot-component";

/**
 * Bootstrap boundary for the vehicle-data-provider FOTA component.
 *
 * R6.1-2 intentionally supports an empty component store only. Component
 * prepare, activation, rollback, and recovery are rejected until R6.1-3.
 */
class SystemdSlotComponentRuntime final : public RuntimeItf {
public:
  Error Init(const RuntimeConfig &config,
             iamclient::CurrentNodeInfoProviderItf &currentNodeInfoProvider,
             imagemanager::ItemInfoProviderItf &itemInfoProvider,
             oci::OCISpecItf &ociSpec,
             InstanceStatusReceiverItf &statusReceiver,
             sm::utils::SystemdConnItf &systemdConn);

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

private:
  Error EnsureEmptyStore() const;
  void FillFailedStatus(const InstanceInfo &instance, const Error &error,
                        InstanceStatus &status) const;
  void FillFailedStatus(const InstanceIdent &instance, const Error &error,
                        InstanceStatus &status) const;

  mutable std::mutex mMutex;
  SystemdSlotComponentConfig mConfig;
  RuntimeInfo mRuntimeInfo;
  StaticString<cIDLen> mNodeID;
  imagemanager::ItemInfoProviderItf *mItemInfoProvider{};
  oci::OCISpecItf *mOCISpec{};
  InstanceStatusReceiverItf *mStatusReceiver{};
  sm::utils::SystemdConnItf *mSystemdConn{};
  bool mStarted{};
};

} // namespace aos::sm::launcher

#endif
