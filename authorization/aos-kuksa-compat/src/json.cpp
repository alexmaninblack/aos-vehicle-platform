// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

#include <array>
#include <cctype>
#include <cstdint>
#include <set>

namespace aos::kac {
namespace {

bool ValidUtf8(std::string_view text) {
  std::size_t index = 0;
  while (index < text.size()) {
    const auto first = static_cast<unsigned char>(text[index]);
    if (first <= 0x7fU) {
      ++index;
      continue;
    }
    std::size_t count = 0;
    std::uint32_t code = 0;
    if ((first & 0xe0U) == 0xc0U) {
      count = 2;
      code = first & 0x1fU;
      if (code == 0) return false;
    } else if ((first & 0xf0U) == 0xe0U) {
      count = 3;
      code = first & 0x0fU;
    } else if ((first & 0xf8U) == 0xf0U) {
      count = 4;
      code = first & 0x07U;
    } else {
      return false;
    }
    if (index + count > text.size()) return false;
    for (std::size_t offset = 1; offset < count; ++offset) {
      const auto next = static_cast<unsigned char>(text[index + offset]);
      if ((next & 0xc0U) != 0x80U) return false;
      code = (code << 6U) | (next & 0x3fU);
    }
    if ((count == 2 && code < 0x80U) || (count == 3 && code < 0x800U) ||
        (count == 4 && code < 0x10000U) || code > 0x10ffffU ||
        (code >= 0xd800U && code <= 0xdfffU)) {
      return false;
    }
    index += count;
  }
  return true;
}

void SkipSpace(std::string_view text, std::size_t& index) {
  while (index < text.size() &&
         (text[index] == ' ' || text[index] == '\t' || text[index] == '\r' ||
          text[index] == '\n')) {
    ++index;
  }
}

int Hex(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

void AppendUtf8(std::uint32_t code, std::string& output) {
  if (code <= 0x7fU) {
    output.push_back(static_cast<char>(code));
  } else if (code <= 0x7ffU) {
    output.push_back(static_cast<char>(0xc0U | (code >> 6U)));
    output.push_back(static_cast<char>(0x80U | (code & 0x3fU)));
  } else if (code <= 0xffffU) {
    output.push_back(static_cast<char>(0xe0U | (code >> 12U)));
    output.push_back(static_cast<char>(0x80U | ((code >> 6U) & 0x3fU)));
    output.push_back(static_cast<char>(0x80U | (code & 0x3fU)));
  } else {
    output.push_back(static_cast<char>(0xf0U | (code >> 18U)));
    output.push_back(static_cast<char>(0x80U | ((code >> 12U) & 0x3fU)));
    output.push_back(static_cast<char>(0x80U | ((code >> 6U) & 0x3fU)));
    output.push_back(static_cast<char>(0x80U | (code & 0x3fU)));
  }
}

std::optional<std::uint32_t> ParseHex4(std::string_view text, std::size_t& index) {
  if (index + 4 > text.size()) return std::nullopt;
  std::uint32_t value = 0;
  for (int count = 0; count < 4; ++count) {
    const int digit = Hex(text[index++]);
    if (digit < 0) return std::nullopt;
    value = (value << 4U) | static_cast<std::uint32_t>(digit);
  }
  return value;
}

std::optional<std::string> ParseString(std::string_view text, std::size_t& index) {
  if (index >= text.size() || text[index++] != '"') return std::nullopt;
  std::string output;
  while (index < text.size()) {
    const unsigned char value = static_cast<unsigned char>(text[index++]);
    if (value == '"') return output;
    if (value < 0x20U) return std::nullopt;
    if (value != '\\') {
      output.push_back(static_cast<char>(value));
      continue;
    }
    if (index >= text.size()) return std::nullopt;
    const char escape = text[index++];
    switch (escape) {
      case '"': output.push_back('"'); break;
      case '\\': output.push_back('\\'); break;
      case '/': output.push_back('/'); break;
      case 'b': output.push_back('\b'); break;
      case 'f': output.push_back('\f'); break;
      case 'n': output.push_back('\n'); break;
      case 'r': output.push_back('\r'); break;
      case 't': output.push_back('\t'); break;
      case 'u': {
        auto first = ParseHex4(text, index);
        if (!first) return std::nullopt;
        std::uint32_t code = *first;
        if (code >= 0xd800U && code <= 0xdbffU) {
          if (index + 2 > text.size() || text[index] != '\\' || text[index + 1] != 'u') {
            return std::nullopt;
          }
          index += 2;
          auto second = ParseHex4(text, index);
          if (!second || *second < 0xdc00U || *second > 0xdfffU) return std::nullopt;
          code = 0x10000U + ((code - 0xd800U) << 10U) + (*second - 0xdc00U);
        } else if (code >= 0xdc00U && code <= 0xdfffU) {
          return std::nullopt;
        }
        AppendUtf8(code, output);
        break;
      }
      default: return std::nullopt;
    }
  }
  return std::nullopt;
}

}  // namespace

std::optional<Request> ParseRequestFrame(std::string_view frame) {
  if (frame.empty() || frame.size() > kMaxRequestBytes || frame.back() != '\n') {
    return std::nullopt;
  }
  frame.remove_suffix(1);
  if (!ValidUtf8(frame)) return std::nullopt;

  std::size_t index = 0;
  SkipSpace(frame, index);
  if (index >= frame.size() || frame[index++] != '{') return std::nullopt;
  std::map<std::string, std::string> fields;
  std::set<std::string> seen;
  SkipSpace(frame, index);
  if (index < frame.size() && frame[index] == '}') return std::nullopt;
  while (index < frame.size()) {
    auto key = ParseString(frame, index);
    if (!key || !seen.insert(*key).second) return std::nullopt;
    if (*key != "protocol" && *key != "operation" && *key != "aosSecret") {
      return std::nullopt;
    }
    SkipSpace(frame, index);
    if (index >= frame.size() || frame[index++] != ':') return std::nullopt;
    SkipSpace(frame, index);
    auto value = ParseString(frame, index);
    if (!value || !ValidUtf8(*value)) return std::nullopt;
    fields.emplace(*key, *value);
    SkipSpace(frame, index);
    if (index >= frame.size()) return std::nullopt;
    if (frame[index] == '}') {
      ++index;
      break;
    }
    if (frame[index++] != ',') return std::nullopt;
    SkipSpace(frame, index);
  }
  SkipSpace(frame, index);
  if (index != frame.size()) return std::nullopt;
  if (fields["protocol"] != kProtocol) return std::nullopt;

  if (fields["operation"] == "status" && fields.size() == 2) {
    return Request{Operation::kStatus, {}};
  }
  if (fields["operation"] == "issue" && fields.size() == 3 &&
      !fields["aosSecret"].empty()) {
    return Request{Operation::kIssue, fields["aosSecret"]};
  }
  return std::nullopt;
}

std::string JsonEscape(std::string_view value) {
  static constexpr char kHex[] = "0123456789abcdef";
  std::string output;
  for (const unsigned char byte : value) {
    switch (byte) {
      case '"': output += "\\\""; break;
      case '\\': output += "\\\\"; break;
      case '\b': output += "\\b"; break;
      case '\f': output += "\\f"; break;
      case '\n': output += "\\n"; break;
      case '\r': output += "\\r"; break;
      case '\t': output += "\\t"; break;
      default:
        if (byte < 0x20U) {
          output += "\\u00";
          output.push_back(kHex[byte >> 4U]);
          output.push_back(kHex[byte & 0x0fU]);
        } else {
          output.push_back(static_cast<char>(byte));
        }
    }
  }
  return output;
}

}  // namespace aos::kac
