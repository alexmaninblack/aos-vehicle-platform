/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "runtime.hpp"

#include <array>
#include <cerrno>
#include <fcntl.h>
#include <fstream>
#include <memory>
#include <regex>
#include <sstream>
#include <sys/stat.h>
#include <system_error>
#include <unistd.h>
#include <utility>

#include <Poco/JSON/Object.h>

#include <core/common/tools/logger.hpp>

#include <common/utils/exception.hpp>
#include <common/utils/json.hpp>

#include <sm/launcher/runtimes/utils/utils.hpp>

#include "providerarchive.hpp"

namespace aos::sm::launcher {

namespace {

constexpr size_t cMaxInstances = 1;
constexpr size_t cMaxPayloadEntries = 4096;
constexpr size_t cMaxRelativePathLength = 240;
constexpr auto cInstalledFile = "installed.json";
constexpr auto cTransactionFile = "transaction.json";
constexpr auto cFailureFile = "last-failure.json";
constexpr auto cStagingDirectory = "staging";
constexpr auto cInstanceFile = ".aos-instance.json";
constexpr auto cComponentMetadata = "component.json";
constexpr auto cProviderExecutable = "bin/vehicle-data-provider";
constexpr auto cProviderConfiguration = "config/provider.json";
constexpr auto cComponentName = "vehicle-data-provider";
constexpr auto cComponentOS = "linux";
constexpr auto cRuntimeInterface = 1U;

Error FromFilesystemError(const std::error_code &error, const char *message) {
  return AOS_ERROR_WRAP(Error(error.value(), message));
}

Error EnsureDirectory(const std::filesystem::path &path,
                      std::filesystem::perms permissions) {
  std::error_code error;
  const auto status = std::filesystem::symlink_status(path, error);
  if (error && error != std::errc::no_such_file_or_directory) {
    return FromFilesystemError(error, "cannot inspect component directory");
  }
  if (std::filesystem::is_symlink(status) ||
      (std::filesystem::exists(status) &&
       !std::filesystem::is_directory(status))) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe component directory"));
  }

  std::filesystem::create_directories(path, error);
  if (error) {
    return FromFilesystemError(error, "cannot create component directory");
  }
  std::filesystem::permissions(path, permissions,
                               std::filesystem::perm_options::replace, error);
  if (error) {
    return FromFilesystemError(error,
                               "cannot set component directory permissions");
  }

  return ErrorEnum::eNone;
}

Error SyncDirectory(const std::filesystem::path &path) {
  const int descriptor = open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (descriptor < 0) {
    return AOS_ERROR_WRAP(Error(errno, "cannot open state directory"));
  }

  const int result = fsync(descriptor);
  const int savedError = errno;
  close(descriptor);
  if (result != 0) {
    return AOS_ERROR_WRAP(Error(savedError, "cannot flush state directory"));
  }

  return ErrorEnum::eNone;
}

Error AtomicWrite(const std::filesystem::path &path, const std::string &data,
                  mode_t mode = 0600) {
  const auto temporary = path.string() + ".tmp";
  struct stat status {};
  if (lstat(temporary.c_str(), &status) == 0 && S_ISLNK(status.st_mode)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe state temporary file"));
  }

  const int descriptor =
      open(temporary.c_str(),
           O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW, mode);
  if (descriptor < 0) {
    return AOS_ERROR_WRAP(Error(errno, "cannot create state file"));
  }
  if (fchmod(descriptor, mode) != 0) {
    const int savedError = errno;
    close(descriptor);
    unlink(temporary.c_str());
    return AOS_ERROR_WRAP(Error(savedError, "cannot protect state file"));
  }

  size_t offset = 0;
  while (offset < data.size()) {
    const auto count =
        write(descriptor, data.data() + offset, data.size() - offset);
    if (count < 0) {
      const int savedError = errno;
      close(descriptor);
      unlink(temporary.c_str());
      return AOS_ERROR_WRAP(Error(savedError, "cannot write state file"));
    }
    offset += static_cast<size_t>(count);
  }

  if (fsync(descriptor) != 0) {
    const int savedError = errno;
    close(descriptor);
    unlink(temporary.c_str());
    return AOS_ERROR_WRAP(Error(savedError, "cannot flush state file"));
  }
  if (close(descriptor) != 0) {
    const int savedError = errno;
    unlink(temporary.c_str());
    return AOS_ERROR_WRAP(Error(savedError, "cannot close state file"));
  }
  if (rename(temporary.c_str(), path.c_str()) != 0) {
    const int savedError = errno;
    unlink(temporary.c_str());
    return AOS_ERROR_WRAP(Error(savedError, "cannot commit state file"));
  }

  return SyncDirectory(path.parent_path());
}

std::string Stringify(const Poco::JSON::Object::Ptr &object) {
  std::ostringstream stream;
  object->stringify(stream);
  stream << '\n';
  return stream.str();
}

void StoreInstance(Poco::JSON::Object &object, const std::string &prefix,
                   const InstanceInfo &instance) {
  object.set(prefix + "ItemId", instance.mItemID.CStr());
  object.set(prefix + "SubjectId", instance.mSubjectID.CStr());
  object.set(prefix + "Instance", instance.mInstance);
  object.set(prefix + "Version", instance.mVersion.CStr());
  object.set(prefix + "ManifestDigest", instance.mManifestDigest.CStr());
  object.set(prefix + "RuntimeId", instance.mRuntimeID.CStr());
  object.set(prefix + "Preinstalled", instance.mPreinstalled);
}

Error LoadInstance(const common::utils::CaseInsensitiveObjectWrapper &object,
                   const std::string &prefix, InstanceInfo &instance) {
  try {
    auto err = instance.mItemID.Assign(
        object.GetValue<std::string>(prefix + "ItemId").c_str());
    if (!err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    err = instance.mSubjectID.Assign(
        object.GetValue<std::string>(prefix + "SubjectId").c_str());
    if (!err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    instance.mInstance = object.GetValue<uint64_t>(prefix + "Instance");
    err = instance.mVersion.Assign(
        object.GetValue<std::string>(prefix + "Version").c_str());
    if (!err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    err = instance.mManifestDigest.Assign(
        object.GetValue<std::string>(prefix + "ManifestDigest").c_str());
    if (!err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    err = instance.mRuntimeID.Assign(
        object.GetValue<std::string>(prefix + "RuntimeId").c_str());
    if (!err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    instance.mPreinstalled = object.GetValue<bool>(prefix + "Preinstalled");
    instance.mType = UpdateItemTypeEnum::eComponent;
  } catch (const std::exception &error) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(error));
  }

  return ErrorEnum::eNone;
}

const char *PhaseToString(ComponentTransactionPhase phase) {
  switch (phase) {
  case ComponentTransactionPhase::ePrepared:
    return "prepared";
  case ComponentTransactionPhase::eUnavailable:
    return "unavailable";
  case ComponentTransactionPhase::ePreviousStopped:
    return "previous-stopped";
  case ComponentTransactionPhase::eSwitched:
    return "switched";
  case ComponentTransactionPhase::eCandidateStarted:
    return "candidate-started";
  }

  return "invalid";
}

Error StringToPhase(const std::string &value,
                    ComponentTransactionPhase &phase) {
  if (value == "prepared") {
    phase = ComponentTransactionPhase::ePrepared;
  } else if (value == "unavailable") {
    phase = ComponentTransactionPhase::eUnavailable;
  } else if (value == "previous-stopped") {
    phase = ComponentTransactionPhase::ePreviousStopped;
  } else if (value == "switched") {
    phase = ComponentTransactionPhase::eSwitched;
  } else if (value == "candidate-started") {
    phase = ComponentTransactionPhase::eCandidateStarted;
  } else {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "invalid transaction phase"));
  }

  return ErrorEnum::eNone;
}

Error ParseSemVer(const std::string &value, std::array<uint64_t, 3> &result) {
  static const std::regex expression(R"(^([0-9]+)\.([0-9]+)\.([0-9]+)$)");
  std::smatch match;
  if (!std::regex_match(value, match, expression)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "version is not canonical semver"));
  }

