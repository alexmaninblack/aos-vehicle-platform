// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

#include <grpcpp/grpcpp.h>
#include <grpcpp/security/credentials.h>

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <memory>
#include <utility>

#include "iamanager/v6/iamanager.grpc.pb.h"

namespace aos::kac {
namespace {

constexpr const char* kIamEndpoint = "ipv4:127.0.0.1:8090";
constexpr const char* kExpectedServerName = "main";
constexpr const char* kCaCredential = "aos-iam-ca";

std::string ReadCa() {
  const char* credentials = std::getenv("CREDENTIALS_DIRECTORY");
  if (credentials == nullptr || credentials[0] != '/') return {};
  const std::string path = std::string(credentials) + "/" + kCaCredential;
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  return std::string(std::istreambuf_iterator<char>(input), {});
}

std::string InstanceSubject(const common::v2::InstanceIdent& instance) {
  if (instance.item_id().empty() || instance.subject_id().empty()) return {};
  return instance.item_id() + ":" + instance.subject_id() + ":" +
         std::to_string(instance.instance());
}

}  // namespace

class GrpcIamClient::Impl {
 public:
  Impl() {
    grpc::SslCredentialsOptions options;
    options.pem_root_certs = ReadCa();
    if (options.pem_root_certs.empty()) return;
    grpc::ChannelArguments arguments;
    arguments.SetSslTargetNameOverride(kExpectedServerName);
    arguments.SetInt(GRPC_ARG_DNS_ENABLE_SRV_QUERIES, 0);
    arguments.SetInt("grpc.enable_http_proxy", 0);
    arguments.SetMaxReceiveMessageSize(64 * 1024);
    channel_ = grpc::CreateCustomChannel(kIamEndpoint, grpc::SslCredentials(options), arguments);
    stub_ = iamanager::v6::IAMPublicPermissionsService::NewStub(channel_);
  }

  IamResult Get(std::string_view secret) {
    if (!stub_ || secret.empty()) return {IamResult::Status::kUnavailable, {}};
    iamanager::v6::PermissionsRequest request;
    request.set_secret(secret.data(), secret.size());
    request.set_functional_server_id(std::string(kFixedResource));
    iamanager::v6::PermissionsResponse response;
    grpc::ClientContext context;
    context.set_deadline(std::chrono::system_clock::now() + std::chrono::seconds(3));
    const grpc::Status status = stub_->GetPermissions(&context, request, &response);
    if (!status.ok()) {
      if (status.error_code() == grpc::StatusCode::PERMISSION_DENIED ||
          status.error_code() == grpc::StatusCode::UNAUTHENTICATED ||
          status.error_code() == grpc::StatusCode::NOT_FOUND) {
        return {IamResult::Status::kDenied, {}};
      }
      return {IamResult::Status::kUnavailable, {}};
    }
    IamDecision decision;
    decision.instance_subject = InstanceSubject(response.instance());
    const auto permission_count = response.permissions().permissions_size();
    if (permission_count > static_cast<int>(kMaxPermissions)) {
      return {IamResult::Status::kUnsupported, {}};
    }
    decision.permissions.reserve(static_cast<std::size_t>(permission_count));
    for (const auto& [path, mode] : response.permissions().permissions()) {
      if (path.size() > kMaxPathBytes) {
        return {IamResult::Status::kUnsupported, {}};
      }
      decision.permissions.push_back(Permission{path, mode});
    }
    if (decision.instance_subject.empty()) return {IamResult::Status::kDenied, {}};
    return {IamResult::Status::kAllowed, std::move(decision)};
  }

 private:
  std::shared_ptr<grpc::Channel> channel_;
  std::unique_ptr<iamanager::v6::IAMPublicPermissionsService::Stub> stub_;
};

GrpcIamClient::GrpcIamClient() : impl_(new Impl()) {}
GrpcIamClient::~GrpcIamClient() { delete impl_; }
IamResult GrpcIamClient::GetPermissions(std::string_view secret) { return impl_->Get(secret); }

}  // namespace aos::kac
