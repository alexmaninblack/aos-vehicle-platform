/*
 * SPDX-FileCopyrightText: 2026 maninblack
 * SPDX-License-Identifier: Apache-2.0
 */

#include "vissvehiclestate.hpp"

#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <sstream>
#include <string_view>

#include <arpa/inet.h>

#include <Poco/Dynamic/Var.h>
#include <Poco/JSON/Object.h>
#include <Poco/JSON/Parser.h>
#include <Poco/Net/Context.h>
#include <Poco/Net/HTTPRequest.h>
#include <Poco/Net/HTTPResponse.h>
#include <Poco/Net/HTTPSClientSession.h>
#include <Poco/Net/NetSSL.h>
#include <Poco/Net/WebSocket.h>
#include <Poco/Timespan.h>
#include <Poco/URI.h>

#include <common/utils/exception.hpp>

namespace aos::sm::launcher {

namespace {

constexpr size_t cMaximumVissFrameBytes = 64 * 1024;

bool IsNumericAddress(const std::string &host) {
  in_addr ipv4{};
  in6_addr ipv6{};
  return inet_pton(AF_INET, host.c_str(), &ipv4) == 1 ||
         inet_pton(AF_INET6, host.c_str(), &ipv6) == 1;
}

std::string Stringify(const Poco::JSON::Object::Ptr &object) {
  std::ostringstream output;
  object->stringify(output);
  return output.str();
}

Error Exchange(Poco::Net::WebSocket &socket, const std::string &path,
               size_t requestIndex, std::string &value,
               std::string &sourceTimestamp) {
  auto request = Poco::makeShared<Poco::JSON::Object>(
      Poco::JSON_PRESERVE_KEY_ORDER);
  const auto requestID = "platform-update-runtime-" +
                         std::to_string(requestIndex);
  request->set("action", "get");
  request->set("path", path);
  request->set("requestId", requestID);
  const auto requestText = Stringify(request);
  socket.sendFrame(requestText.data(), static_cast<int>(requestText.size()),
                   Poco::Net::WebSocket::FRAME_TEXT);

  std::array<char, cMaximumVissFrameBytes + 1> input{};
  int flags{};
  const auto size = socket.receiveFrame(input.data(), cMaximumVissFrameBytes,
                                        flags);
  if (size <= 0 || static_cast<size_t>(size) > cMaximumVissFrameBytes ||
      (flags & Poco::Net::WebSocket::FRAME_OP_BITMASK) !=
          Poco::Net::WebSocket::FRAME_OP_TEXT) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eFailed, "invalid VISS 3.1 response frame"));
  }

  try {
    Poco::JSON::Parser parser;
    const auto parsed = parser.parse(std::string(input.data(), size));
    const auto response = parsed.extract<Poco::JSON::Object::Ptr>();
    if (response->getValue<std::string>("action") != "get" ||
        response->getValue<std::string>("requestId") != requestID) {
      return AOS_ERROR_WRAP(
          Error(ErrorEnum::eInvalidArgument, "mismatched VISS response"));
    }
    const auto data =
        response->get("data").extract<Poco::JSON::Object::Ptr>();
    if (data->getValue<std::string>("path") != path) {
      return AOS_ERROR_WRAP(
          Error(ErrorEnum::eInvalidArgument, "mismatched VISS path"));
    }
    const auto datapoint =
        data->get("dp").extract<Poco::JSON::Object::Ptr>();
    value = datapoint->get("value").convert<std::string>();
    sourceTimestamp = datapoint->getValue<std::string>("ts");
    if (sourceTimestamp.empty()) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument, "VISS source timestamp is missing"));
    }
  } catch (const std::exception &exception) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(
        exception, ErrorEnum::eInvalidArgument));
  }

  return ErrorEnum::eNone;
}

bool ParseFixedUnsigned(std::string_view value, size_t offset, size_t length,
                        unsigned &result) {
  const auto first = value.data() + offset;
  const auto last = first + length;
  const auto parsed = std::from_chars(first, last, result);
  return parsed.ec == std::errc{} && parsed.ptr == last;
}

