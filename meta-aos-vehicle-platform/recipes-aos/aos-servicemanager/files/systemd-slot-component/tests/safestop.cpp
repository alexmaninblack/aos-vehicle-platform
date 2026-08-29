/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <gtest/gtest.h>

#include <limits>

#include "safestop.hpp"

namespace aos::sm::launcher {

namespace {

VehicleStateFrame SafeFrame(
    uint64_t id, std::chrono::steady_clock::time_point sourceObserved,
    std::chrono::steady_clock::time_point acquired) {
  return {id, "SAFE_STOP", "STABLE", 9, 4, false, false,
          0.3, 0.5, 95.0, sourceObserved, acquired};
}

std::vector<VehicleStateFrame>
SafeWindow(std::chrono::steady_clock::time_point now) {
  std::vector<VehicleStateFrame> result;
  for (uint64_t id = 1; id <= SafeStopEvaluator::cRequiredFrames; ++id) {
    const auto acquired =
        now - std::chrono::milliseconds{50} *
                  (SafeStopEvaluator::cRequiredFrames - id);
    result.push_back(
        SafeFrame(id, acquired - std::chrono::milliseconds{5}, acquired));
  }
  return result;
}

} // namespace

TEST(SafeStopEvaluatorTest, AcceptsExactThresholdsAcrossDistinctFrames) {
  const auto now = std::chrono::steady_clock::now();
  // The stability history spans 550 ms. Each sample was fresh when captured,
  // while only the latest sample is required to remain current at this gate.
  EXPECT_TRUE(SafeStopEvaluator{}.Evaluate(SafeWindow(now), now).mReady);
}

TEST(SafeStopEvaluatorTest,
     RejectsIncompleteRepeatedAndStaleAtAcquisitionWindows) {
  const auto now = std::chrono::steady_clock::now();
  auto window = SafeWindow(now);
  window.pop_back();
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eIncompleteWindow);

  window = SafeWindow(now);
  window.back().mFrameID = window[window.size() - 2].mFrameID;
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eRepeatedOrOutOfOrderFrame);

  window = SafeWindow(now);
  window.front().mSourceObservedAt =
      window.front().mAcquiredAt - std::chrono::milliseconds{251};
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eStaleEvidence);
}

TEST(SafeStopEvaluatorTest, RejectsLatestSampleThatAgedPastTheGateLimit) {
  const auto now = std::chrono::steady_clock::now();
  auto window = SafeWindow(now);
  EXPECT_EQ(SafeStopEvaluator{}
                .Evaluate(window, now + std::chrono::milliseconds{246})
                .mReason,
            SafeStopReason::eStaleEvidence);
}

TEST(SafeStopEvaluatorTest, RejectsMissingAndNonMonotonicEvidence) {
  const auto now = std::chrono::steady_clock::now();
  auto window = SafeWindow(now);
  window.back().mSpeedKmh.reset();
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eMissingEvidence);

  window = SafeWindow(now);
  window.back().mAcquiredAt = window[window.size() - 2].mAcquiredAt -
                              std::chrono::milliseconds{1};
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eContradictoryEvidence);
}

TEST(SafeStopEvaluatorTest, RejectsModeResetGenerationAndMotionFailures) {
  const auto now = std::chrono::steady_clock::now();
  auto window = SafeWindow(now);
  window.back().mActiveMode = "AUTOPILOT";
  EXPECT_FALSE(SafeStopEvaluator{}.Evaluate(window, now).mReady);

  window = SafeWindow(now);
  window.back().mResetDiscontinuity = true;
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eReset);

  window = SafeWindow(now);
  window.back().mControlGeneration = 10;
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eContradictoryEvidence);

  window = SafeWindow(now);
  window.back().mBrakePercent = 94.999;
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eNotStopped);

  window = SafeWindow(now);
  window.back().mSpeedKmh = std::numeric_limits<double>::quiet_NaN();
  EXPECT_EQ(SafeStopEvaluator{}.Evaluate(window, now).mReason,
            SafeStopReason::eContradictoryEvidence);
}

} // namespace aos::sm::launcher
