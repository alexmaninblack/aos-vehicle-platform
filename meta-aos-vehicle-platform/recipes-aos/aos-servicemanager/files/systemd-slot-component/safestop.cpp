/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "safestop.hpp"

#include <cmath>

namespace aos::sm::launcher {

namespace {

bool Complete(const VehicleStateFrame &frame) {
  return frame.mFrameID.has_value() && frame.mActiveMode.has_value() &&
         frame.mTransitionState.has_value() &&
         frame.mControlGeneration.has_value() &&
         frame.mResetGeneration.has_value() &&
         frame.mResetInProgress.has_value() &&
         frame.mResetDiscontinuity.has_value() &&
         frame.mSpeedKmh.has_value() && frame.mAcceleratorPercent.has_value() &&
         frame.mBrakePercent.has_value();
}

bool Finite(const VehicleStateFrame &frame) {
  return std::isfinite(*frame.mSpeedKmh) &&
         std::isfinite(*frame.mAcceleratorPercent) &&
         std::isfinite(*frame.mBrakePercent);
}

} // namespace

SafeStopEvaluation SafeStopEvaluator::Evaluate(
    const std::vector<VehicleStateFrame> &window,
    std::chrono::steady_clock::time_point now) const {
  if (window.size() != cRequiredFrames) {
    return {false, SafeStopReason::eIncompleteWindow};
  }

  const auto expectedControlGeneration = window.front().mControlGeneration;
  const auto expectedResetGeneration = window.front().mResetGeneration;
  std::optional<uint64_t> previousFrame;
  std::optional<std::chrono::steady_clock::time_point> previousAcquisition;

  for (const auto &frame : window) {
    if (!Complete(frame)) {
      return {false, SafeStopReason::eMissingEvidence};
    }
    // Historical frames prove consecutive stability. Freshness is admitted at
    // acquisition; buffered history is never reinterpreted as current state.
    if (frame.mSourceObservedAt > frame.mAcquiredAt) {
      return {false, SafeStopReason::eContradictoryEvidence};
    }
    if (frame.mAcquiredAt - frame.mSourceObservedAt > cMaximumSourceAge) {
      return {false, SafeStopReason::eStaleEvidence};
    }
    if (previousAcquisition.has_value() &&
        frame.mAcquiredAt < *previousAcquisition) {
      return {false, SafeStopReason::eContradictoryEvidence};
    }
    previousAcquisition = frame.mAcquiredAt;
    if (previousFrame.has_value() && *frame.mFrameID <= *previousFrame) {
      return {false, SafeStopReason::eRepeatedOrOutOfOrderFrame};
    }
    previousFrame = frame.mFrameID;
    if (frame.mControlGeneration != expectedControlGeneration ||
        frame.mResetGeneration != expectedResetGeneration || !Finite(frame) ||
        *frame.mSpeedKmh < 0.0 || *frame.mAcceleratorPercent < 0.0 ||
        *frame.mAcceleratorPercent > 100.0 || *frame.mBrakePercent < 0.0 ||
        *frame.mBrakePercent > 100.0) {
      return {false, SafeStopReason::eContradictoryEvidence};
    }
    if (*frame.mActiveMode != "SAFE_STOP" ||
        *frame.mTransitionState != "STABLE") {
      return {false, SafeStopReason::eTransitionIncomplete};
    }
    if (*frame.mResetInProgress || *frame.mResetDiscontinuity) {
      return {false, SafeStopReason::eReset};
    }
    if (*frame.mSpeedKmh > cMaximumSpeedKmh ||
        *frame.mAcceleratorPercent > cMaximumAcceleratorPercent ||
        *frame.mBrakePercent < cMinimumBrakePercent) {
      return {false, SafeStopReason::eNotStopped};
    }
  }

  // Only the latest observation represents current vehicle state at a gate.
  // Recheck it at every destructive boundary; old window members remain
  // stability evidence even though their source timestamps are now older.
  const auto &latest = window.back();
  if (latest.mSourceObservedAt > now ||
      now - latest.mSourceObservedAt > cMaximumSourceAge) {
    return {false, SafeStopReason::eStaleEvidence};
  }

  return {true, SafeStopReason::eReady};
}

} // namespace aos::sm::launcher
