/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_PROVIDERARCHIVE_HPP_
#define AOS_VEHICLE_PLATFORM_SYSTEMD_SLOT_COMPONENT_PROVIDERARCHIVE_HPP_

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <set>
#include <string>
#include <system_error>

#include <core/common/tools/error.hpp>

namespace aos::sm::imagemanager {

inline constexpr auto cProviderLayerMediaType =
    "application/vnd.aos.vehicle-data-provider.layer.v1.tar";
inline constexpr uint64_t cProviderArchiveMaxPayloadBytes =
    512ULL * 1024ULL * 1024ULL;
inline constexpr size_t cProviderArchiveMaxEntries = 4096;
inline constexpr size_t cProviderArchiveMaxPathLength = 240;

namespace detail {

inline bool IsZeroBlock(const std::array<unsigned char, 512> &block) {
  for (const auto value : block) {
    if (value != 0) {
      return false;
    }
  }
  return true;
}

inline bool ContainsControlCharacter(const std::string &value) {
  for (const unsigned char character : value) {
    if (character < 0x20 || character == 0x7f) {
      return true;
    }
  }
  return false;
}

inline Error ReadString(const std::array<unsigned char, 512> &block,
                        size_t offset, size_t length, std::string &value) {
  value.clear();
  for (size_t index = 0; index < length; ++index) {
    const auto character = block[offset + index];
    if (character == 0) {
      break;
    }
    value.push_back(static_cast<char>(character));
  }

  if (ContainsControlCharacter(value)) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive field contains a control character");
  }

  return ErrorEnum::eNone;
}

inline Error ParseOctal(const std::array<unsigned char, 512> &block,
                        size_t offset, size_t length, uint64_t &value) {
  value = 0;
  size_t index = 0;
  while (index < length &&
         (block[offset + index] == ' ' || block[offset + index] == 0)) {
    ++index;
  }

  bool foundDigit = false;
  for (; index < length; ++index) {
    const auto character = block[offset + index];
    if (character == 0 || character == ' ') {
      for (; index < length; ++index) {
        if (block[offset + index] != 0 && block[offset + index] != ' ') {
          return Error(ErrorEnum::eInvalidArgument,
                       "provider archive has an invalid numeric field");
        }
      }
      break;
    }
    if (character < '0' || character > '7' || value > (UINT64_MAX >> 3)) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive has an invalid numeric field");
    }
    foundDigit = true;
    value = (value << 3) + static_cast<uint64_t>(character - '0');
  }

  if (!foundDigit) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive has an empty numeric field");
  }
  return ErrorEnum::eNone;
}

inline Error ValidateChecksum(const std::array<unsigned char, 512> &block) {
  uint64_t expected = 0;
  if (auto err = ParseOctal(block, 148, 8, expected); !err.IsNone()) {
    return err;
  }

  uint64_t actual = 0;
  for (size_t index = 0; index < block.size(); ++index) {
    actual += index >= 148 && index < 156 ? ' ' : block[index];
  }
  if (actual != expected) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive header checksum mismatch");
  }
  return ErrorEnum::eNone;
}

inline Error ValidatePath(const std::string &name, char type,
                          std::string &canonical) {
  canonical = name;
  if (type == '5' && !canonical.empty() && canonical.back() == '/') {
    canonical.pop_back();
  }
  if (canonical.empty() || canonical.size() > cProviderArchiveMaxPathLength ||
      ContainsControlCharacter(canonical)) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive path is invalid");
  }

  const std::filesystem::path path(canonical);
  if (path.is_absolute() || path.lexically_normal() != path) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive path is not normalized and relative");
  }
  for (const auto &part : path) {
    if (part.empty() || part == "." || part == "..") {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive path escapes its root");
    }
  }
  const auto filename = path.filename().string();
  if (filename.rfind(".wh.", 0) == 0 || canonical == ".aos-instance.json") {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive path is bootstrap-reserved");
  }
  canonical = path.generic_string();
  return ErrorEnum::eNone;
}

} // namespace detail

