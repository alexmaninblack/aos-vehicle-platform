// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <string_view>

namespace aos::kac {

// Removes only an exact, caller-owned regular temporary verifier with one
// hard link. Missing state is already clean; any other object fails closed.
bool RemoveStaleTemporaryVerifier(std::string_view path);

}  // namespace aos::kac
