// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#include "kac/core.hpp"

#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <openssl/provider.h>
#include <openssl/rsa.h>
#include <openssl/store.h>
#include <openssl/ui.h>

#include <cstdlib>
#include <fstream>
#include <iterator>
#include <limits>
#include <memory>
#include <mutex>

namespace aos::kac {
namespace {

constexpr const char* kCredentialName = "kuksa-jwt-pin";
constexpr const char* kPrivateKeyUri =
    "pkcs11:token=aos-kuksa;object=kuksa-jwt;type=private";

std::string ReadCredential() {
  const char* directory = std::getenv("CREDENTIALS_DIRECTORY");
  if (directory == nullptr || *directory == '\0') return {};
  const std::string path = std::string(directory) + "/" + kCredentialName;
  std::ifstream input(path, std::ios::binary);
  if (!input) return {};
  std::string pin{std::istreambuf_iterator<char>(input), {}};
  while (!pin.empty() && (pin.back() == '\n' || pin.back() == '\r')) pin.pop_back();
  if (pin.empty() || pin.size() > 256U) {
    if (!pin.empty()) OPENSSL_cleanse(pin.data(), pin.size());
    return {};
  }
  return pin;
}

int UiReader(UI* ui, UI_STRING* prompt) {
  if (UI_get_string_type(prompt) != UIT_PROMPT &&
      UI_get_string_type(prompt) != UIT_VERIFY) {
    return 1;
  }
  const auto* pin = static_cast<const std::string*>(UI_get0_user_data(ui));
  if (pin == nullptr) return 0;
  return UI_set_result(ui, prompt, pin->c_str()) >= 0 ? 1 : 0;
}

struct UiMethodDeleter {
  void operator()(UI_METHOD* method) const { UI_destroy_method(method); }
};

struct BioDeleter {
  void operator()(BIO* bio) const { BIO_free(bio); }
};

struct MdCtxDeleter {
  void operator()(EVP_MD_CTX* context) const { EVP_MD_CTX_free(context); }
};

}  // namespace

class Pkcs11Signer::Impl {
 public:
  Impl() {
    pin_ = ReadCredential();
    if (pin_.empty()) return;
    default_provider_ = OSSL_PROVIDER_load(nullptr, "default");
    pkcs11_provider_ = OSSL_PROVIDER_load(nullptr, "pkcs11");
    if (default_provider_ == nullptr || pkcs11_provider_ == nullptr) return;
    std::unique_ptr<UI_METHOD, UiMethodDeleter> ui(UI_create_method("kac-pin"));
    if (!ui || UI_method_set_reader(ui.get(), UiReader) != 0) return;
    OSSL_STORE_CTX* store = OSSL_STORE_open_ex(
        kPrivateKeyUri, nullptr, nullptr, ui.get(), &pin_, nullptr, nullptr, nullptr);
    if (store == nullptr) return;
    bool ambiguous_or_invalid = false;
    while (!OSSL_STORE_eof(store)) {
      OSSL_STORE_INFO* info = OSSL_STORE_load(store);
      if (info == nullptr) {
        if (OSSL_STORE_error(store)) {
          ambiguous_or_invalid = true;
          break;
        }
        continue;
      }
      if (OSSL_STORE_INFO_get_type(info) == OSSL_STORE_INFO_PKEY) {
        EVP_PKEY* candidate = OSSL_STORE_INFO_get1_PKEY(info);
        if (candidate != nullptr && key_ != nullptr) {
          EVP_PKEY_free(candidate);
          ambiguous_or_invalid = true;
        } else if (candidate != nullptr) {
          key_ = candidate;
        }
      }
      OSSL_STORE_INFO_free(info);
      if (ambiguous_or_invalid) break;
    }
    if (OSSL_STORE_close(store) != 1) ambiguous_or_invalid = true;
    if (ambiguous_or_invalid) {
      EVP_PKEY_free(key_);
      key_ = nullptr;
    }
    if (key_ == nullptr) return;

    std::unique_ptr<BIO, BioDeleter> output(BIO_new(BIO_s_mem()));
    if (!output || PEM_write_bio_PUBKEY(output.get(), key_) != 1) return;
    char* data = nullptr;
    const long size = BIO_get_mem_data(output.get(), &data);
    if (size <= 0 || data == nullptr ||
        size > static_cast<long>(std::numeric_limits<int>::max())) {
      return;
    }
    public_key_pem_.assign(data, static_cast<std::size_t>(size));
    std::unique_ptr<BIO, BioDeleter> input(BIO_new_mem_buf(
        public_key_pem_.data(), static_cast<int>(public_key_pem_.size())));
    if (!input) return;
    verification_key_ = PEM_read_bio_PUBKEY_ex(
        input.get(), nullptr, nullptr, nullptr, nullptr, "provider=default");
    if (verification_key_ == nullptr) public_key_pem_.clear();
  }

