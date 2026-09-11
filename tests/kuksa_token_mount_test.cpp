// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kuksatokenmount.hpp"
#include <algorithm>
#include <cassert>

using aos::sm::launcher::demo::BindKuksaTokenOwner;
using aos::sm::launcher::demo::TokenMountState;

int main()
{
    const std::vector<std::string> options {"rw", "nosuid", "nodev", "noexec", "mode=0700", "size=65536"};
    const auto bind = [&](const std::vector<std::string>& values, std::uint32_t uid, std::uint32_t gid) {
        return BindKuksaTokenOwner("kuksa-auth-client", "/run/aosedge/secrets/kuksa", "tmpfs", "tmpfs", values, uid, gid);
    };
    for (const auto uid : {5000U, 8372U, 65536U}) {
        const auto result = bind(options, uid, uid + 1);
        assert(result.state == TokenMountState::Adjusted);
        assert(result.options.size() == 8);
        assert(result.options[6] == "uid=" + std::to_string(uid));
        assert(result.options[7] == "gid=" + std::to_string(uid + 1));
        assert(std::equal(options.begin(), options.end(), result.options.begin()));
        assert(bind(options, uid, uid + 1).options == result.options);
    }
    auto reversed = options;
    std::reverse(reversed.begin(), reversed.end());
    assert(bind(reversed, 5000, 5001).state == TokenMountState::Adjusted);
    assert(options.size() == 6); // Shared resource definition was never changed.

    for (const auto& extra : {"uid=5000", "gid=5000", "mode=0777", "exec", "suid", "context=unconfined_t", "rw"}) {
        auto bad = options;
        bad.emplace_back(extra);
        assert(bind(bad, 5000, 5001).state == TokenMountState::Invalid);
    }
    for (std::size_t index = 0; index < options.size(); ++index) {
        auto missing = options;
        missing.erase(missing.begin() + index);
        assert(bind(missing, 5000, 5001).state == TokenMountState::Invalid);
    }
    for (const auto invalid : {0U, std::numeric_limits<std::uint32_t>::max()}) {
        assert(bind(options, invalid, 5001).state == TokenMountState::Invalid);
        assert(bind(options, 5000, invalid).state == TokenMountState::Invalid);
    }
    for (const auto& pair : {std::pair {"bind", "tmpfs"}, std::pair {"tmpfs", "/host/path"}}) {
        assert(BindKuksaTokenOwner("kuksa-auth-client", "/run/aosedge/secrets/kuksa", pair.first, pair.second,
            options, 5000, 5001).state == TokenMountState::Invalid);
    }
    for (const auto& pair : {std::pair {"other-resource", "/run/aosedge/secrets/kuksa"},
             std::pair {"kuksa-auth-client", "/run/aosedge/platform/kuksa-auth"},
             std::pair {"kuksa-auth-client", "/run/aosedge/secrets/kuksa/child"}}) {
        const auto result = BindKuksaTokenOwner(pair.first, pair.second, "bind", "/host/path", options, 0, 0);
        assert(result.state == TokenMountState::Unchanged);
        assert(result.options == options);
    }
}