bool IsLeapYear(unsigned year) {
  return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
}

unsigned DaysInMonth(unsigned year, unsigned month) {
  constexpr std::array<unsigned, 12> cDays = {
      31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  if (month == 2 && IsLeapYear(year)) {
    return 29;
  }
  return cDays[month - 1];
}

constexpr int64_t DaysFromCivil(int year, unsigned month, unsigned day) {
  year -= month <= 2;
  const auto era = (year >= 0 ? year : year - 399) / 400;
  const auto yearOfEra = static_cast<unsigned>(year - era * 400);
  const auto adjustedMonth = month > 2 ? month - 3 : month + 9;
  const auto dayOfYear =
      (153 * adjustedMonth + 2) / 5 +
      day - 1;
  const auto dayOfEra =
      yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear;
  return static_cast<int64_t>(era) * 146097 + dayOfEra - 719468;
}

Error ParseSourceTimestamp(
    std::string_view value,
    std::chrono::system_clock::time_point &result) {
  const bool hasMilliseconds = value.size() == 24;
  if ((!hasMilliseconds && value.size() != 20) || value[4] != '-' ||
      value[7] != '-' || value[10] != 'T' || value[13] != ':' ||
      value[16] != ':' || value.back() != 'Z' ||
      (hasMilliseconds && value[19] != '.')) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eInvalidArgument, "invalid VISS source timestamp"));
  }

  unsigned year{};
  unsigned month{};
  unsigned day{};
  unsigned hour{};
  unsigned minute{};
  unsigned second{};
  unsigned millisecond{};
  if (!ParseFixedUnsigned(value, 0, 4, year) ||
      !ParseFixedUnsigned(value, 5, 2, month) ||
      !ParseFixedUnsigned(value, 8, 2, day) ||
      !ParseFixedUnsigned(value, 11, 2, hour) ||
      !ParseFixedUnsigned(value, 14, 2, minute) ||
      !ParseFixedUnsigned(value, 17, 2, second) ||
      (hasMilliseconds &&
       !ParseFixedUnsigned(value, 20, 3, millisecond)) ||
      year < 1970 || month == 0 || month > 12 || day == 0 ||
      day > DaysInMonth(year, month) || hour > 23 || minute > 59 ||
      second > 59) {
    return AOS_ERROR_WRAP(Error(
        ErrorEnum::eInvalidArgument, "invalid VISS source timestamp"));
  }

  const auto seconds = DaysFromCivil(static_cast<int>(year), month, day) *
                           24 * 60 * 60 +
                       static_cast<int64_t>(hour) * 60 * 60 +
                       static_cast<int64_t>(minute) * 60 + second;
  result = std::chrono::system_clock::time_point{
      std::chrono::seconds{seconds} + std::chrono::milliseconds{millisecond}};
  return ErrorEnum::eNone;
}

Error BoundReceive(Poco::Net::WebSocket &socket,
                   std::chrono::steady_clock::time_point deadline) {
  const auto now = std::chrono::steady_clock::now();
  if (now >= deadline) {
    return AOS_ERROR_WRAP(
        Error(ErrorEnum::eFailed, "VISS coherent snapshot timed out"));
  }
  const auto remaining =
      std::chrono::duration_cast<std::chrono::microseconds>(deadline - now);
  socket.setReceiveTimeout(Poco::Timespan{
      static_cast<Poco::Timespan::TimeDiff>(remaining.count())});
  return ErrorEnum::eNone;
}

} // namespace