  try {
    for (size_t index = 0; index < result.size(); ++index) {
      const auto token = match[index + 1].str();
      if ((token.size() > 1 && token[0] == '0') || token.size() > 19) {
        return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                    "version is not canonical semver"));
      }
      result[index] = std::stoull(token);
    }
  } catch (const std::exception &error) {
    return AOS_ERROR_WRAP(
        common::utils::ToAosError(error, ErrorEnum::eInvalidArgument));
  }

  return ErrorEnum::eNone;
}

bool ContainsControlCharacter(const std::string &value) {
  for (const unsigned char character : value) {
    if (character < 0x20 || character == 0x7f) {
      return true;
    }
  }
  return false;
}

Error SealPayload(const std::filesystem::path &root) {
  std::error_code error;
  for (const auto &entry :
       std::filesystem::recursive_directory_iterator(root)) {
    auto permissions = entry.status().permissions();
    permissions &= ~(std::filesystem::perms::owner_write |
                     std::filesystem::perms::group_write |
                     std::filesystem::perms::others_write);
    std::filesystem::permissions(entry.path(), permissions,
                                 std::filesystem::perm_options::replace, error);
    if (error) {
      return FromFilesystemError(error, "cannot seal component payload");
    }
  }
  std::filesystem::permissions(root,
                               std::filesystem::perms::owner_read |
                                   std::filesystem::perms::owner_exec |
                                   std::filesystem::perms::group_read |
                                   std::filesystem::perms::group_exec |
                                   std::filesystem::perms::others_read |
                                   std::filesystem::perms::others_exec,
                               std::filesystem::perm_options::replace, error);
  if (error) {
    return FromFilesystemError(error, "cannot seal component root");
  }

  return ErrorEnum::eNone;
}

} // namespace

SystemdSlotComponentRuntime::SystemdSlotComponentRuntime(
    ProviderProfileItf *profileOverride)
    : mProfile(profileOverride) {}

