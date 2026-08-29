/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_SAFESTOP_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_SAFESTOP_HPP_

#include <array>
#include <chrono>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <core/common/tools/error.hpp>

namespace aos::sm::launcher {

/** The ten Gateway facts admitted by Safe Stop Profile 1.1.1 / D4-028. */
struct VehicleStateFrame {
  std::optional<uint64_t> mFrameID;
  std::optional<std::string> mActiveMode;
  std::optional<std::string> mTransitionState;
  std::optional<uint64_t> mControlGeneration;
  std::optional<uint64_t> mResetGeneration;
  std::optional<bool> mResetInProgress;
  std::optional<bool> mResetDiscontinuity;
  std::optional<double> mSpeedKmh;
  std::optional<double> mAcceleratorPercent;
  std::optional<double> mBrakePercent;
  /** Source timestamp projected onto the local monotonic clock at capture. */
  std::chrono::steady_clock::time_point mSourceObservedAt{};
  /** Local monotonic time at which this coherent frame was acquired. */
  std::chrono::steady_clock::time_point mAcquiredAt{};
};

/** Cancelable, transport-only source of one coherent Gateway frame. */
class VehicleStateProviderItf {
public:
  virtual ~VehicleStateProviderItf() = default;

  virtual Error ReadFrame(VehicleStateFrame &frame,
                          std::chrono::milliseconds timeout) = 0;
  virtual void Cancel() = 0;
};

enum class SafeStopReason {
  eReady,
  eIncompleteWindow,
  eMissingEvidence,
  eStaleEvidence,
  eRepeatedOrOutOfOrderFrame,
  eContradictoryEvidence,
  eTransitionIncomplete,
  eReset,
  eNotStopped,
};

struct SafeStopEvaluation {
  bool mReady{};
  SafeStopReason mReason{SafeStopReason::eIncompleteWindow};
};

/** Pure Platform FOTA Safe Stop Profile 1.1.1 / D4-028 evaluator. */
class SafeStopEvaluator final {
public:
  static constexpr size_t cRequiredFrames = 12;
  static constexpr auto cMaximumSourceAge = std::chrono::milliseconds{250};
  static constexpr double cMaximumSpeedKmh = 0.3;
  static constexpr double cMaximumAcceleratorPercent = 0.5;
  static constexpr double cMinimumBrakePercent = 95.0;

  SafeStopEvaluation
  Evaluate(const std::vector<VehicleStateFrame> &window,
           std::chrono::steady_clock::time_point now) const;
};

/** Exact read allowlist for the PLATFORM_UPDATE_RUNTIME VISS role. */
inline constexpr std::array<const char *, 10> cSafeStopPaths = {
    "Vehicle.CarlaSimulation.FrameId",
    "Vehicle.CarlaSimulation.Control.ActiveMode",
    "Vehicle.CarlaSimulation.Control.TransitionState",
    "Vehicle.CarlaSimulation.Control.Generation",
    "Vehicle.CarlaSimulation.Reset.Generation",
    "Vehicle.CarlaSimulation.Reset.InProgress",
    "Vehicle.CarlaSimulation.Reset.Discontinuity",
    "Vehicle.Speed",
    "Vehicle.Chassis.Accelerator.PedalPosition",
    "Vehicle.Chassis.Brake.PedalPosition",
};

} // namespace aos::sm::launcher

#endif
