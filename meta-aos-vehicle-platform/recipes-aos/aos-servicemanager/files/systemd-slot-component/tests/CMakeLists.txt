# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

set(TARGET_NAME systemdslotcomponent_test)

set(SOURCES providerarchive.cpp runtime.cpp)

set(LIBRARIES
    aos::core::common::tests::utils
    aos::core::common::tests::mocks
    aos::core::sm::tests::mocks
    aos::sm::imagemanager
    aos::sm::runtimes::systemdslotcomponent
    aos::sm::utils
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
