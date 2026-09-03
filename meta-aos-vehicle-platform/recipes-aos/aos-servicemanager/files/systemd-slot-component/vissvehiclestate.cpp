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
#include <set>
#include <system_error>

#include <Poco/Dynamic/Var.h>
#include <Poco/JSON/Object.h>
#include <Poco/JSON/Parser.h>
#include <common/utils/exception.hpp>

namespace aos::sm::launcher {

namespace {

constexpr auto cRequiredRole = "PLATFORM_UPDATE_RUNTIME";
constexpr auto cTestOnlyProfile = "LTVP_VISS_SERVER_AUTH_TEST_ONLY";
constexpr auto cTestOnlyEndpoint = "wss://10.0.0.1:6443";
constexpr auto cTestOnlyServerName = "127.0.0.1";
constexpr auto cTestOnlyPathSet = "PLATFORM_FOTA_SAFE_STOP_1_1_1";

bool HasExactKeys(const Poco::JSON::Object::Ptr &object,
                  std::initializer_list<const char *> expected) {
  Poco::JSON::Object::NameList names;
  object->getNames(names);
  std::set<std::string> actual(names.begin(), names.end());
  std::set<std::string> required;
  for (const auto *name : expected) {
    required.emplace(name);
  }
  return actual == required;
}

bool ReadString(const Poco::JSON::Object::Ptr &object, const char *name,
                std::string &value) {
  if (!object->has(name)) {
    return false;
  }
  const auto item = object->get(name);
  if (item.type() != typeid(std::string)) {
    return false;
  }
  value = item.extract<std::string>();
  return !value.empty();
}

bool ReadPositiveInteger(const Poco::JSON::Object::Ptr &object,
                         const char *name, uint64_t &value) {
  if (!object->has(name)) {
    return false;
  }
  const auto item = object->get(name);
  if (item.type() == typeid(Poco::UInt64)) {
    value = item.extract<Poco::UInt64>();
    return value != 0;
  }
  if (item.type() == typeid(Poco::Int64)) {
    const auto signedValue = item.extract<Poco::Int64>();
    if (signedValue <= 0) {
      return false;
    }
    value = static_cast<uint64_t>(signedValue);
    return true;
  }
  if (item.type() == typeid(unsigned)) {
    value = item.extract<unsigned>();
    return value != 0;
  }
  if (item.type() == typeid(int)) {
    const auto signedValue = item.extract<int>();
    if (signedValue <= 0) {
      return false;
    }
    value = static_cast<uint64_t>(signedValue);
    return true;
  }
  return false;
}

bool IsCanonicalUUID(const std::string &value) {
  static const std::regex cCanonicalUUID(
      "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$");
  return std::regex_match(value, cCanonicalUUID);
}

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

Error Viss31MtlsVehicleStateProvider::ValidateCredentialAbsent(
    const std::filesystem::path &path) const {
  std::error_code error;
  const auto status = std::filesystem::symlink_status(path, error);
  if (!error && (std::filesystem::exists(status) ||
                 std::filesystem::is_symlink(status))) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eInvalidArgument,
        "private VISS client material is forbidden in TEST_ONLY mode"));
  }
  if (error && error != std::errc::no_such_file_or_directory) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eFailed,
        "cannot prove private VISS client material absent"));
  }
  return ErrorEnum::eNone;
}

Error Viss31MtlsVehicleStateProvider::ValidateBinding(
    bool &serverAuthenticatedTestOnly) const {
  serverAuthenticatedTestOnly = false;
  try {
    std::ifstream stream(mConfig.mBindingCredential);
    if (!stream.is_open()) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eNotFound,
          "PLATFORM_UPDATE_RUNTIME binding credential is unavailable"));
    }
    Poco::JSON::Parser parser;
    const auto parsed = parser.parse(stream);
    const auto object = parsed.extract<Poco::JSON::Object::Ptr>();
    uint64_t schemaVersion{};
    if (!ReadPositiveInteger(object, "schemaVersion", schemaVersion)) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument,
          "PLATFORM_UPDATE_RUNTIME binding credential is inconsistent"));
    }
    std::string unitID;
    std::string nodeID;
    uint64_t generation{};
    if (schemaVersion == 1) {
      std::string role;
      std::string fingerprint;
      if (!HasExactKeys(object,
                        {"schemaVersion", "unitId", "nodeId", "role",
                         "clientCertificateSha256", "assignmentGeneration"}) ||
          !ReadString(object, "unitId", unitID) ||
          !ReadString(object, "nodeId", nodeID) ||
          !ReadString(object, "role", role) ||
          !ReadString(object, "clientCertificateSha256", fingerprint) ||
          !ReadPositiveInteger(object, "assignmentGeneration", generation) ||
          nodeID != mConfig.mExpectedNodeID || role != mConfig.mRole ||
          !std::regex_match(fingerprint, std::regex("^[0-9a-f]{64}$"))) {
        return AOS_ERROR_WRAP(Error(
            ErrorEnum::eInvalidArgument,
            "PLATFORM_UPDATE_RUNTIME binding credential is inconsistent"));
      }
      return ErrorEnum::eNone;
    }
    std::string profile;
    std::string endpoint;
    std::string serverName;
    std::string pathSet;
    if (schemaVersion != 2 ||
        !HasExactKeys(object,
                      {"schemaVersion", "profile", "unitId", "nodeId",
                       "assignmentGeneration", "endpoint", "tlsServerName",
                       "pathSet"}) ||
        !ReadString(object, "profile", profile) ||
        !ReadString(object, "unitId", unitID) ||
        !ReadString(object, "nodeId", nodeID) ||
        !ReadPositiveInteger(object, "assignmentGeneration", generation) ||
        !ReadString(object, "endpoint", endpoint) ||
        !ReadString(object, "tlsServerName", serverName) ||
        !ReadString(object, "pathSet", pathSet) ||
        profile != cTestOnlyProfile || !IsCanonicalUUID(unitID) ||
        nodeID != mConfig.mExpectedNodeID ||
        endpoint != cTestOnlyEndpoint || endpoint != mConfig.mEndpoint ||
        serverName != cTestOnlyServerName || serverName != mConfig.mServerName ||
        pathSet != cTestOnlyPathSet) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument,
          "PLATFORM_UPDATE_RUNTIME TEST_ONLY binding is inconsistent"));
    }
    serverAuthenticatedTestOnly = true;
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
       {mConfig.mCACredential, mConfig.mBindingCredential}) {
    if (auto err = ValidateCredential(credential); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
  }
  bool serverAuthenticatedTestOnly{};
  if (auto err = ValidateBinding(serverAuthenticatedTestOnly); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (serverAuthenticatedTestOnly) {
    for (const auto &credential :
         {mConfig.mCertificateCredential, mConfig.mPrivateKeyCredential}) {
      if (auto err = ValidateCredentialAbsent(credential); !err.IsNone()) {
        return AOS_ERROR_WRAP(err);
      }
    }
  } else {
    for (const auto &credential :
         {mConfig.mCertificateCredential, mConfig.mPrivateKeyCredential}) {
      if (auto err = ValidateCredential(credential); !err.IsNone()) {
        return AOS_ERROR_WRAP(err);
      }
    }
  }

  auto transportConfig = mConfig;
  transportConfig.mServerAuthenticatedTestOnly = serverAuthenticatedTestOnly;
  Viss31Snapshot snapshot;
  if (auto err =
          mTransport->ReadSnapshot(transportConfig, cSafeStopPaths, snapshot,
                                   timeout);
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