/** Validates the restricted, uncompressed USTAR provider layer before tar. */
inline Error ValidateProviderArchive(const std::filesystem::path &archivePath) {
  std::error_code filesystemError;
  const auto status =
      std::filesystem::symlink_status(archivePath, filesystemError);
  if (filesystemError || std::filesystem::is_symlink(status) ||
      !std::filesystem::is_regular_file(status)) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive is not a regular file");
  }

  const auto archiveSize =
      std::filesystem::file_size(archivePath, filesystemError);
  constexpr auto cMaximumHeaderBytes =
      (cProviderArchiveMaxEntries + 2ULL) * 512ULL;
  if (filesystemError || archiveSize < 1024 || archiveSize % 512 != 0 ||
      archiveSize > cProviderArchiveMaxPayloadBytes + cMaximumHeaderBytes) {
    return Error(ErrorEnum::eInvalidArgument,
                 "provider archive size is outside its fixed bounds");
  }

  std::ifstream stream(archivePath, std::ios::binary);
  if (!stream.is_open()) {
    return Error(ErrorEnum::eFailed, "cannot open provider archive");
  }

  std::set<std::string> paths;
  uint64_t offset = 0;
  uint64_t payloadBytes = 0;
  size_t entries = 0;
  std::array<unsigned char, 512> block{};
  while (offset + block.size() <= archiveSize) {
    stream.read(reinterpret_cast<char *>(block.data()), block.size());
    if (stream.gcount() != static_cast<std::streamsize>(block.size())) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive is truncated");
    }
    offset += block.size();

    if (detail::IsZeroBlock(block)) {
      std::array<unsigned char, 512> second{};
      stream.read(reinterpret_cast<char *>(second.data()), second.size());
      if (stream.gcount() != static_cast<std::streamsize>(second.size()) ||
          !detail::IsZeroBlock(second)) {
        return Error(ErrorEnum::eInvalidArgument,
                     "provider archive end marker is invalid");
      }
      offset += second.size();
      while (offset < archiveSize) {
        stream.read(reinterpret_cast<char *>(block.data()), block.size());
        const auto count = stream.gcount();
        if (count <= 0) {
          return Error(ErrorEnum::eInvalidArgument,
                       "provider archive padding is truncated");
        }
        for (std::streamsize index = 0; index < count; ++index) {
          if (block[static_cast<size_t>(index)] != 0) {
            return Error(ErrorEnum::eInvalidArgument,
                         "provider archive has data after its end marker");
          }
        }
        offset += static_cast<uint64_t>(count);
      }
      return entries == 0 ? Error(ErrorEnum::eInvalidArgument,
                                  "provider archive is empty")
                          : ErrorEnum::eNone;
    }

    if (++entries > cProviderArchiveMaxEntries) {
      return Error(ErrorEnum::eNoMemory,
                   "provider archive has too many entries");
    }
    if (auto err = detail::ValidateChecksum(block); !err.IsNone()) {
      return err;
    }
    if (std::string(reinterpret_cast<const char *>(block.data() + 257), 5) !=
        "ustar") {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive is not restricted USTAR");
    }

    const char type = static_cast<char>(block[156]);
    if (type != '\0' && type != '0' && type != '5') {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive contains a link or special file");
    }

    std::string name;
    std::string prefix;
    std::string linkName;
    if (auto err = detail::ReadString(block, 0, 100, name); !err.IsNone()) {
      return err;
    }
    if (auto err = detail::ReadString(block, 345, 155, prefix); !err.IsNone()) {
      return err;
    }
    if (auto err = detail::ReadString(block, 157, 100, linkName);
        !err.IsNone()) {
      return err;
    }
    if (!prefix.empty()) {
      name = prefix + "/" + name;
    }
    if (!linkName.empty()) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive link target is forbidden");
    }

    std::string canonical;
    if (auto err = detail::ValidatePath(name, type, canonical); !err.IsNone()) {
      return err;
    }
    if (!paths.insert(canonical).second) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive contains a duplicate path");
    }

    uint64_t mode = 0;
    uint64_t size = 0;
    if (auto err = detail::ParseOctal(block, 100, 8, mode); !err.IsNone()) {
      return err;
    }
    if (auto err = detail::ParseOctal(block, 124, 12, size); !err.IsNone()) {
      return err;
    }
    if ((mode & (07000U | 0022U)) != 0 ||
        (type != '5' && (mode & 0111U) != 0 &&
         canonical != "bin/vehicle-data-provider")) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive permissions are unsafe");
    }
    if (type == '5' && size != 0) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive directory has file data");
    }
    if (size > cProviderArchiveMaxPayloadBytes - payloadBytes) {
      return Error(ErrorEnum::eNoMemory,
                   "provider archive payload is too large");
    }
    payloadBytes += size;

    const uint64_t paddedSize = (size + 511ULL) & ~511ULL;
    if (paddedSize > archiveSize - offset) {
      return Error(ErrorEnum::eInvalidArgument,
                   "provider archive entry is truncated");
    }
    stream.seekg(static_cast<std::streamoff>(paddedSize), std::ios::cur);
    if (!stream) {
      return Error(ErrorEnum::eInvalidArgument,
                   "cannot advance through provider archive");
    }
    offset += paddedSize;
  }

  return Error(ErrorEnum::eInvalidArgument,
               "provider archive has no end marker");
}

} // namespace aos::sm::imagemanager

#endif
