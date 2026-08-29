/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_VISSVEHICLESTATE_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_VISSVEHICLESTATE_HPP_

#include <atomic>
#include <chrono>
#include <filesystem>
#include <map>
#include <memory>
#include <string>

#include "safestop.hpp"

namespace aos::sm::launcher {

/** Non-secret endpoint plus unit-private systemd credential copies. */
struct Viss31MtlsConfig {
  std::string mEndpoint;
  std::string mServerName;
  std::string mRole;
  std::string mExpectedNodeID;
  std::filesystem::path mCACredential;
  std::filesystem::path mCertificateCredential;
  std::filesystem::path mPrivateKeyCredential;
  std::filesystem::path mBindingCredential;
};

/** A coherent VISS GET response, before policy interpretation. */
struct Viss31Snapshot {
  std::map<std::string, std::string> mValues;
  std::chrono::steady_clock::time_point mSourceObservedAt;
  std::chrono::steady_clock::time_point mAcquiredAt;
};

/** Narrow wire seam used by the VISS adapter and replaced by a fake in tests. */
class Viss31MtlsTransportItf {
public:
  virtual ~Viss31MtlsTransportItf() = default;

  virtual Error ReadSnapshot(const Viss31MtlsConfig &config,
                             const std::array<const char *, 10> &paths,
                             Viss31Snapshot &snapshot,
                             std::chrono::milliseconds timeout) = 0;
  virtual void Cancel() = 0;
};

/** Pinned Poco VISSv3 WebSocket client; it exposes no policy surface. */
class PocoViss31MtlsTransport final : public Viss31MtlsTransportItf {
public:
  Error ReadSnapshot(const Viss31MtlsConfig &config,
                     const std::array<const char *, 10> &paths,
                     Viss31Snapshot &snapshot,
                     std::chrono::milliseconds timeout) override;
  void Cancel() override;

private:
  std::atomic_bool mCanceled{};
};

/**
 * VISS 3.1 mTLS transport adapter for the purpose-bound update-runtime role.
 *
 * It knows only the fixed ten-path transport contract. Safe Stop thresholds
 * deliberately live in SafeStopEvaluator.
 */
class Viss31MtlsVehicleStateProvider final : public VehicleStateProviderItf {
public:
  explicit Viss31MtlsVehicleStateProvider(
      Viss31MtlsTransportItf *transport = nullptr);

  Error Init(const Viss31MtlsConfig &config);
  Error ReadFrame(VehicleStateFrame &frame,
                  std::chrono::milliseconds timeout) override;
  void Cancel() override;

private:
  Error ValidateCredential(const std::filesystem::path &path) const;
  Error ValidateBinding() const;

  Viss31MtlsConfig mConfig;
  Viss31MtlsTransportItf *mTransport{};
  bool mInitialized{};
};

} // namespace aos::sm::launcher

#endif