Error PocoViss31MtlsTransport::ReadSnapshot(
    const Viss31MtlsConfig &config,
    const std::array<const char *, 10> &paths, Viss31Snapshot &snapshot,
    std::chrono::milliseconds timeout) {
  mCanceled = false;
  const auto started = std::chrono::steady_clock::now();
  const auto deadline = started + timeout;
  try {
    const Poco::URI endpoint(config.mEndpoint);
    if (endpoint.getScheme() != "wss" || !IsNumericAddress(endpoint.getHost()) ||
        endpoint.getPort() == 0) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument,
          "VISS endpoint must be a fixed numeric wss address"));
    }

    Poco::Net::initializeSSL();
    auto context = new Poco::Net::Context(
        Poco::Net::Context::CLIENT_USE, config.mPrivateKeyCredential.string(),
        config.mCertificateCredential.string(), config.mCACredential.string(),
        Poco::Net::Context::VERIFY_STRICT, 4, false,
        "HIGH:!aNULL:!eNULL:!MD5:!RC4");
    Poco::Net::HTTPSClientSession session(endpoint.getHost(),
                                          endpoint.getPort(), context);
    session.setPeerHostName(config.mServerName);
    session.setTimeout(Poco::Timespan(
        static_cast<Poco::Timespan::TimeDiff>(timeout.count()) * 1000));

    Poco::Net::HTTPRequest request(
        Poco::Net::HTTPRequest::HTTP_GET,
        endpoint.getPath().empty() ? "/" : endpoint.getPathEtc(),
        Poco::Net::HTTPMessage::HTTP_1_1);
    request.set("Sec-WebSocket-Protocol", "VISSv3");
    Poco::Net::HTTPResponse response;
    Poco::Net::WebSocket socket(session, request, response);
    if (response.get("Sec-WebSocket-Protocol", "") != "VISSv3") {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument,
          "Gateway did not negotiate the pinned VISSv3 subprotocol"));
    }

    snapshot.mValues.clear();
    std::string firstFrame;
    std::string sourceTimestamp;
    if (auto err = BoundReceive(socket, deadline); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    if (auto err =
            Exchange(socket, paths[0], 0, firstFrame, sourceTimestamp);
        !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    snapshot.mValues.emplace(paths[0], firstFrame);
    for (size_t index = 1; index < paths.size(); ++index) {
      if (mCanceled) {
        return AOS_ERROR_WRAP(
            Error(ErrorEnum::eWrongState, "VISS read canceled"));
      }
      std::string value;
      std::string currentTimestamp;
      if (auto err = BoundReceive(socket, deadline); !err.IsNone()) {
        return AOS_ERROR_WRAP(err);
      }
      if (auto err = Exchange(socket, paths[index], index, value,
                              currentTimestamp);
          !err.IsNone()) {
        return AOS_ERROR_WRAP(err);
      }
      if (currentTimestamp != sourceTimestamp) {
        return AOS_ERROR_WRAP(Error(
            ErrorEnum::eInvalidArgument,
            "VISS facts crossed a Gateway source timestamp boundary"));
      }
      snapshot.mValues.emplace(paths[index], std::move(value));
    }
    std::string finalFrame;
    std::string finalTimestamp;
    if (auto err = BoundReceive(socket, deadline); !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    if (auto err = Exchange(socket, paths[0], paths.size(), finalFrame,
                            finalTimestamp);
        !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    if (firstFrame != finalFrame || finalTimestamp != sourceTimestamp) {
      return AOS_ERROR_WRAP(Error(
          ErrorEnum::eInvalidArgument,
          "VISS facts crossed a Gateway frame boundary"));
    }

    std::chrono::system_clock::time_point sourceWallClock;
    if (auto err = ParseSourceTimestamp(sourceTimestamp, sourceWallClock);
        !err.IsNone()) {
      return AOS_ERROR_WRAP(err);
    }
    const auto acquiredWallClock = std::chrono::system_clock::now();
    snapshot.mAcquiredAt = std::chrono::steady_clock::now();
    snapshot.mSourceObservedAt =
        snapshot.mAcquiredAt +
        std::chrono::duration_cast<std::chrono::steady_clock::duration>(
            sourceWallClock - acquiredWallClock);
    if (snapshot.mAcquiredAt > deadline) {
      return AOS_ERROR_WRAP(
          Error(ErrorEnum::eFailed, "VISS coherent snapshot timed out"));
    }
    socket.shutdown();
  } catch (const std::exception &exception) {
    return AOS_ERROR_WRAP(common::utils::ToAosError(exception));
  }
  return ErrorEnum::eNone;
}

void PocoViss31MtlsTransport::Cancel() { mCanceled = true; }

} // namespace aos::sm::launcher
