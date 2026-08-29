# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20)
project(aos_kuksa_auth_compat VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Protobuf REQUIRED)
find_package(gRPC CONFIG REQUIRED)
find_package(absl CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)

if(NOT DEFINED AOS_CORE_API_DIR)
  message(FATAL_ERROR "AOS_CORE_API_DIR must name the pinned aos_core_api checkout")
endif()
if(NOT DEFINED Protobuf_PROTOC_EXECUTABLE)
  message(FATAL_ERROR "Protobuf_PROTOC_EXECUTABLE must name the pinned native protoc")
endif()
if(NOT DEFINED GRPC_CPP_PLUGIN_EXECUTABLE)
  message(FATAL_ERROR "GRPC_CPP_PLUGIN_EXECUTABLE must name the pinned native gRPC plugin")
endif()

set(GENERATED_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
set(IAM_PROTO "${AOS_CORE_API_DIR}/proto/iamanager/v6/iamanager.proto")
set(COMMON_PROTO "${AOS_CORE_API_DIR}/proto/common/v2/common.proto")
set(GENERATED_SOURCES
  "${GENERATED_DIR}/iamanager/v6/iamanager.pb.cc"
  "${GENERATED_DIR}/iamanager/v6/iamanager.grpc.pb.cc"
  "${GENERATED_DIR}/common/v2/common.pb.cc")
set(GENERATED_HEADERS
  "${GENERATED_DIR}/iamanager/v6/iamanager.pb.h"
  "${GENERATED_DIR}/iamanager/v6/iamanager.grpc.pb.h"
  "${GENERATED_DIR}/common/v2/common.pb.h")

add_custom_command(
  OUTPUT ${GENERATED_SOURCES} ${GENERATED_HEADERS}
  COMMAND ${CMAKE_COMMAND} -E make_directory "${GENERATED_DIR}"
  COMMAND "${Protobuf_PROTOC_EXECUTABLE}"
    "--proto_path=${AOS_CORE_API_DIR}/proto"
    "--cpp_out=${GENERATED_DIR}"
    "--grpc_out=${GENERATED_DIR}"
    "--plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN_EXECUTABLE}"
    "${COMMON_PROTO}" "${IAM_PROTO}"
  DEPENDS "${COMMON_PROTO}" "${IAM_PROTO}"
  VERBATIM)

add_library(kac_proto STATIC ${GENERATED_SOURCES})
target_include_directories(kac_proto PUBLIC "${GENERATED_DIR}")
target_link_libraries(kac_proto PUBLIC
  gRPC::grpc++
  protobuf::libprotobuf
  absl::log_internal_check_op)

add_library(kac_core STATIC
  src/core.cpp
  src/json.cpp
  src/grpc_iam_client.cpp
  src/pkcs11_signer.cpp)
add_dependencies(kac_core kac_proto)
target_include_directories(kac_core PUBLIC include "${GENERATED_DIR}")
target_compile_options(kac_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(kac_core PUBLIC kac_proto OpenSSL::Crypto)

add_executable(aos-kuksa-auth-compat src/main.cpp src/server.cpp)
target_compile_options(aos-kuksa-auth-compat PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(aos-kuksa-auth-compat PRIVATE kac_core pthread)

add_executable(aos-kuksa-verifier-prepare src/verifier_prepare.cpp)
target_compile_options(aos-kuksa-verifier-prepare PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(aos-kuksa-verifier-prepare PRIVATE kac_core)

include(CTest)
if(BUILD_TESTING)
  add_executable(kac-tests tests/kac_tests.cpp)
  target_compile_options(kac-tests PRIVATE -Wall -Wextra -Wpedantic -Werror)
  target_link_libraries(kac-tests PRIVATE kac_core)
  add_test(NAME kac-tests COMMAND kac-tests)
endif()

include(GNUInstallDirs)
install(TARGETS aos-kuksa-auth-compat aos-kuksa-verifier-prepare
  RUNTIME DESTINATION ${CMAKE_INSTALL_LIBEXECDIR})
