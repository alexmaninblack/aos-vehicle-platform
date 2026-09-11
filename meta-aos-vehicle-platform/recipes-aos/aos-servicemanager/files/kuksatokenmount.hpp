// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#ifndef AOS_DEMO_KUKSA_TOKEN_MOUNT_HPP
#define AOS_DEMO_KUKSA_TOKEN_MOUNT_HPP

#include <cstdint>
#include <limits>
#include <set>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace aos::sm::launcher::demo {

enum class TokenMountState { Unchanged, Adjusted, Invalid };

struct TokenMountResult {
    TokenMountState state;
    std::vector<std::string> options;
};

// Only the platform-owned KAC credential mount has per-instance ownership.
// Resource declarations stay immutable; no placeholder expansion, fixed UID,
// extra capability, writable host directory or broader mode is introduced.
inline TokenMountResult BindKuksaTokenOwner(std::string_view resource, std::string_view destination,
    std::string_view type, std::string_view source, const std::vector<std::string>& options,
    std::uint32_t uid, std::uint32_t gid)
{
    if (resource != "kuksa-auth-client" || destination != "/run/aosedge/secrets/kuksa") {
        return {TokenMountState::Unchanged, options};
    }

    const std::set<std::string> expected {"rw", "nosuid", "nodev", "noexec", "mode=0700", "size=65536"};
    const std::set<std::string> actual(options.begin(), options.end());
    if (type != "tmpfs" || source != "tmpfs" || uid == 0 || gid == 0
        || uid == std::numeric_limits<std::uint32_t>::max()
        || gid == std::numeric_limits<std::uint32_t>::max()
        || options.size() != expected.size() || actual != expected) {
        return {TokenMountState::Invalid, {}};
    }

    auto owned = options;
    owned.emplace_back("uid=" + std::to_string(uid));
    owned.emplace_back("gid=" + std::to_string(gid));
    return {TokenMountState::Adjusted, std::move(owned)};
}

} // namespace aos::sm::launcher::demo

#endif
