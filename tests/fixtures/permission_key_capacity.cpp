// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

// Exercise the native StaticString storage used by itemconfig.cpp's mFunction.
// Include only these portable headers, not unrelated Linux/threading types.
// The companion test verifies the original field declaration and build flags.
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

#include <core/common/config.hpp>
#include <core/common/tools/string.hpp>

int main()
{
    constexpr auto capacity = AOS_CONFIG_TYPES_FUNCTION_LEN;
    static_assert(AOS_CONFIG_TYPES_PERMISSIONS_LEN == 32, "Permission values must not change");
    static_assert(AOS_CONFIG_TYPES_FUNCTIONS_MAX_COUNT == 32, "Permission counts must not change");

    const char* paths[] = {
        "Vehicle.Speed",
        "Vehicle.Acceleration.Lateral",
        "Vehicle.Acceleration.Longitudinal",
        "Vehicle.Acceleration.Vertical",
        "Vehicle.Chassis.Accelerator.PedalPosition",
        "Vehicle.Chassis.Brake.PedalPosition",
    };
    aos::StaticString<capacity> function;
    aos::StaticString<AOS_CONFIG_TYPES_PERMISSIONS_LEN> permissions;
    assert(permissions.Assign("r").IsNone());
    unsigned accepted = 0;
    for (const auto path : paths) {
        const auto fits = std::strlen(path) <= capacity;
        const auto error = function.Assign(path);
        assert(error.IsNone() == fits);
        if (fits) {
            ++accepted;
            assert(std::strcmp(function.CStr(), path) == 0);
        }
        assert(std::strcmp(permissions.CStr(), "r") == 0);
    }

    const std::string boundary(capacity, 'x');
    const std::string tooLong(capacity + 1, 'y');
    assert(function.Assign(boundary.c_str()).IsNone());
    assert(std::strcmp(function.CStr(), boundary.c_str()) == 0);
    assert(!function.Assign(tooLong.c_str()).IsNone());
    // Oversize keys must fail, never truncate or overwrite the previous key.
    assert(std::strcmp(function.CStr(), boundary.c_str()) == 0);
    assert(function.Assign("Vehicle.Speed").IsNone());
    assert(function.Assign("Vehicle.Speed").IsNone());
    assert(std::strcmp(function.CStr(), "Vehicle.Speed") == 0);
    // The IAM RPC must allocate by function count (32), not functional
    // service count (16). Exercise the real native bounded-array container.
    aos::StaticArray<int, AOS_CONFIG_TYPES_FUNC_SERVICE_MAX_COUNT> oldReply;
    aos::StaticArray<int, AOS_CONFIG_TYPES_FUNCTIONS_MAX_COUNT> correctedReply;
    for (int i = 0; i < 17; ++i) {
        assert(oldReply.PushBack(i).IsNone() == (i < 16));
        assert(correctedReply.PushBack(i).IsNone());
    }
    assert(oldReply.Size() == 16 && correctedReply.Size() == 17);
    for (int i = 17; i < 32; ++i) assert(correctedReply.PushBack(i).IsNone());
    assert(!correctedReply.PushBack(32).IsNone());
    assert(correctedReply.Size() == 32);
    std::printf("capacity=%zu accepted=%u rejected=%u boundary=PASS repeat=PASS\n",
        static_cast<size_t>(capacity), accepted, 6 - accepted);
}