Error SystemdSlotComponentRuntime::Init(
    const RuntimeConfig &config,
    iamclient::CurrentNodeInfoProviderItf &currentNodeInfoProvider,
    imagemanager::ItemInfoProviderItf &itemInfoProvider,
    oci::OCISpecItf &ociSpec, InstanceStatusReceiverItf &statusReceiver,
    sm::utils::SystemdConnItf &systemdConn) {
  if (config.mPlugin != cRuntimeSystemdSlotComponent || !config.isComponent ||
      config.mType.empty() || !config.mConfig) {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                "invalid systemd slot component runtime"));
  }
  if (auto err = ParseConfig(config, mConfig); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  auto nodeInfo = std::make_unique<NodeInfo>();
  if (auto err = currentNodeInfoProvider.GetCurrentNodeInfo(*nodeInfo);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = utils::CreateRuntimeInfo(config.mType, *nodeInfo,
                                          cMaxInstances, mRuntimeInfo);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = mNodeID.Assign(nodeInfo->mNodeID); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  mItemInfoProvider = &itemInfoProvider;
  mOCISpec = &ociSpec;
  mStatusReceiver = &statusReceiver;
  if (mProfile == nullptr) {
    if (auto err = mDefaultProfile.Init(mConfig, systemdConn); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    mProfile = &mDefaultProfile;
  }

  return EnsureStore();
}

Error SystemdSlotComponentRuntime::Start() {
  std::lock_guard lock{mMutex};
  if (auto err = EnsureStore(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  mStarted = true;
  if (auto err = Recover(); !err.IsNone()) {
    mStarted = false;
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = GarbageCollect(); !err.IsNone()) {
    mStarted = false;
    return AOS_ERROR_WRAP(err);
  }

  LOG_INF() << "Vehicle data provider component runtime started"
            << Log::Field("runtimeType", mRuntimeInfo.mRuntimeType)
            << Log::Field("installed", mInstalled.has_value());

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Stop() {
  std::lock_guard lock{mMutex};
  mStarted = false;
  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::GetRuntimeInfo(
    RuntimeInfo &runtimeInfo) const {
  std::lock_guard lock{mMutex};
  runtimeInfo = mRuntimeInfo;
  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::StartInstance(const InstanceInfo &instance,
                                                 InstanceStatus &status) {
  std::lock_guard lock{mMutex};
  if (!mStarted || instance.mRuntimeID != mRuntimeInfo.mRuntimeID ||
      instance.mType != UpdateItemTypeEnum::eComponent ||
      instance.mInstance != 0) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eWrongState, "component runtime is not ready"));
  }

  auto existing = std::make_unique<ComponentTransaction>();
  if (auto err = LoadTransaction(*existing); !err.Is(ErrorEnum::eNotFound)) {
    if (!err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eWrongState, "component update is already active"));
  }

  if (mInstalled.has_value() &&
      mInstalled->mInstance.mManifestDigest == instance.mManifestDigest) {
    FillStatus(*mInstalled, InstanceStateEnum::eActive, ErrorEnum::eNone,
               status);
    return ErrorEnum::eNone;
  }

  FillStatus(instance, InstanceStateEnum::eActivating, ErrorEnum::eNone,
             status);
  Notify(status);

  if (auto err = CheckVersionPolicy(instance); !err.IsNone()) {
    FillStatus(instance, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }

  auto candidate = std::make_unique<ComponentRelease>();
  if (auto err = PrepareCandidate(instance, *candidate); !err.IsNone()) {
    FillStatus(instance, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }

  auto transaction = std::make_unique<ComponentTransaction>();
  transaction->mCandidate = *candidate;
  transaction->mPrevious = mInstalled;
  transaction->mPhase = ComponentTransactionPhase::ePrepared;
  if (auto err = SaveTransaction(*transaction); !err.IsNone()) {
    FillStatus(instance, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }

  auto activationError = Activate(*candidate, mInstalled);
  if (!activationError.IsNone()) {
    auto durableTransaction =
        std::make_unique<ComponentTransaction>(*transaction);
    if (auto loadError = LoadTransaction(*durableTransaction);
        !loadError.IsNone()) {
      LOG_ERR() << "Cannot reload failed component transaction"
                << Log::Field(loadError);
    } else if (auto rollbackError =
                   Rollback(*durableTransaction, activationError);
               !rollbackError.IsNone()) {
      LOG_ERR() << "Automatic provider rollback failed"
                << Log::Field(rollbackError);
    }

    FillStatus(instance, InstanceStateEnum::eFailed, activationError, status);
    Notify(status);
    if (mInstalled.has_value()) {
      auto restored = std::make_unique<InstanceStatus>();
      FillStatus(*mInstalled, InstanceStateEnum::eActive, ErrorEnum::eNone,
                 *restored);
      Notify(*restored);
    }
    return AOS_ERROR_WRAP(activationError);
  }

  FillStatus(*candidate, InstanceStateEnum::eActive, ErrorEnum::eNone, status);
  Notify(status);
  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::StopInstance(const InstanceIdent &instance,
                                                InstanceStatus &status) {
  std::lock_guard lock{mMutex};
  if (!mStarted || !mInstalled.has_value() ||
      static_cast<const InstanceIdent &>(mInstalled->mInstance) != instance) {
    FillStatus(instance, InstanceStateEnum::eFailed,
               Error(ErrorEnum::eNotFound,
                     "vehicle data provider component is not active"),
               status);
    Notify(status);
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eNotFound, "vehicle data provider component is not active"));
  }

  if (auto err = mProfile->MarkUnavailable(); !err.IsNone()) {
    FillStatus(*mInstalled, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = mProfile->StopProvider(); !err.IsNone()) {
    FillStatus(*mInstalled, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = RemoveActive(); !err.IsNone()) {
    FillStatus(*mInstalled, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = RemoveStateFile(StatePath(cInstalledFile)); !err.IsNone()) {
    FillStatus(*mInstalled, InstanceStateEnum::eFailed, err, status);
    Notify(status);
    return AOS_ERROR_WRAP(err);
  }

  auto stopped = std::make_unique<ComponentRelease>(*mInstalled);
  mInstalled.reset();
  FillStatus(*stopped, InstanceStateEnum::eInactive, ErrorEnum::eNone, status);
  Notify(status);
  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Reboot() {
  return AOS_ERROR_WRAP(
      Error(ErrorEnum::eNotSupported,
            "provider component updates do not reboot the Node"));
}

Error SystemdSlotComponentRuntime::GetInstanceMonitoringData(
    const InstanceIdent &instanceIdent,
    monitoring::InstanceMonitoringData &monitoringData) {
  std::lock_guard lock{mMutex};
  (void)monitoringData;
  if (!mInstalled.has_value() || static_cast<const InstanceIdent &>(
                                     mInstalled->mInstance) != instanceIdent) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eNotFound, "provider component is not active"));
  }

  return AOS_ERROR_WRAP(
      Error(ErrorEnum::eNotSupported, "component monitoring is not available"));
}

Error SystemdSlotComponentRuntime::EnsureStore() const {
  constexpr auto cReadableDirectory =
      std::filesystem::perms::owner_all | std::filesystem::perms::group_read |
      std::filesystem::perms::group_exec | std::filesystem::perms::others_read |
      std::filesystem::perms::others_exec;
  constexpr auto cPrivateDirectory = std::filesystem::perms::owner_all;

  for (const auto &item :
       {std::pair{mConfig.mWorkingDir, cReadableDirectory},
        std::pair{mConfig.mWorkingDir / "slots", cReadableDirectory},
        std::pair{mConfig.mWorkingDir / "state", cPrivateDirectory},
        std::pair{mConfig.mWorkingDir / "credentials", cPrivateDirectory}}) {
    if (auto err = EnsureDirectory(item.first, item.second); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Recover() {
  auto transaction = std::make_unique<ComponentTransaction>();
  auto transactionError = LoadTransaction(*transaction);
  if (!transactionError.IsNone() &&
      !transactionError.Is(ErrorEnum::eNotFound)) {
    return AOS_ERROR_WRAP(transactionError);
  }

  auto installed = std::make_unique<ComponentRelease>();
  auto installedError = LoadRelease(StatePath(cInstalledFile), *installed);
  if (!installedError.IsNone() && !installedError.Is(ErrorEnum::eNotFound)) {
    return AOS_ERROR_WRAP(installedError);
  }

  if (transactionError.Is(ErrorEnum::eNotFound)) {
    if (installedError.Is(ErrorEnum::eNotFound)) {
      mInstalled.reset();
      std::string active;
      auto activeError = ReadActive(active);
      if (activeError.Is(ErrorEnum::eNotFound)) {
        return ErrorEnum::eNone;
      }
      return AOS_ERROR_WRAP(
          Error(ErrorEnum::eWrongState,
                "active slot exists without committed component state"));
    }

    if (auto err = ValidateReleaseSlot(*installed); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    std::string active;
    if (auto err = ReadActive(active);
        !err.IsNone() || active != installed->mSlot) {
      return AOS_ERROR_WRAP(Error(ErrorEnum::eWrongState,
                                  "installed component slot is not active"));
    }
    if (auto err = mProfile->CheckHealth(); !err.IsNone()) {
      if (auto startError = mProfile->StartProvider(); !startError.IsNone()) {
        return AOS_ERROR_WRAP(startError);
      }
      if (auto healthError = mProfile->CheckHealth(); !healthError.IsNone()) {
        return AOS_ERROR_WRAP(healthError);
      }
    }

    mInstalled = *installed;
    auto status = std::make_unique<InstanceStatus>();
    FillStatus(*installed, InstanceStateEnum::eActive, ErrorEnum::eNone,
               *status);
    Notify(*status);
    return ErrorEnum::eNone;
  }

  std::string active;
  const auto activeError = ReadActive(active);
  if (installedError.IsNone() &&
      installed->mInstance.mManifestDigest ==
          transaction->mCandidate.mInstance.mManifestDigest &&
      installed->mSlot == transaction->mCandidate.mSlot &&
      activeError.IsNone() && active == installed->mSlot &&
      mProfile->CheckHealth().IsNone()) {
    mInstalled = *installed;
    if (auto err = RemoveStateFile(StatePath(cTransactionFile));
        !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    auto status = std::make_unique<InstanceStatus>();
    FillStatus(*installed, InstanceStateEnum::eActive, ErrorEnum::eNone,
               *status);
    Notify(*status);
    return ErrorEnum::eNone;
  }

  const auto interruption =
      Error(ErrorEnum::eFailed, "interrupted provider update was rolled back");
  if (auto err = Rollback(*transaction, interruption); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  auto failed = std::make_unique<InstanceStatus>();
  FillStatus(transaction->mCandidate, InstanceStateEnum::eFailed, interruption,
             *failed);
  Notify(*failed);
  if (mInstalled.has_value()) {
    auto restored = std::make_unique<InstanceStatus>();
    FillStatus(*mInstalled, InstanceStateEnum::eActive, ErrorEnum::eNone,
               *restored);
    Notify(*restored);
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::GarbageCollect() const {
  for (const auto &path : {StatePath(cStagingDirectory),
                           StatePath(std::string(cInstalledFile) + ".tmp"),
                           StatePath(std::string(cTransactionFile) + ".tmp"),
                           StatePath(std::string(cFailureFile) + ".tmp")}) {
    std::error_code error;
    const auto status = std::filesystem::symlink_status(path, error);
    if (error && error != std::errc::no_such_file_or_directory) {
      return FromFilesystemError(error, "cannot inspect stale component state");
    }
    if (!std::filesystem::exists(status) &&
        !std::filesystem::is_symlink(status)) {
      continue;
    }
    std::filesystem::remove_all(path, error);
    if (error) {
      return FromFilesystemError(error, "cannot remove stale component state");
    }
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::PrepareCandidate(
    const InstanceInfo &instance, ComponentRelease &candidate) {
  StaticString<cFilePathLen> manifestPath;
  if (auto err = mItemInfoProvider->GetBlobPath(instance.mManifestDigest,
                                                manifestPath);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  auto manifest = std::make_unique<oci::ImageManifest>();
  if (auto err = mOCISpec->LoadImageManifest(manifestPath, *manifest);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = ValidateManifest(*manifest); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  StaticString<cFilePathLen> layerPath;
  if (auto err = mItemInfoProvider->GetLayerPath(manifest->mLayers[0].mDigest,
                                                 layerPath);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  candidate.mInstance = instance;
  candidate.mSlot =
      mInstalled.has_value() && mInstalled->mSlot == "a" ? "b" : "a";
  const auto target = SlotPath(candidate.mSlot);
  const auto staging = StatePath(cStagingDirectory);

  std::error_code filesystemError;
  const auto targetStatus =
      std::filesystem::symlink_status(target, filesystemError);
  if (filesystemError &&
      filesystemError != std::errc::no_such_file_or_directory) {
    return FromFilesystemError(filesystemError, "cannot inspect inactive slot");
  }
  if (std::filesystem::is_symlink(targetStatus)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "inactive slot is a symbolic link"));
  }
  std::filesystem::remove_all(target, filesystemError);
  if (filesystemError) {
    return FromFilesystemError(filesystemError, "cannot clear inactive slot");
  }
  std::filesystem::remove_all(staging, filesystemError);
  if (filesystemError) {
    return FromFilesystemError(filesystemError,
                               "cannot clear component staging");
  }

  if (auto err = ValidateAndCopyPayload(layerPath.CStr(), staging, instance);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = SaveRelease(staging / cInstanceFile, candidate);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = SealPayload(staging); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  std::filesystem::rename(staging, target, filesystemError);
  if (filesystemError) {
    return FromFilesystemError(filesystemError,
                               "cannot commit prepared component slot");
  }
  if (auto err = SyncDirectory(target.parent_path()); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = mProfile->OfflineSelfTest(target); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::ValidateManifest(
    const oci::ImageManifest &manifest) const {
  if (manifest.mSchemaVersion != oci::cSchemaVersion ||
      manifest.mLayers.Size() != 1 || manifest.mLayers[0].mSize == 0 ||
      manifest.mLayers[0].mSize > mConfig.mMaxPayloadBytes ||
      manifest.mLayers[0].mMediaType != imagemanager::cProviderLayerMediaType) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "invalid provider OCI manifest"));
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::ValidateAndCopyPayload(
    const std::filesystem::path &source,
    const std::filesystem::path &destination,
    const InstanceInfo &instance) const {
  std::error_code reservedError;
  const auto reservedStatus =
      std::filesystem::symlink_status(source / cInstanceFile, reservedError);
  if (reservedError && reservedError != std::errc::no_such_file_or_directory) {
    return FromFilesystemError(reservedError,
                               "cannot inspect reserved component metadata");
  }
  if (std::filesystem::exists(reservedStatus) ||
      std::filesystem::is_symlink(reservedStatus)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument,
              "provider payload contains bootstrap-owned metadata"));
  }

  uint64_t payloadBytes = 0;
  if (auto err = ValidatePayloadTree(source, instance, payloadBytes);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  std::error_code error;
  const auto space = std::filesystem::space(mConfig.mWorkingDir, error);
  if (error) {
    return FromFilesystemError(error, "cannot inspect component storage");
  }
  if (payloadBytes > mConfig.mMaxPayloadBytes ||
      space.available < payloadBytes + mConfig.mMinimumFreeBytes) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eNoMemory, "insufficient component storage"));
  }

  std::filesystem::create_directory(destination, error);
  if (error) {
    return FromFilesystemError(error, "cannot create component staging");
  }

  try {
    for (const auto &entry :
         std::filesystem::recursive_directory_iterator(source)) {
      const auto relative = entry.path().lexically_relative(source);
      const auto target = destination / relative;
      if (entry.is_directory()) {
        std::filesystem::create_directory(target);
        std::filesystem::permissions(target, entry.status().permissions(),
                                     std::filesystem::perm_options::replace);
      } else {
        std::filesystem::copy_file(entry.path(), target,
                                   std::filesystem::copy_options::none);
        std::filesystem::permissions(target, entry.status().permissions(),
                                     std::filesystem::perm_options::replace);
      }
    }
  } catch (const std::exception &exception) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(exception));
  }

  uint64_t copiedBytes = 0;
  return ValidatePayloadTree(destination, instance, copiedBytes);
}

Error SystemdSlotComponentRuntime::ValidatePayloadTree(
    const std::filesystem::path &root, const InstanceInfo &instance,
    uint64_t &payloadBytes) const {
  std::error_code error;
  const auto rootStatus = std::filesystem::symlink_status(root, error);
  if (error || std::filesystem::is_symlink(rootStatus) ||
      !std::filesystem::is_directory(rootStatus) || !root.is_absolute()) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe provider payload root"));
  }

  payloadBytes = 0;
  size_t entries = 0;
  try {
    for (const auto &entry :
         std::filesystem::recursive_directory_iterator(root)) {
      if (++entries > cMaxPayloadEntries) {
        return AOS_ERROR_WRAP(Error(ErrorEnum::eNoMemory,
                                    "provider payload has too many entries"));
      }
      const auto status = entry.symlink_status();
      const auto relative = entry.path().lexically_relative(root);
      const auto relativeString = relative.generic_string();
      if (relative.empty() || relative.is_absolute() ||
          relative.lexically_normal() != relative ||
          relativeString.size() > cMaxRelativePathLength ||
          ContainsControlCharacter(relativeString)) {
        return AOS_ERROR_WRAP(
            Error(ErrorEnum::eInvalidArgument, "unsafe provider payload path"));
      }
      for (const auto &part : relative) {
        if (part == "..") {
          return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                      "escaping provider payload path"));
        }
      }
      if (std::filesystem::is_symlink(status) ||
          (!std::filesystem::is_directory(status) &&
           !std::filesystem::is_regular_file(status))) {
        return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                    "unsupported provider payload file type"));
      }
      const auto permissions = status.permissions();
      if ((permissions &
           (std::filesystem::perms::set_uid | std::filesystem::perms::set_gid |
            std::filesystem::perms::group_write |
            std::filesystem::perms::others_write)) !=
          std::filesystem::perms::none) {
        return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                    "unsafe provider payload permissions"));
      }
      if (std::filesystem::is_regular_file(status)) {
        const bool executable =
            (permissions & (std::filesystem::perms::owner_exec |
                            std::filesystem::perms::group_exec |
                            std::filesystem::perms::others_exec)) !=
            std::filesystem::perms::none;
        if (executable && relativeString != cProviderExecutable) {
          return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                      "unexpected executable in payload"));
        }
        const auto size = entry.file_size();
        if (size > mConfig.mMaxPayloadBytes ||
            payloadBytes > mConfig.mMaxPayloadBytes - size) {
          return AOS_ERROR_WRAP(
              Error(ErrorEnum::eNoMemory, "provider payload is too large"));
        }
        payloadBytes += size;
      }
    }
  } catch (const std::exception &exception) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(exception));
  }

  if (auto err = ValidatePayloadMetadata(root, instance); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::ValidatePayloadMetadata(
    const std::filesystem::path &root, const InstanceInfo &instance) const {
  const auto metadataPath = root / cComponentMetadata;
  std::ifstream metadata(metadataPath);
  if (!metadata.is_open()) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eNotFound, "provider component metadata is missing"));
  }

  try {
    auto parsed = common::utils::ParseJson(metadata);
    if (!parsed.mError.IsNone()) {
      return AOS_ERROR_WRAP(parsed.mError);
    }
    const auto object =
        common::utils::CaseInsensitiveObjectWrapper(parsed.mValue);
    const auto schema = object.GetValue<uint32_t>("schemaVersion");
    const auto component = object.GetValue<std::string>("component");
    const auto version = object.GetValue<std::string>("version");
    const auto architecture = object.GetValue<std::string>("architecture");
    const auto os = object.GetValue<std::string>("os");
    const auto runtimeInterface = object.GetValue<uint32_t>("runtimeInterface");
    const auto entrypoint = object.GetValue<std::string>("entrypoint");
    const auto configuration = object.GetValue<std::string>("configuration");

    std::array<uint64_t, 3> parsedVersion{};
    if (auto err = ParseSemVer(version, parsedVersion); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    if (schema != 1 || component != cComponentName ||
        version != instance.mVersion.CStr() ||
        architecture != mRuntimeInfo.mArchInfo.mArchitecture.CStr() ||
        os != cComponentOS || runtimeInterface != cRuntimeInterface ||
        entrypoint != cProviderExecutable ||
        configuration != cProviderConfiguration) {
      return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                  "incompatible provider component metadata"));
    }
  } catch (const std::exception &exception) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(exception));
  }

  const auto executable = root / cProviderExecutable;
  const auto configuration = root / cProviderConfiguration;
  struct stat executableStatus {};
  struct stat configurationStatus {};
  if (lstat(executable.c_str(), &executableStatus) != 0 ||
      !S_ISREG(executableStatus.st_mode) ||
      (executableStatus.st_mode & S_IXUSR) == 0 ||
      lstat(configuration.c_str(), &configurationStatus) != 0 ||
      !S_ISREG(configurationStatus.st_mode)) {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                "provider payload files are invalid"));
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Activate(
    const ComponentRelease &candidate,
    const std::optional<ComponentRelease> &previous) {
  auto transaction = std::make_unique<ComponentTransaction>();
  transaction->mCandidate = candidate;
  transaction->mPrevious = previous;
  transaction->mPhase = ComponentTransactionPhase::ePrepared;

  if (auto err = mProfile->MarkUnavailable(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  transaction->mPhase = ComponentTransactionPhase::eUnavailable;
  if (auto err = SaveTransaction(*transaction); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  if (auto err = mProfile->StopProvider(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  transaction->mPhase = ComponentTransactionPhase::ePreviousStopped;
  if (auto err = SaveTransaction(*transaction); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  if (auto err = SwitchActive(candidate.mSlot); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  transaction->mPhase = ComponentTransactionPhase::eSwitched;
  if (auto err = SaveTransaction(*transaction); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  if (auto err = mProfile->StartProvider(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  transaction->mPhase = ComponentTransactionPhase::eCandidateStarted;
  if (auto err = SaveTransaction(*transaction); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (auto err = mProfile->CheckHealth(); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  if (auto err = SaveRelease(StatePath(cInstalledFile), candidate);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  mInstalled = candidate;
  if (auto err = RemoveStateFile(StatePath(cTransactionFile)); !err.IsNone()) {
    LOG_WRN() << "Committed provider update retains a stale transaction"
              << Log::Field(err);
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::Rollback(
    const ComponentTransaction &transaction, const Error &candidateError) {
  Error rollbackError;
  if (auto err = mProfile->MarkUnavailable(); !err.IsNone()) {
    rollbackError = AOS_ERROR_WRAP(err);
  }
  if (auto err = mProfile->StopProvider();
      !err.IsNone() && rollbackError.IsNone()) {
    rollbackError = AOS_ERROR_WRAP(err);
  }

  if (transaction.mPrevious.has_value()) {
    if (auto err = ValidateReleaseSlot(*transaction.mPrevious); !err.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    } else if (auto err = SwitchActive(transaction.mPrevious->mSlot);
               !err.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    } else if (auto err = mProfile->StartProvider(); !err.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    } else if (auto err = mProfile->CheckHealth(); !err.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    } else if (auto err = SaveRelease(StatePath(cInstalledFile),
                                      *transaction.mPrevious);
               !err.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    } else {
      mInstalled = *transaction.mPrevious;
    }
  } else {
    if (auto err = RemoveActive(); !err.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    }
    if (auto err = RemoveStateFile(StatePath(cInstalledFile));
        !err.IsNone() && rollbackError.IsNone()) {
      rollbackError = AOS_ERROR_WRAP(err);
    }
    mInstalled.reset();
  }

  if (!rollbackError.IsNone()) {
    RemoveActive();
    RemoveStateFile(StatePath(cInstalledFile));
    mInstalled.reset();
    SaveFailure(transaction, rollbackError);
    return AOS_ERROR_WRAP(rollbackError);
  }

  SaveFailure(transaction, candidateError);
  if (auto err = RemoveStateFile(StatePath(cTransactionFile)); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }

  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::SaveRelease(
    const std::filesystem::path &path, const ComponentRelease &release) const {
  auto object =
      Poco::makeShared<Poco::JSON::Object>(Poco::JSON_PRESERVE_KEY_ORDER);
  object->set("schemaVersion", 1);
  object->set("slot", release.mSlot);
  StoreInstance(*object, "", release.mInstance);
  return AtomicWrite(path, Stringify(object), 0600);
}

Error SystemdSlotComponentRuntime::LoadRelease(
    const std::filesystem::path &path, ComponentRelease &release) const {
  std::error_code filesystemError;
  const auto status = std::filesystem::symlink_status(path, filesystemError);
  if (filesystemError == std::errc::no_such_file_or_directory ||
      (!std::filesystem::exists(status) &&
       !std::filesystem::is_symlink(status))) {
    return ErrorEnum::eNotFound;
  }
  if (filesystemError) {
    return FromFilesystemError(filesystemError, "cannot inspect release state");
  }
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe release state file"));
  }

  std::ifstream stream(path);
  if (!stream.is_open()) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eFailed, "cannot open release state"));
  }
  try {
    auto parsed = common::utils::ParseJson(stream);
    if (!parsed.mError.IsNone()) {
      return AOS_ERROR_WRAP(parsed.mError);
    }
    const auto object =
        common::utils::CaseInsensitiveObjectWrapper(parsed.mValue);
    if (object.GetValue<uint32_t>("schemaVersion") != 1) {
      return AOS_ERROR_WRAP(
          Error(ErrorEnum::eInvalidArgument, "invalid release state schema"));
    }
    release.mSlot = object.GetValue<std::string>("slot");
    if (auto err = LoadInstance(object, "", release.mInstance); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
  } catch (const std::exception &error) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(error));
  }

  return ValidateSlotName(release.mSlot);
}

Error SystemdSlotComponentRuntime::SaveTransaction(
    const ComponentTransaction &transaction) const {
  auto object =
      Poco::makeShared<Poco::JSON::Object>(Poco::JSON_PRESERVE_KEY_ORDER);
  object->set("schemaVersion", 1);
  object->set("phase", PhaseToString(transaction.mPhase));
  object->set("candidateSlot", transaction.mCandidate.mSlot);
  StoreInstance(*object, "candidate", transaction.mCandidate.mInstance);
  object->set("hasPrevious", transaction.mPrevious.has_value());
  if (transaction.mPrevious.has_value()) {
    object->set("previousSlot", transaction.mPrevious->mSlot);
    StoreInstance(*object, "previous", transaction.mPrevious->mInstance);
  }

  return AtomicWrite(StatePath(cTransactionFile), Stringify(object), 0600);
}

Error SystemdSlotComponentRuntime::LoadTransaction(
    ComponentTransaction &transaction) const {
  const auto path = StatePath(cTransactionFile);
  std::error_code filesystemError;
  const auto status = std::filesystem::symlink_status(path, filesystemError);
  if (filesystemError == std::errc::no_such_file_or_directory ||
      (!std::filesystem::exists(status) &&
       !std::filesystem::is_symlink(status))) {
    return ErrorEnum::eNotFound;
  }
  if (filesystemError) {
    return FromFilesystemError(filesystemError,
                               "cannot inspect component transaction");
  }
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe transaction state file"));
  }

  std::ifstream stream(path);
  if (!stream.is_open()) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eFailed, "cannot open component transaction"));
  }
  try {
    auto parsed = common::utils::ParseJson(stream);
    if (!parsed.mError.IsNone()) {
      return AOS_ERROR_WRAP(parsed.mError);
    }
    const auto object =
        common::utils::CaseInsensitiveObjectWrapper(parsed.mValue);
    if (object.GetValue<uint32_t>("schemaVersion") != 1) {
      return AOS_ERROR_WRAP(
          Error(ErrorEnum::eInvalidArgument, "invalid transaction schema"));
    }
    if (auto err = StringToPhase(object.GetValue<std::string>("phase"),
                                 transaction.mPhase);
        !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    transaction.mCandidate.mSlot =
        object.GetValue<std::string>("candidateSlot");
    if (auto err =
            LoadInstance(object, "candidate", transaction.mCandidate.mInstance);
        !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    if (object.GetValue<bool>("hasPrevious")) {
      transaction.mPrevious.emplace();
      transaction.mPrevious->mSlot =
          object.GetValue<std::string>("previousSlot");
      if (auto err = LoadInstance(object, "previous",
                                  transaction.mPrevious->mInstance);
          !err.IsNone()) {
        return AOS_ERROR_WRAP(err);
      }
    } else {
      transaction.mPrevious.reset();
    }
  } catch (const std::exception &error) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(error));
  }

  if (auto err = ValidateSlotName(transaction.mCandidate.mSlot);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (transaction.mPrevious.has_value()) {
    return ValidateSlotName(transaction.mPrevious->mSlot);
  }
  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::SaveFailure(
    const ComponentTransaction &transaction, const Error &error) const {
  auto object =
      Poco::makeShared<Poco::JSON::Object>(Poco::JSON_PRESERVE_KEY_ORDER);
  object->set("schemaVersion", 1);
  object->set("candidateVersion",
              transaction.mCandidate.mInstance.mVersion.CStr());
  object->set("candidateManifestDigest",
              transaction.mCandidate.mInstance.mManifestDigest.CStr());
  object->set("phase", PhaseToString(transaction.mPhase));
  object->set("message", error.Message());
  return AtomicWrite(StatePath(cFailureFile), Stringify(object), 0600);
}

Error SystemdSlotComponentRuntime::RemoveStateFile(
    const std::filesystem::path &path) const {
  std::error_code error;
  const auto status = std::filesystem::symlink_status(path, error);
  if (error == std::errc::no_such_file_or_directory ||
      (!std::filesystem::exists(status) &&
       !std::filesystem::is_symlink(status))) {
    return ErrorEnum::eNone;
  }
  if (error) {
    return FromFilesystemError(error, "cannot inspect component state file");
  }
  if (std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "unsafe component state file"));
  }
  const auto removed = std::filesystem::remove(path, error);
  if (error) {
    return FromFilesystemError(error, "cannot remove component state file");
  }
  if (!removed) {
    return ErrorEnum::eNone;
  }
  return SyncDirectory(path.parent_path());
}

Error SystemdSlotComponentRuntime::SwitchActive(const std::string &slot) const {
  if (auto err = ValidateSlotName(slot); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  const auto active = mConfig.mWorkingDir / "active";
  const auto temporary = mConfig.mWorkingDir / "active.tmp";
  std::error_code error;
  const auto activeStatus = std::filesystem::symlink_status(active, error);
  if (error && error != std::errc::no_such_file_or_directory) {
    return FromFilesystemError(error, "cannot inspect active component link");
  }
  if (std::filesystem::exists(activeStatus) &&
      !std::filesystem::is_symlink(activeStatus)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "active component path is unsafe"));
  }
  std::filesystem::remove(temporary, error);
  error.clear();
  std::filesystem::create_symlink(std::filesystem::path("slots") / slot,
                                  temporary, error);
  if (error) {
    return FromFilesystemError(error, "cannot create active component link");
  }
  std::filesystem::rename(temporary, active, error);
  if (error) {
    std::filesystem::remove(temporary);
    return FromFilesystemError(error, "cannot switch active component link");
  }
  return SyncDirectory(mConfig.mWorkingDir);
}

Error SystemdSlotComponentRuntime::RemoveActive() const {
  const auto active = mConfig.mWorkingDir / "active";
  std::error_code error;
  const auto status = std::filesystem::symlink_status(active, error);
  if (error == std::errc::no_such_file_or_directory ||
      (!std::filesystem::exists(status) &&
       !std::filesystem::is_symlink(status))) {
    return ErrorEnum::eNone;
  }
  if (error) {
    return FromFilesystemError(error, "cannot inspect active component link");
  }
  if (!std::filesystem::is_symlink(status)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "active component path is unsafe"));
  }
  if (!std::filesystem::remove(active, error) || error) {
    return FromFilesystemError(error, "cannot remove active component link");
  }
  return SyncDirectory(mConfig.mWorkingDir);
}

Error SystemdSlotComponentRuntime::ReadActive(std::string &slot) const {
  const auto active = mConfig.mWorkingDir / "active";
  std::error_code error;
  const auto status = std::filesystem::symlink_status(active, error);
  if (error == std::errc::no_such_file_or_directory ||
      (!std::filesystem::exists(status) &&
       !std::filesystem::is_symlink(status))) {
    return ErrorEnum::eNotFound;
  }
  if (error) {
    return FromFilesystemError(error, "cannot inspect active component link");
  }
  if (!std::filesystem::is_symlink(status)) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "active component path is unsafe"));
  }
  const auto target = std::filesystem::read_symlink(active, error);
  if (error || target.parent_path() != "slots") {
    return AOS_ERROR_WRAP(Error(ErrorEnum::eInvalidArgument,
                                "active component target is invalid"));
  }
  slot = target.filename().string();
  return ValidateSlotName(slot);
}

Error SystemdSlotComponentRuntime::ValidateSlotName(
    const std::string &slot) const {
  if (slot != "a" && slot != "b") {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "invalid component slot"));
  }
  return ErrorEnum::eNone;
}