  ~Impl() {
    EVP_PKEY_free(verification_key_);
    EVP_PKEY_free(key_);
    if (pkcs11_provider_ != nullptr) OSSL_PROVIDER_unload(pkcs11_provider_);
    if (default_provider_ != nullptr) OSSL_PROVIDER_unload(default_provider_);
    if (!pin_.empty()) OPENSSL_cleanse(pin_.data(), pin_.size());
  }

  bool Ready() const {
    return key_ != nullptr && verification_key_ != nullptr &&
           EVP_PKEY_is_a(key_, "RSA") == 1 && EVP_PKEY_bits(key_) == 2048 &&
           EVP_PKEY_is_a(verification_key_, "RSA") == 1 &&
           EVP_PKEY_bits(verification_key_) == 2048;
  }

  std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) {
    std::lock_guard<std::mutex> guard(lock_);
    if (!Ready()) return std::nullopt;
    std::unique_ptr<EVP_MD_CTX, MdCtxDeleter> context(EVP_MD_CTX_new());
    EVP_PKEY_CTX* key_context = nullptr;
    if (!context ||
        EVP_DigestSignInit(
            context.get(), &key_context, EVP_sha256(), nullptr, key_) != 1 ||
        key_context == nullptr ||
        EVP_PKEY_CTX_set_rsa_padding(key_context, RSA_PKCS1_PADDING) != 1 ||
        EVP_DigestSignUpdate(context.get(), input.data(), input.size()) != 1) {
      return std::nullopt;
    }
    const int key_size = EVP_PKEY_get_size(key_);
    if (key_size != 256) {
      return std::nullopt;
    }
    std::size_t size = static_cast<std::size_t>(key_size);
    std::vector<std::uint8_t> signature(size);
    if (EVP_DigestSignFinal(context.get(), signature.data(), &size) != 1) {
      return std::nullopt;
    }
    if (size != static_cast<std::size_t>(key_size)) return std::nullopt;
    signature.resize(size);
    return signature;
  }

  bool Verify(std::string_view input, const std::vector<std::uint8_t>& signature) const {
    std::lock_guard<std::mutex> guard(lock_);
    if (!Ready()) return false;
    std::unique_ptr<EVP_MD_CTX, MdCtxDeleter> context(EVP_MD_CTX_new());
    EVP_PKEY_CTX* key_context = nullptr;
    return context &&
           EVP_DigestVerifyInit(
               context.get(), &key_context, EVP_sha256(), nullptr,
               verification_key_) == 1 &&
           key_context != nullptr &&
           EVP_PKEY_CTX_set_rsa_padding(key_context, RSA_PKCS1_PADDING) == 1 &&
           EVP_DigestVerifyUpdate(context.get(), input.data(), input.size()) == 1 &&
           EVP_DigestVerifyFinal(context.get(), signature.data(), signature.size()) == 1;
  }

  std::optional<std::string> PublicKeyPem() const {
    std::lock_guard<std::mutex> guard(lock_);
    if (!Ready()) return std::nullopt;
    return public_key_pem_;
  }

 private:
  std::string pin_;
  OSSL_PROVIDER* default_provider_{nullptr};
  OSSL_PROVIDER* pkcs11_provider_{nullptr};
  EVP_PKEY* key_{nullptr};
  EVP_PKEY* verification_key_{nullptr};
  std::string public_key_pem_;
  mutable std::mutex lock_;
};

Pkcs11Signer::Pkcs11Signer() : impl_(new Impl()) {}
Pkcs11Signer::~Pkcs11Signer() { delete impl_; }
bool Pkcs11Signer::Ready() const { return impl_->Ready(); }
std::optional<std::vector<std::uint8_t>> Pkcs11Signer::Sign(std::string_view input) {
  return impl_->Sign(input);
}
bool Pkcs11Signer::Verify(
    std::string_view input, const std::vector<std::uint8_t>& signature) const {
  return impl_->Verify(input, signature);
}
std::optional<std::string> Pkcs11Signer::PublicKeyPem() const {
  return impl_->PublicKeyPem();
}

}  // namespace aos::kac
