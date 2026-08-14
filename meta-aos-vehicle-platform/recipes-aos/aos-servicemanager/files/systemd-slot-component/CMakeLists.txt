# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

set(TARGET_NAME systemdslotcomponent)

set(SOURCES config.cpp runtime.cpp)
set(HEADERS config.hpp runtime.hpp)

set(LIBRARIES Poco::JSON aos::sm::runtimes::utils)
set(HEADERS_BASE_DIRS ${CMAKE_CURRENT_SOURCE_DIR})

add_module(
    TARGET_NAME
    ${TARGET_NAME}
    LOG_MODULE
    STACK_USAGE
    ${AOS_STACK_USAGE}
    DEFINES
    AOS_SYSTEMD_SLOT_COMPONENT_RUNTIME
    INCLUDES
    ${CMAKE_CURRENT_SOURCE_DIR}
    SOURCES
    ${SOURCES}
    HEADERS
    ${HEADERS}
    LIBRARIES
    ${LIBRARIES}
)

if(WITH_TEST)
    add_subdirectory(tests)
endif()
