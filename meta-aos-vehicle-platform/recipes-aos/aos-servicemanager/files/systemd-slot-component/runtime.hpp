/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_RUNTIME_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_RUNTIME_HPP_

#include <filesystem>
#include <mutex>
#include <optional>
#include <string>

#include <core/common/iamclient/itf/currentnodeinfoprovider.hpp>
#include <core/common/ocispec/itf/ocispec.hpp>
#include <core/sm/imagemanager/itf/iteminfoprovider.hpp>
#include <core/sm/launcher/itf/instancestatusreceiver.hpp>
#include <core/sm/launcher/itf/runtime.hpp>

#include <sm/launcher/runtimes/config.hpp>
#include <sm/utils/itf/systemdconn.hpp>

#include "config.hpp"
#include "providerprofile.hpp"

namespace aos::sm::launcher {

/** Service Manager plugin name owned by the OEM bootstrap image. */
inline constexpr auto cRuntimeSystemdSlotComponent = "systemd-slot-component";

/** Persistent release record for one fixed A/B slot. */
struct ComponentRelease {
  InstanceInfo mInstance;
  std::string mSlot;
};

/** Durable transaction phases used for interruption recovery. */
enum class ComponentTransactionPhase {
  ePrepared,
  eUnavailable,
  ePreviousStopped,
  eSwitched,
  eCandidateStarted,
};

/** Durable component transition record. */
struct ComponentTransaction {
  ComponentRelease mCandidate;
  std::optional<ComponentRelease> mPrevious;
  ComponentTransactionPhase mPhase{ComponentTransactionPhase::ePrepared};
};

/**
 * Persistent A/B lifecycle for the vehicle-data-provider FOTA component.
 *
 * The bootstrap owns all executable lifecycle policy. Component payloads are
 * declarative data and can select neither commands nor host paths.
 */
class SystemdSlotComponentRuntime final : public RuntimeItf {
public:
  explicit SystemdSlotComponentRuntime(
      ProviderProfileItf *profileOverride = nullptr);

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
  Error EnsureStore() const;
  Error Recover();
  Error GarbageCollect() const;
  Error PrepareCandidate(const InstanceInfo &instance,
                         ComponentRelease &candidate);
  Error ValidateManifest(const oci::ImageManifest &manifest) const;
  Error ValidateAndCopyPayload(const std::filesystem::path &source,
                               const std::filesystem::path &destination,
                               const InstanceInfo &instance) const;
  Error ValidatePayloadTree(const std::filesystem::path &root,
                            const InstanceInfo &instance,
                            uint64_t &payloadBytes) const;
  Error ValidatePayloadMetadata(const std::filesystem::path &root,
                                const InstanceInfo &instance) const;
  Error Activate(const ComponentRelease &candidate,
                 const std::optional<ComponentRelease> &previous);
  Error Rollback(const ComponentTransaction &transaction,
                 const Error &candidateError);

  Error SaveRelease(const std::filesystem::path &path,
                    const ComponentRelease &release) const;
  Error LoadRelease(const std::filesystem::path &path,
                    ComponentRelease &release) const;
  Error SaveTransaction(const ComponentTransaction &transaction) const;
  Error LoadTransaction(ComponentTransaction &transaction) const;
  Error SaveFailure(const ComponentTransaction &transaction,
                    const Error &error) const;
  Error RemoveStateFile(const std::filesystem::path &path) const;
  Error SwitchActive(const std::string &slot) const;
  Error RemoveActive() const;
  Error ReadActive(std::string &slot) const;
  Error ValidateSlotName(const std::string &slot) const;
  Error ValidateReleaseSlot(const ComponentRelease &release) const;
  Error CheckVersionPolicy(const InstanceInfo &candidate) const;

  void FillStatus(const ComponentRelease &release, InstanceStateEnum state,
                  const Error &error, InstanceStatus &status) const;
  void FillStatus(const InstanceInfo &instance, InstanceStateEnum state,
                  const Error &error, InstanceStatus &status) const;
  void FillStatus(const InstanceIdent &instance, InstanceStateEnum state,
                  const Error &error, InstanceStatus &status) const;
  void Notify(const InstanceStatus &status) const;
  std::filesystem::path StatePath(const std::string &name) const;
  std::filesystem::path SlotPath(const std::string &slot) const;

  mutable std::mutex mMutex;
  SystemdSlotComponentConfig mConfig;
  RuntimeInfo mRuntimeInfo;
  StaticString<cIDLen> mNodeID;
  imagemanager::ItemInfoProviderItf *mItemInfoProvider{};
  oci::OCISpecItf *mOCISpec{};
  InstanceStatusReceiverItf *mStatusReceiver{};
  ProviderProfile mDefaultProfile;
  ProviderProfileItf *mProfile{};
  std::optional<ComponentRelease> mInstalled;
  bool mStarted{};
};

} // namespace aos::sm::launcher

#endif
