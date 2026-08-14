# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

set(TARGET_NAME systemdslotcomponent_test)

set(SOURCES runtime.cpp)

set(LIBRARIES
    aos::core::common::tests::utils
    aos::core::common::tests::mocks
    aos::core::sm::tests::mocks
    aos::sm::runtimes::systemdslotcomponent
    GTest::gmock_main
)

add_test(
    TARGET_NAME
    ${TARGET_NAME}
    LOG_MODULE
    SOURCES
    ${SOURCES}
    LIBRARIES
    ${LIBRARIES}
)
