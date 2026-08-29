// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "factory/integration.hpp"

#include <fcntl.h>
#include <openssl/bn.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/rand.h>
#include <openssl/rsa.h>
#include <openssl/x509.h>
#include <openssl/x509v3.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstdio>
#include <functional>
#include <memory>
#include <string>
#include <string_view>

namespace aos::factory {
namespace {

constexpr std::string_view kKeyName{"server.key"};
constexpr std::string_view kCertificateName{"server.pem"};
constexpr std::string_view kTemporaryKeyName{".server.key.tmp"};
constexpr std::string_view kTemporaryCertificateName{".server.pem.tmp"};

template <typename T, void (*Free)(T*)>
using OpenSslPtr = std::unique_ptr<T, decltype(Free)>;

using BioPtr = OpenSslPtr<BIO, BIO_free_all>;
using BnPtr = OpenSslPtr<BIGNUM, BN_free>;
using EvpKeyPtr = OpenSslPtr<EVP_PKEY, EVP_PKEY_free>;
using EvpKeyContextPtr = OpenSslPtr<EVP_PKEY_CTX, EVP_PKEY_CTX_free>;
using X509Ptr = OpenSslPtr<X509, X509_free>;
using X509ExtensionPtr = OpenSslPtr<X509_EXTENSION, X509_EXTENSION_free>;

bool IsExpectedFile(int directory, std::string_view name, mode_t mode) {
  struct stat status {};
  if (::fstatat(directory, std::string(name).c_str(), &status, AT_SYMLINK_NOFOLLOW) != 0) {
    return false;
  }
  return S_ISREG(status.st_mode) && status.st_uid == ::geteuid() &&
         (status.st_mode & 0777U) == mode;
}

bool Exists(int directory, std::string_view name) {
  struct stat status {};
  return ::fstatat(directory, std::string(name).c_str(), &status, AT_SYMLINK_NOFOLLOW) == 0;
}

bool RemoveRegularFileIfPresent(int directory, std::string_view name) {
  struct stat status {};
  const std::string value(name);
  if (::fstatat(directory, value.c_str(), &status, AT_SYMLINK_NOFOLLOW) != 0) {
    return errno == ENOENT;
  }
  if (!S_ISREG(status.st_mode) || status.st_uid != ::geteuid()) return false;
  return ::unlinkat(directory, value.c_str(), 0) == 0;
}

BioPtr OpenReadBio(int directory, std::string_view name) {
  const int descriptor = ::openat(directory, std::string(name).c_str(),
                                  O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (descriptor < 0) return {nullptr, BIO_free_all};
  BIO* bio = BIO_new_fd(descriptor, BIO_CLOSE);
  if (bio == nullptr) ::close(descriptor);
  return {bio, BIO_free_all};
}

bool HasIpSan(X509* certificate, std::string_view expected) {
  GENERAL_NAMES* names = static_cast<GENERAL_NAMES*>(
      X509_get_ext_d2i(certificate, NID_subject_alt_name, nullptr, nullptr));
  if (names == nullptr) return false;
  bool found = false;
  for (int index = 0; index < sk_GENERAL_NAME_num(names); ++index) {
    const GENERAL_NAME* name = sk_GENERAL_NAME_value(names, index);
    if (name->type != GEN_IPADD || name->d.iPAddress->length != 4) continue;
    const unsigned char* data = name->d.iPAddress->data;
    const std::string value = std::to_string(data[0]) + "." + std::to_string(data[1]) +
                              "." + std::to_string(data[2]) + "." + std::to_string(data[3]);
    found = value == expected;
    if (found) break;
  }
  GENERAL_NAMES_free(names);
  return found;
}

bool HasDnsSan(X509* certificate, std::string_view expected) {
  GENERAL_NAMES* names = static_cast<GENERAL_NAMES*>(
      X509_get_ext_d2i(certificate, NID_subject_alt_name, nullptr, nullptr));
  if (names == nullptr) return false;
  bool found = false;
  for (int index = 0; index < sk_GENERAL_NAME_num(names); ++index) {
    const GENERAL_NAME* name = sk_GENERAL_NAME_value(names, index);
    if (name->type != GEN_DNS) continue;
    const ASN1_STRING* dns = name->d.dNSName;
    const unsigned char* data = ASN1_STRING_get0_data(dns);
    const int length = ASN1_STRING_length(dns);
    found = length >= 0 && static_cast<std::size_t>(length) == expected.size() &&
            std::string_view(reinterpret_cast<const char*>(data), expected.size()) == expected;
    if (found) break;
  }
  GENERAL_NAMES_free(names);
  return found;
}

bool ValidateIdentity(int directory) {
  if (!IsExpectedFile(directory, kKeyName, 0600) ||
      !IsExpectedFile(directory, kCertificateName, 0644)) {
    return false;
  }
  BioPtr key_bio = OpenReadBio(directory, kKeyName);
  BioPtr certificate_bio = OpenReadBio(directory, kCertificateName);
  if (!key_bio || !certificate_bio) return false;
  EvpKeyPtr key(PEM_read_bio_PrivateKey(key_bio.get(), nullptr, nullptr, nullptr), EVP_PKEY_free);
  X509Ptr certificate(PEM_read_bio_X509(certificate_bio.get(), nullptr, nullptr, nullptr), X509_free);
  return key && certificate && X509_check_private_key(certificate.get(), key.get()) == 1 &&
         X509_cmp_current_time(X509_get0_notBefore(certificate.get())) < 0 &&
         X509_cmp_current_time(X509_get0_notAfter(certificate.get())) > 0 &&
         HasIpSan(certificate.get(), "127.0.0.1") && HasDnsSan(certificate.get(), "Server");
}

EvpKeyPtr GenerateKey() {
  EvpKeyContextPtr context(EVP_PKEY_CTX_new_id(EVP_PKEY_RSA, nullptr), EVP_PKEY_CTX_free);
  EVP_PKEY* raw = nullptr;
  if (!context || EVP_PKEY_keygen_init(context.get()) <= 0 ||
      EVP_PKEY_CTX_set_rsa_keygen_bits(context.get(), 2048) <= 0 ||
      EVP_PKEY_keygen(context.get(), &raw) <= 0) {
    EVP_PKEY_free(raw);
    return {nullptr, EVP_PKEY_free};
  }
  return {raw, EVP_PKEY_free};
}

X509Ptr GenerateCertificate(EVP_PKEY* key) {
  X509Ptr certificate(X509_new(), X509_free);
  BnPtr serial(BN_new(), BN_free);
  if (!certificate || !serial || BN_rand(serial.get(), 128, BN_RAND_TOP_ANY, BN_RAND_BOTTOM_ANY) != 1 ||
      BN_to_ASN1_INTEGER(serial.get(), X509_get_serialNumber(certificate.get())) == nullptr ||
      X509_set_version(certificate.get(), 2) != 1 ||
      X509_gmtime_adj(X509_getm_notBefore(certificate.get()), -300) == nullptr ||
      X509_gmtime_adj(X509_getm_notAfter(certificate.get()), 315360000L) == nullptr ||
      X509_set_pubkey(certificate.get(), key) != 1) {
    return {nullptr, X509_free};
  }

  X509_NAME* name = X509_get_subject_name(certificate.get());
  constexpr unsigned char common_name[] = "AosEdge per-vehicle KUKSA";
  if (name == nullptr || X509_NAME_add_entry_by_NID(
                             name, NID_commonName, MBSTRING_ASC, common_name, -1, -1, 0) != 1 ||
      X509_set_issuer_name(certificate.get(), name) != 1) {
    return {nullptr, X509_free};
  }
  X509ExtensionPtr basic_constraints(
      X509V3_EXT_conf_nid(nullptr, nullptr, NID_basic_constraints,
                         const_cast<char*>("critical,CA:FALSE")),
      X509_EXTENSION_free);
  X509ExtensionPtr key_usage(
      X509V3_EXT_conf_nid(nullptr, nullptr, NID_key_usage,
                         const_cast<char*>("critical,digitalSignature,keyEncipherment")),
      X509_EXTENSION_free);
  X509ExtensionPtr extended_key_usage(
      X509V3_EXT_conf_nid(nullptr, nullptr, NID_ext_key_usage,
                         const_cast<char*>("serverAuth")),
      X509_EXTENSION_free);
  X509ExtensionPtr subject_alt_name(
      X509V3_EXT_conf_nid(nullptr, nullptr, NID_subject_alt_name,
                         const_cast<char*>("IP:127.0.0.1,DNS:Server")),
      X509_EXTENSION_free);
  if (!basic_constraints || !key_usage || !extended_key_usage || !subject_alt_name ||
      X509_add_ext(certificate.get(), basic_constraints.get(), -1) != 1 ||
      X509_add_ext(certificate.get(), key_usage.get(), -1) != 1 ||
      X509_add_ext(certificate.get(), extended_key_usage.get(), -1) != 1 ||
      X509_add_ext(certificate.get(), subject_alt_name.get(), -1) != 1 ||
      X509_sign(certificate.get(), key, EVP_sha256()) <= 0) {
    return {nullptr, X509_free};
  }
  return certificate;
}

bool WriteIdentityFile(int directory, std::string_view name, mode_t mode,
                       const std::function<bool(BIO*)>& writer) {
  const int descriptor = ::openat(directory, std::string(name).c_str(),
                                  O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, mode);
  if (descriptor < 0) return false;
  if (::fchmod(descriptor, mode) != 0) {
    ::close(descriptor);
    ::unlinkat(directory, std::string(name).c_str(), 0);
    return false;
  }
  BIO* raw = BIO_new_fd(descriptor, BIO_NOCLOSE);
  const bool ok = raw != nullptr && writer(raw) && BIO_flush(raw) == 1 && ::fsync(descriptor) == 0;
  BIO_free_all(raw);
  ::close(descriptor);
  if (!ok) ::unlinkat(directory, std::string(name).c_str(), 0);
  return ok;
}

}  // namespace

TlsPrepareResult PrepareTlsIdentity(std::string_view directory_path) {
  const std::string path(directory_path);
  const int directory = ::open(path.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
  if (directory < 0) return TlsPrepareResult::kUnavailable;
  struct stat directory_status {};
  if (::fstat(directory, &directory_status) != 0 || !S_ISDIR(directory_status.st_mode) ||
      directory_status.st_uid != ::geteuid() || (directory_status.st_mode & 0777U) != 0700U) {
    ::close(directory);
    return TlsPrepareResult::kRejected;
  }

  const bool key_exists = Exists(directory, kKeyName);
  const bool certificate_exists = Exists(directory, kCertificateName);
  if (key_exists && certificate_exists) {
    const bool valid = ValidateIdentity(directory);
    ::close(directory);
    return valid ? TlsPrepareResult::kReused : TlsPrepareResult::kRejected;
  }
  if ((key_exists && !RemoveRegularFileIfPresent(directory, kKeyName)) ||
      (certificate_exists && !RemoveRegularFileIfPresent(directory, kCertificateName)) ||
      !RemoveRegularFileIfPresent(directory, kTemporaryKeyName) ||
      !RemoveRegularFileIfPresent(directory, kTemporaryCertificateName)) {
    ::close(directory);
    return TlsPrepareResult::kRejected;
  }

  EvpKeyPtr key = GenerateKey();
  X509Ptr certificate = key ? GenerateCertificate(key.get()) : X509Ptr(nullptr, X509_free);
  const bool key_written = key && WriteIdentityFile(
      directory, kTemporaryKeyName, 0600,
      [&key](BIO* bio) { return PEM_write_bio_PrivateKey(bio, key.get(), nullptr, nullptr, 0, nullptr, nullptr) == 1; });
  const bool certificate_written = certificate && WriteIdentityFile(
      directory, kTemporaryCertificateName, 0644,
      [&certificate](BIO* bio) { return PEM_write_bio_X509(bio, certificate.get()) == 1; });
  bool published = key_written && certificate_written &&
                   ::renameat(directory, std::string(kTemporaryKeyName).c_str(), directory,
                              std::string(kKeyName).c_str()) == 0 &&
                   ::renameat(directory, std::string(kTemporaryCertificateName).c_str(), directory,
                              std::string(kCertificateName).c_str()) == 0 &&
                   ::fsync(directory) == 0 && ValidateIdentity(directory);
  if (!published) {
    RemoveRegularFileIfPresent(directory, kTemporaryKeyName);
    RemoveRegularFileIfPresent(directory, kTemporaryCertificateName);
    if (!Exists(directory, kCertificateName)) RemoveRegularFileIfPresent(directory, kKeyName);
  }
  ::close(directory);
  return published ? TlsPrepareResult::kCreated : TlsPrepareResult::kUnavailable;
}

}  // namespace aos::factory

#ifndef AOS_FACTORY_NO_MAIN
int main() {
  const auto result = aos::factory::PrepareTlsIdentity("/var/lib/aos-kuksa-tls");
  switch (result) {
    case aos::factory::TlsPrepareResult::kCreated:
      std::puts("created per-vehicle KUKSA TLS identity");
      return 0;
    case aos::factory::TlsPrepareResult::kReused:
      std::puts("validated existing per-vehicle KUKSA TLS identity");
      return 0;
    case aos::factory::TlsPrepareResult::kRejected:
      std::fputs("rejected unsafe or invalid KUKSA TLS identity state\n", stderr);
      return 1;
    case aos::factory::TlsPrepareResult::kUnavailable:
      std::fputs("could not prepare KUKSA TLS identity\n", stderr);
      return 1;
  }
  return 1;
}
#endif