Error SystemdSlotComponentRuntime::ValidateReleaseSlot(
    const ComponentRelease &release) const {
  if (auto err = ValidateSlotName(release.mSlot); !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  auto stored = std::make_unique<ComponentRelease>();
  if (auto err = LoadRelease(SlotPath(release.mSlot) / cInstanceFile, *stored);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (stored->mSlot != release.mSlot ||
      stored->mInstance.mManifestDigest != release.mInstance.mManifestDigest ||
      stored->mInstance.mVersion != release.mInstance.mVersion) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eWrongState, "component slot metadata mismatch"));
  }
  uint64_t payloadBytes = 0;
  return ValidatePayloadTree(SlotPath(release.mSlot), release.mInstance,
                             payloadBytes);
}

Error SystemdSlotComponentRuntime::CheckVersionPolicy(
    const InstanceInfo &candidate) const {
  std::array<uint64_t, 3> candidateVersion{};
  if (auto err = ParseSemVer(candidate.mVersion.CStr(), candidateVersion);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (!mInstalled.has_value()) {
    return ErrorEnum::eNone;
  }

  std::array<uint64_t, 3> installedVersion{};
  if (auto err =
          ParseSemVer(mInstalled->mInstance.mVersion.CStr(), installedVersion);
      !err.IsNone()) {
    return AOS_ERROR_WRAP(err);
  }
  if (candidateVersion < installedVersion) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument, "component downgrade is rejected"));
  }
  if (candidateVersion == installedVersion &&
      candidate.mManifestDigest != mInstalled->mInstance.mManifestDigest) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eInvalidArgument,
              "component version cannot identify two different manifests"));
  }

  return ErrorEnum::eNone;
}

