// SPDX-FileCopyrightText: 2026 maninblack
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aos::kac::provider {

inline constexpr std::int64_t kLifetimeSeconds = 604800;
inline constexpr std::int64_t kMaximumFutureSeconds = 5;
inline constexpr std::size_t kMaximumJwtBytes = 16U * 1024U;

inline constexpr std::string_view kHeader =
    R"({"alg":"RS256","typ":"JWT"})";
inline constexpr std::string_view kScope =
    "provide:Vehicle.Acceleration.Lateral "
    "provide:Vehicle.Acceleration.Longitudinal "
    "provide:Vehicle.Acceleration.Vertical "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row1.Left.LateralSlipAngle "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row1.Left.LongitudinalSlip "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row1.Right.LateralSlipAngle "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row1.Right.LongitudinalSlip "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row2.Left.LateralSlipAngle "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row2.Left.LongitudinalSlip "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row2.Right.LateralSlipAngle "
    "provide:Vehicle.CarlaSimulation.ChaosWheel.Row2.Right.LongitudinalSlip "
    "provide:Vehicle.Chassis.Accelerator.PedalPosition "
    "provide:Vehicle.Chassis.Axle.Row1.SteeringAngle "
    "provide:Vehicle.Chassis.Axle.Row1.Wheel.Left.AngularSpeed "
    "provide:Vehicle.Chassis.Axle.Row1.Wheel.Left.Speed "
    "provide:Vehicle.Chassis.Axle.Row1.Wheel.Right.AngularSpeed "
    "provide:Vehicle.Chassis.Axle.Row1.Wheel.Right.Speed "
    "provide:Vehicle.Chassis.Axle.Row2.Wheel.Left.AngularSpeed "
    "provide:Vehicle.Chassis.Axle.Row2.Wheel.Left.Speed "
    "provide:Vehicle.Chassis.Axle.Row2.Wheel.Right.AngularSpeed "
    "provide:Vehicle.Chassis.Axle.Row2.Wheel.Right.Speed "
    "provide:Vehicle.Chassis.Brake.PedalPosition "
    "provide:Vehicle.OEM.BrakeHealth.Advisory.GatewayStatus "
    "provide:Vehicle.OEM.TireHealth.Advisory.GatewayStatus "
    "provide:Vehicle.Speed "
    "read:Vehicle.OEM.BrakeHealth.Advisory.Request "
    "read:Vehicle.OEM.TireHealth.Advisory.Request";

class Signer {
 public:
  virtual ~Signer() = default;
  virtual bool Ready() const = 0;
  virtual std::optional<std::vector<std::uint8_t>> Sign(std::string_view input) = 0;
  virtual bool Verify(std::string_view input,
                      const std::vector<std::uint8_t>& signature) const = 0;
};

struct ExistingToken {
  bool exists{false};
  bool regular{false};
  bool root_owned{false};
  unsigned mode{0};
  std::string bytes;
};

class Store {
 public:
  virtual ~Store() = default;
  virtual std::optional<ExistingToken> Read() = 0;
  virtual bool ReplaceAtomically(std::string_view bytes) = 0;
};

enum class Result { kReused, kCreated, kRejected, kUnavailable };

std::string Payload(std::int64_t issued_at);
std::optional<std::string> CreateToken(std::int64_t issued_at, Signer& signer);
bool ValidateToken(std::string_view token, std::int64_t now, const Signer& signer);
Result Prepare(std::int64_t now, Signer& signer, Store& store);

class FixedStore final : public Store {
 public:
  FixedStore();
  ~FixedStore() override;
  FixedStore(const FixedStore&) = delete;
  FixedStore& operator=(const FixedStore&) = delete;
  std::optional<ExistingToken> Read() override;
  bool ReplaceAtomically(std::string_view bytes) override;

 private:
  int directory_fd_{-1};
};

}  // namespace aos::kac::provider
