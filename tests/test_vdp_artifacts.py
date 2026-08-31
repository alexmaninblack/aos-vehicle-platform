# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import gzip
import io
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
FOTA = ROOT / "packaging/fota"
sys.path.insert(0, str(FOTA))

import vdp_artifact  # noqa: E402


def fake_packages(_wheels: list[Path]) -> list[dict[str, object]]:
    return [
        {
            "SPDXID": f"SPDXRef-Package-{index}",
            "checksums": [{"algorithm": "SHA256", "checksumValue": str(index) * 64}],
            "copyrightText": "NOASSERTION",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "Apache-2.0",
            "licenseDeclared": "Apache-2.0",
            "name": name,
            "versionInfo": "test",
        }
        for index, name in enumerate(
            ("grpcio", "kuksa-client", "protobuf", "typing-extensions", "websockets"),
            start=1,
        )
    ]


class VdpArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(dir="/tmp")
        cls.root = Path(cls.temporary.name)
        cls.wheelhouse = cls.root / "wheelhouse"
        cls.wheelhouse.mkdir()
        members = {
            "grpcio-1.75.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.whl": [
                "grpcio-1.75.0.dist-info/METADATA",
                "grpc/_cython/_credentials/roots.pem",
            ],
            "kuksa_client-0.5.0-py3-none-any.whl": ["kuksa_client-0.5.0.dist-info/METADATA"],
            "protobuf-5.29.6-cp38-abi3-manylinux2014_aarch64.whl": ["protobuf-5.29.6.dist-info/METADATA"],
            "typing_extensions-4.15.0-py3-none-any.whl": ["typing_extensions-4.15.0.dist-info/METADATA"],
            "websockets-15.0.1-cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64.whl": [
                "websockets-15.0.1.dist-info/METADATA"
            ],
        }
        cls.wheels = []
        for name, names in members.items():
            wheel = cls.wheelhouse / name
            with zipfile.ZipFile(wheel, "w") as archive:
                for member_name in names:
                    info = zipfile.ZipInfo(member_name)
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, b"test fixture\n")
            cls.wheels.append(wheel)
        cls.outputs: dict[str, tuple[Path, Path]] = {}
        with mock.patch.object(
            vdp_artifact, "verify_entry_gate", return_value=sorted(cls.wheels)
        ), mock.patch.object(vdp_artifact, "_runtime_packages", side_effect=fake_packages):
            for version in vdp_artifact.vdp_family.VERSIONS:
                first = cls.root / f"{version}-first"
                second = cls.root / f"{version}-second"
                vdp_artifact.build(first, version, cls.wheelhouse)
                vdp_artifact.build(second, version, cls.wheelhouse)
                cls.outputs[version] = first, second

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_all_three_candidates_are_byte_identical_across_fresh_builds(self) -> None:
        manifests = {}
        for version, (first, second) in self.outputs.items():
            for name in (
                vdp_artifact.prepared_filename(version),
                vdp_artifact.layer_name(version),
                vdp_artifact.manifest_filename(version),
                "candidate.json",
            ):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            manifest_path = first / vdp_artifact.manifest_filename(version)
            manifests[version] = vdp_artifact.validate(first, version, manifest_path)
        vdp_artifact.validate_family(manifests)

    def test_prepared_names_and_manifest_are_exact_and_canonical(self) -> None:
        for version, (first, _) in self.outputs.items():
            manifest_path = first / vdp_artifact.manifest_filename(version)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest_path.read_bytes(), vdp_artifact.canonical_json(manifest))
            self.assertEqual(manifest["candidateId"], f"aosedge-vdp-component-{version}")
            self.assertEqual(
                manifest["preparedArtifact"]["fileName"],
                f"aosedge-vdp-component-{version}-linux-arm64.unsigned.tar.gz",
            )
            self.assertNotIn("manifestSha256", manifest)
            self.assertEqual(manifest["source"]["revision"], vdp_artifact.PRODUCT_SOURCE_REVISION)
            self.assertEqual(manifest["compatibility"]["factoryImageVersion"], "6.1.1-maninblack.21")

    def test_artifact_contains_only_the_build_selected_release(self) -> None:
        for version, (first, _) in self.outputs.items():
            artifact = first / vdp_artifact.prepared_filename(version)
            with gzip.open(artifact, "rb") as compressed:
                with tarfile.open(fileobj=io.BytesIO(compressed.read()), mode="r:") as envelope:
                    layer = envelope.extractfile(vdp_artifact.layer_path(version)).read()
            with tarfile.open(fileobj=io.BytesIO(layer), mode="r:") as payload:
                names = set(payload.getnames())
            release_modules = {
                name for name in names
                if name.startswith("python/carla_viss_kuksa_provider/releases/v")
            }
            self.assertEqual(
                release_modules,
                {"python/carla_viss_kuksa_provider/releases/" + vdp_artifact.vdp_family.PROFILE_MODULE[version]},
            )
            self.assertEqual(
                "python/carla_viss_kuksa_provider/advisory.py" in names,
                version == "3.0.0",
            )
            self.assertNotIn("prebuild.json", names)
            self.assertNotIn("grpc/_cython/_credentials/roots.pem", names)

    def test_embedded_dependency_lock_is_bound_in_provenance(self) -> None:
        expected = (FOTA / "requirements-arm64.txt").read_bytes()
        for version, (first, _) in self.outputs.items():
            members = vdp_artifact._member_map(first / vdp_artifact.layer_name(version))
            embedded = members["dependency-lock/requirements-arm64.txt"][1]
            self.assertEqual(embedded, expected)
            provenance = json.loads(members["provenance/provenance.json"][1])
            records = [
                record
                for record in provenance["buildInputs"]
                if record["path"]
                == "payload/dependency-lock/requirements-arm64.txt"
            ]
            self.assertEqual(
                records,
                [
                    {
                        "byteLength": len(expected),
                        "path": "payload/dependency-lock/requirements-arm64.txt",
                        "sha256": vdp_artifact.sha256_bytes(expected),
                    }
                ],
            )

    def test_stage_requires_exact_version_controlled_manifest_bytes(self) -> None:
        version = "1.0.0"
        first, _ = self.outputs[version]
        canonical_root = self.root / "canonical"
        canonical_root.mkdir()
        canonical = canonical_root / vdp_artifact.manifest_filename(version)
        manifest = first / vdp_artifact.manifest_filename(version)
        canonical.write_bytes(manifest.read_bytes())
        content_store = self.root / "content-store"
        with mock.patch.object(
            vdp_artifact, "CANONICAL_MANIFEST_ROOT", canonical_root
        ), mock.patch.object(vdp_artifact, "CONTENT_STORE_ROOT", content_store):
            staged = vdp_artifact.stage(first, version, manifest)
            self.assertEqual(
                (staged / canonical.name).read_bytes(), canonical.read_bytes()
            )
            canonical.write_bytes(
                self.outputs["2.0.0"][0]
                .joinpath(vdp_artifact.manifest_filename("2.0.0"))
                .read_bytes()
            )
            with self.assertRaisesRegex(
                vdp_artifact.ArtifactError, "version-controlled canonical"
            ):
                vdp_artifact.stage(first, version, manifest)

    def test_tampered_prepared_bytes_fail_manifest_binding(self) -> None:
        original, _ = self.outputs["1.0.0"]
        copy = self.root / "tampered"
        shutil.copytree(original, copy)
        artifact = copy / vdp_artifact.prepared_filename("1.0.0")
        artifact.write_bytes(artifact.read_bytes() + b"tamper")
        with self.assertRaisesRegex(vdp_artifact.ArtifactError, "compression|manifest"):
            vdp_artifact.validate(
                copy, "1.0.0", copy / vdp_artifact.manifest_filename("1.0.0")
            )

    def test_secret_certificate_and_non_arm64_payloads_fail_closed(self) -> None:
        member = tarfile.TarInfo("credential.pem")
        member.uid = member.gid = member.mtime = 0
        member.mode = 0o644
        member.type = tarfile.REGTYPE
        with self.assertRaisesRegex(vdp_artifact.ArtifactError, "credential"):
            vdp_artifact._validate_archive_metadata(
                {"credential.pem": (member, b"-----BEGIN CERTIFICATE-----")}
            )
        elf = tarfile.TarInfo("python/site-packages/native.so")
        elf.uid = elf.gid = elf.mtime = 0
        elf.mode = 0o644
        elf.type = tarfile.REGTYPE
        header = bytearray(20)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = (62).to_bytes(2, "little")
        with self.assertRaisesRegex(vdp_artifact.ArtifactError, "AArch64"):
            vdp_artifact._validate_archive_metadata(
                {"python/site-packages/native.so": (elf, bytes(header))}
            )

    def test_offline_guard_and_exact_wheel_allowlist_fail_closed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(vdp_artifact.ArtifactError, "offline"):
                vdp_artifact.verify_entry_gate(self.root / "output", self.wheelhouse)
        with self.assertRaisesRegex(vdp_artifact.ArtifactError, "digest"):
            vdp_artifact.validate_wheelhouse(self.wheelhouse)

    def test_family_validator_rejects_non_strict_release_capabilities(self) -> None:
        manifests = {
            version: json.loads(
                (first / vdp_artifact.manifest_filename(version)).read_text(encoding="utf-8")
            )
            for version, (first, _) in self.outputs.items()
        }
        manifests["2.0.0"]["functionalOutputs"]["kuksaPublishedPaths"] = list(
            manifests["1.0.0"]["functionalOutputs"]["kuksaPublishedPaths"]
        )
        with self.assertRaisesRegex(vdp_artifact.ArtifactError, "strict"):
            vdp_artifact.validate_family(manifests)

    def test_version_controlled_producer_manifests_are_canonical_and_complete(self) -> None:
        manifests = {}
        for version in vdp_artifact.vdp_family.VERSIONS:
            path = (
                ROOT / "manifests/release-candidates"
                / vdp_artifact.manifest_filename(version)
            )
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.read_bytes(), vdp_artifact.canonical_json(manifest))
            self.assertEqual(manifest["semanticVersion"], version)
            self.assertEqual(manifest["signingState"], "UNSIGNED")
            self.assertNotIn("manifestSha256", manifest)
            manifests[version] = manifest
        vdp_artifact.validate_family(manifests)


if __name__ == "__main__":
    unittest.main()
