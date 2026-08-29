/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "vissvehiclestate.hpp"

#include <cerrno>
#include <charconv>
#include <cmath>
#include <fstream>
#include <regex>
#include <system_error>

#include <common/utils/exception.hpp>
#include <common/utils/json.hpp>

namespace aos::sm::launcher {

namespace {

constexpr auto cRequiredRole = "PLATFORM_UPDATE_RUNTIME";

Error ParseUnsigned(const std::string &value, uint64_t &result) {
  const auto parsed =
      std::from_chars(value.data(), value.data() + value.size(), result);
  if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size()) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "invalid VISS unsigned value"));
  }
  return ErrorEnum::eNone;
}

Error ParseDouble(const std::string &value, double &result) {
  const auto parsed =
      std::from_chars(value.data(), value.data() + value.size(), result);
  if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
      !std::isfinite(result)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "invalid VISS numeric value"));
  }
  return ErrorEnum::eNone;
}

Error ParseBool(const std::string &value, bool &result) {
  if (value == "true") {
    result = true;
  } else if (value == "false") {
    result = false;
  } else {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "invalid VISS Boolean value"));
  }
  return ErrorEnum::eNone;
}

const std::string *Find(const Viss31Snapshot &snapshot, const char *path) {
  const auto item = snapshot.mValues.find(path);
  return item == snapshot.mValues.end() ? nullptr : &item->second;
}

} // namespace

Viss31MtlsVehicleStateProvider::Viss31MtlsVehicleStateProvider(
    Viss31MtlsTransportItf *transport)
    : mTransport(transport) {}

Error Viss31MtlsVehicleStateProvider::ValidateCredential(
    const std::filesystem::path &path) const {
  std::error_code error;
  const auto status = std::filesystem::symlink_status(path, error);
  if (error || std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status) || path.empty()) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eNotFound,
        "PLATFORM_UPDATE_RUNTIME systemd credential is unavailable"));
  }
  return ErrorEnum::eNone;
}

Error Viss31MtlsVehicleStateProvider::ValidateBinding() const {
  try {
    std::ifstream stream(mConfig.mBindingCredential);
    if (!stream.is_open()) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eNotFound,
          "PLATFORM_UPDATE_RUNTIME binding credential is unavailable"));
    }
    auto parsed = common::utils::ParseJson(stream);
    if (!parsed.mError.IsNone()) {
      return AOS_ERROR_WRAP(parsed.mError);
    }
    const auto object =
        common::utils::CaseInsensitiveObjectWrapper(parsed.mValue);
    const auto unitID = object.GetValue<std::string>("unitId");
    const auto nodeID = object.GetValue<std::string>("nodeId");
    const auto role = object.GetValue<std::string>("role");
    const auto fingerprint =
        object.GetValue<std::string>("clientCertificateSha256");
    const auto generation =
        object.GetValue<uint64_t>("assignmentGeneration");
    if (object.GetValue<uint32_t>("schemaVersion") != 1 || unitID.empty() ||
        nodeID != mConfig.mExpectedNodeID || role != mConfig.mRole ||
        generation == 0 ||
        !std::regex_match(fingerprint, std::regex("^[0-9a-f]{64}$"))) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument,
          "PLATFORM_UPDATE_RUNTIME binding credential is inconsistent"));
    }
  } catch (const std::exception &exception) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(
        exception, ErrorEnum::eInvalidArgument));
  }
  return ErrorEnum::eNone;
}

Error Viss31MtlsVehicleStateProvider::Init(const Viss31MtlsConfig &config) {
  if (mTransport == nullptr || config.mRole != cRequiredRole ||
      config.mEndpoint.rfind("wss://", 0) != 0 ||
      config.mServerName.empty()) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eInvalidArgument,
        "invalid purpose-bound VISS 3.1 mTLS configuration"));
  }
  mConfig = config;
  mInitialized = true;
  return ErrorEnum::eNone;
}

Error Viss31MtlsVehicleStateProvider::ReadFrame(
    VehicleStateFrame &frame, std::chrono::milliseconds timeout) {
  if (!mInitialized) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eWrongState,
        "PLATFORM_UPDATE_RUNTIME VISS adapter is not initialized"));
  }
  for (const auto &credential :
       {mConfig.mCACredential, mConfig.mCertificateCredential,
        mConfig.mPrivateKeyCredential, mConfig.mBindingCredential}) {
    if (auto err = ValidateCredential(credential); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
  }
  if (auto err = ValidateBinding(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  Viss31Snapshot snapshot;
  if (auto err =
          mTransport->ReadSnapshot(mConfig, cSafeStopPaths, snapshot, timeout);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  for (const auto *path : cSafeStopPaths) {
    if (Find(snapshot, path) == nullptr || snapshot.mValues.size() != 10) {
      return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                  "incomplete or widened VISS snapshot"));
    }
  }

  uint64_t frameID{};
  uint64_t controlGeneration{};
  uint64_t resetGeneration{};
  bool resetInProgress{};
  bool resetDiscontinuity{};
  double speed{};
  double accelerator{};
  double brake{};
  if (auto err = ParseUnsigned(*Find(snapshot, cSafeStopPaths[0]), frameID);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err =
          ParseUnsigned(*Find(snapshot, cSafeStopPaths[3]), controlGeneration);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err =
          ParseUnsigned(*Find(snapshot, cSafeStopPaths[4]), resetGeneration);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err =
          ParseBool(*Find(snapshot, cSafeStopPaths[5]), resetInProgress);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err =
          ParseBool(*Find(snapshot, cSafeStopPaths[6]), resetDiscontinuity);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = ParseDouble(*Find(snapshot, cSafeStopPaths[7]), speed);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = ParseDouble(*Find(snapshot, cSafeStopPaths[8]), accelerator);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = ParseDouble(*Find(snapshot, cSafeStopPaths[9]), brake);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  frame = {frameID,
           *Find(snapshot, cSafeStopPaths[1]),
           *Find(snapshot, cSafeStopPaths[2]),
           controlGeneration,
           resetGeneration,
           resetInProgress,
           resetDiscontinuity,
           speed,
           accelerator,
           brake,
           snapshot.mSourceObservedAt,
           snapshot.mAcquiredAt};
  return ErrorEnum::eNone;
}

void Viss31MtlsVehicleStateProvider::Cancel() {
  if (mTransport != nullptr) {
    mTransport->Cancel();
  }
}

} // namespace aos::sm::launcher
