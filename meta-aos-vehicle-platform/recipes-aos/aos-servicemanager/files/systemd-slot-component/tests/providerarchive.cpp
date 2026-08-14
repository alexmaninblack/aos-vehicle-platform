/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include <array>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <unistd.h>
#include <vector>

#include <gtest/gtest.h>

#include <sm/imagemanager/imagehandler.hpp>

#include "providerarchive.hpp"

namespace aos::sm::imagemanager {

namespace {

struct TarEntry {
  std::string mName;
  char mType{'0'};
  uint32_t mMode{0644};
  std::string mData;
  std::string mLinkName;
};

void WriteOctal(std::array<unsigned char, 512> &header, size_t offset,
                size_t length, uint64_t value) {
  std::ostringstream stream;
  stream << std::oct << std::setfill('0') << std::setw(length - 1) << value;
  const auto text = stream.str();
  ASSERT_LT(text.size(), length);
  std::memcpy(header.data() + offset, text.data(), text.size());
}

void WriteArchive(const std::filesystem::path &path,
                  const std::vector<TarEntry> &entries) {
  std::ofstream stream(path, std::ios::binary);
  ASSERT_TRUE(stream.is_open());
  for (const auto &entry : entries) {
    ASSERT_LE(entry.mName.size(), 100U);
    ASSERT_LE(entry.mLinkName.size(), 100U);
    std::array<unsigned char, 512> header{};
    std::memcpy(header.data(), entry.mName.data(), entry.mName.size());
    WriteOctal(header, 100, 8, entry.mMode);
    WriteOctal(header, 108, 8, 0);
    WriteOctal(header, 116, 8, 0);
    WriteOctal(header, 124, 12, entry.mData.size());
    WriteOctal(header, 136, 12, 0);
    std::memset(header.data() + 148, ' ', 8);
    header[156] = static_cast<unsigned char>(entry.mType);
    std::memcpy(header.data() + 157, entry.mLinkName.data(),
                entry.mLinkName.size());
    std::memcpy(header.data() + 257, "ustar", 5);
    header[262] = 0;
    header[263] = '0';
    header[264] = '0';

    uint64_t checksum = 0;
    for (const auto value : header) {
      checksum += value;
    }
    std::ostringstream checksumStream;
    checksumStream << std::oct << std::setfill('0') << std::setw(6) << checksum;
    const auto checksumText = checksumStream.str();
    ASSERT_EQ(checksumText.size(), 6U);
    std::memcpy(header.data() + 148, checksumText.data(), checksumText.size());
    header[154] = 0;
    header[155] = ' ';

    stream.write(reinterpret_cast<const char *>(header.data()), header.size());
    stream.write(entry.mData.data(), entry.mData.size());
    const std::array<char, 512> padding{};
    const auto paddingSize = (512 - (entry.mData.size() % 512)) % 512;
    stream.write(padding.data(), static_cast<std::streamsize>(paddingSize));
  }
  const std::array<char, 1024> end{};
  stream.write(end.data(), end.size());
  stream.close();
}

class ProviderArchiveTest : public testing::Test {
protected:
  void SetUp() override {
    mDirectory = std::filesystem::temp_directory_path() /
                 ("r61-provider-archive-test-" + std::to_string(getpid()));
    std::filesystem::remove_all(mDirectory);
    std::filesystem::create_directories(mDirectory);
    mArchive = mDirectory / "provider.tar";
  }

  void TearDown() override { std::filesystem::remove_all(mDirectory); }

  std::filesystem::path mDirectory;
  std::filesystem::path mArchive;
};

TEST_F(ProviderArchiveTest, AcceptsRestrictedUstarPayload) {
  WriteArchive(
      mArchive,
      {{"bin/", '5', 0755, {}, {}},
       {"config/", '5', 0755, {}, {}},
       {"component.json", '0', 0644, "{}\n", {}},
       {"bin/vehicle-data-provider", '0', 0755, "#!/bin/sh\nexit 0\n", {}},
       {"config/provider.json", '0', 0644, "{}\n", {}}});

  EXPECT_TRUE(ValidateProviderArchive(mArchive).IsNone());
}

TEST_F(ProviderArchiveTest, RejectsEscapingPathBeforeExtraction) {
  WriteArchive(mArchive, {{"../escape", '0', 0644, "unsafe", {}}});
  EXPECT_TRUE(
      ValidateProviderArchive(mArchive).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(ProviderArchiveTest, RejectsSymbolicLinkBeforeExtraction) {
  WriteArchive(mArchive, {{"escape", '2', 0777, {}, "/etc/passwd"}});
  EXPECT_TRUE(
      ValidateProviderArchive(mArchive).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(ProviderArchiveTest, RejectsDuplicatePathBeforeExtraction) {
  WriteArchive(mArchive, {{"config/provider.json", '0', 0644, "{}", {}},
                          {"config/provider.json", '0', 0644, "{}", {}}});
  EXPECT_TRUE(
      ValidateProviderArchive(mArchive).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(ProviderArchiveTest, RejectsUnsafeModeBeforeExtraction) {
  WriteArchive(mArchive, {{"config/provider.json", '0', 0664, "{}", {}}});
  EXPECT_TRUE(
      ValidateProviderArchive(mArchive).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(ProviderArchiveTest, RejectsOciWhiteoutBeforeConversion) {
  WriteArchive(mArchive, {{"config/.wh.provider.json", '0', 0644, {}, {}}});
  EXPECT_TRUE(
      ValidateProviderArchive(mArchive).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(ProviderArchiveTest, RejectsHeaderChecksumMismatch) {
  WriteArchive(mArchive, {{"config/provider.json", '0', 0644, "{}", {}}});
  std::fstream stream(mArchive,
                      std::ios::binary | std::ios::in | std::ios::out);
  ASSERT_TRUE(stream.is_open());
  stream.put('x');
  stream.close();

  EXPECT_TRUE(
      ValidateProviderArchive(mArchive).Is(ErrorEnum::eInvalidArgument));
}

TEST_F(ProviderArchiveTest, ImageManagerRejectsUnsafeArchiveBeforeExtraction) {
  WriteArchive(mArchive, {{"../escape", '0', 0644, "unsafe", {}}});
  const auto destination = mDirectory / "unpacked";
  ImageHandler handler;
  ASSERT_TRUE(handler.Init().IsNone());

  const auto err = handler.UnpackLayer(mArchive.c_str(), destination.c_str(),
                                       cProviderLayerMediaType);
  EXPECT_TRUE(err.Is(ErrorEnum::eInvalidArgument));
  EXPECT_FALSE(std::filesystem::exists(destination));
  EXPECT_FALSE(std::filesystem::exists(mDirectory / "escape"));
}

TEST_F(ProviderArchiveTest, ImageManagerExtractsValidatedArchive) {
  WriteArchive(
      mArchive,
      {{"bin/", '5', 0755, {}, {}},
       {"bin/vehicle-data-provider", '0', 0755, "#!/bin/sh\nexit 0\n", {}}});
  const auto destination = mDirectory / "unpacked";
  ImageHandler handler;
  ASSERT_TRUE(handler.Init().IsNone());

  const auto err = handler.UnpackLayer(mArchive.c_str(), destination.c_str(),
                                       cProviderLayerMediaType);
  ASSERT_TRUE(err.IsNone());
  EXPECT_TRUE(std::filesystem::is_regular_file(destination /
                                               "bin/vehicle-data-provider"));
}

} // namespace

} // namespace aos::sm::imagemanager