void SystemdSlotComponentRuntime::FillStatus(const ComponentRelease &release,
                                             InstanceStateEnum state,
                                             const Error &error,
                                             InstanceStatus &status) const {
  FillStatus(release.mInstance, state, error, status);
}

void SystemdSlotComponentRuntime::FillStatus(const InstanceInfo &instance,
                                             InstanceStateEnum state,
                                             const Error &error,
                                             InstanceStatus &status) const {
  FillStatus(static_cast<const InstanceIdent &>(instance), state, error,
             status);
  status.mManifestDigest = instance.mManifestDigest;
  status.mVersion = instance.mVersion;
  status.mPreinstalled = instance.mPreinstalled;
}

void SystemdSlotComponentRuntime::FillStatus(const InstanceIdent &instance,
                                             InstanceStateEnum state,
                                             const Error &error,
                                             InstanceStatus &status) const {
  static_cast<InstanceIdent &>(status) = instance;
  status.mNodeID = mNodeID;
  status.mRuntimeID = mRuntimeInfo.mRuntimeID;
  status.mType = UpdateItemTypeEnum::eComponent;
  status.mState = state;
  status.mError = error;
}

void SystemdSlotComponentRuntime::Notify(const InstanceStatus &status) const {
  if (auto err = mStatusReceiver->OnInstancesStatusesReceived(
          Array<InstanceStatus>{&status, 1});
      !err.IsNone()) {
    LOG_WRN() << "Cannot publish component status" << Log::Field(err);
  }
}

std::filesystem::path
SystemdSlotComponentRuntime::StatePath(const std::string &name) const {
  return mConfig.mWorkingDir / "state" / name;
}

std::filesystem::path
SystemdSlotComponentRuntime::SlotPath(const std::string &slot) const {
  return mConfig.mWorkingDir / "slots" / slot;
}

} // namespace aos::sm::launcher
