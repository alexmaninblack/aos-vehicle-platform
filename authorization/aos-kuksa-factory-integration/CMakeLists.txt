# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20)
project(aos_kuksa_factory_integration VERSION 0.1.0 LANGUAGES CXX)

find_package(OpenSSL REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(kuksa_factory_logic STATIC src/token_init.cpp src/runtime_cleanup.cpp src/tls_prepare.cpp)
target_compile_definitions(kuksa_factory_logic PRIVATE AOS_FACTORY_NO_MAIN=1)
target_include_directories(kuksa_factory_logic PUBLIC include)
target_compile_options(kuksa_factory_logic PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(kuksa_factory_logic PUBLIC ${CMAKE_DL_LIBS} OpenSSL::Crypto)

add_executable(aos-kuksa-token-init src/token_init.cpp)
target_include_directories(aos-kuksa-token-init PRIVATE include)
target_compile_options(aos-kuksa-token-init PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(aos-kuksa-token-init PRIVATE ${CMAKE_DL_LIBS})

add_executable(aos-kuksa-runtime-cleanup src/runtime_cleanup.cpp)
target_include_directories(aos-kuksa-runtime-cleanup PRIVATE include)
target_compile_options(aos-kuksa-runtime-cleanup PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(aos-kuksa-tls-prepare src/tls_prepare.cpp)
target_include_directories(aos-kuksa-tls-prepare PRIVATE include)
target_compile_options(aos-kuksa-tls-prepare PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(aos-kuksa-tls-prepare PRIVATE OpenSSL::Crypto)

include(CTest)
if(BUILD_TESTING)
  add_executable(factory-integration-tests tests/factory_integration_tests.cpp)
  target_compile_options(factory-integration-tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
  target_link_libraries(factory-integration-tests PRIVATE kuksa_factory_logic)
  add_test(NAME factory-integration-tests COMMAND factory-integration-tests)
endif()

include(GNUInstallDirs)
install(TARGETS aos-kuksa-token-init aos-kuksa-runtime-cleanup aos-kuksa-tls-prepare
  RUNTIME DESTINATION ${CMAKE_INSTALL_LIBEXECDIR})
