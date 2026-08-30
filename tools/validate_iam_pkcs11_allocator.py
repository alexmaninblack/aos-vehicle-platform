#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Validate the bounded Aos IAM PKCS#11 session-cache closure."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
IAM_APPEND = (
    ROOT
    / "meta-aos-vehicle-platform/recipes-aos/aos-iamanager/"
    "aos-iamanager_git.bbappend"
)
IAM_TRANSFORM = (
    ROOT
    / "meta-aos-vehicle-platform/recipes-aos/aos-iamanager/files/"
    "aos-kuksa-iam-configure.py"
)
SESSION_POOL_MACRO = "AOS_CONFIG_PKCS11_SESSION_POOL_MAX_SIZE"
SESSIONS_PER_LIB_MACRO = "AOS_CONFIG_PKCS11_SESSIONS_PER_LIB"
SESSION_POOL_MAX_SIZE = 3
SESSIONS_PER_LIB = 4
SESSION_CONTEXT_BYTES = 64
FLAGS = "CKF_RW_SESSION | CKF_SERIAL_SESSION"
SOFTHSM_LIBRARY = "/usr/lib/softhsm/libsofthsm2.so"

# The first six entries are the pinned native v9.1 iam.cfg contract.  The
# seventh entry is loaded from the tracked transformer below so the validator
# cannot silently diverge from the image configuration it is protecting.
NATIVE_CERT_MODULES = (
    ("online", SOFTHSM_LIBRARY, "aoscloud"),
    ("offline", SOFTHSM_LIBRARY, "aoscloud"),
    ("iam", SOFTHSM_LIBRARY, "aoscore"),
    ("sm", SOFTHSM_LIBRARY, "aoscore"),
    ("cm", SOFTHSM_LIBRARY, "aoscore"),
    ("diskencryption", SOFTHSM_LIBRARY, "aoscore"),
)


class ValidationError(RuntimeError):
    """Raised when the accepted three-key allocator closure is widened."""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_kuksa_module() -> dict[str, object]:
    spec = importlib.util.spec_from_file_location("iam_transform", IAM_TRANSFORM)
    if spec is None or spec.loader is None:
        raise ValidationError("cannot load the tracked IAM transformer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MODULE


def effective_session_keys() -> tuple[tuple[str, str, str], ...]:
    kuksa = _load_kuksa_module()
    params = kuksa.get("params")
    if not isinstance(params, dict):
        raise ValidationError("KUKSA IAM module params are missing")
    modules = (*NATIVE_CERT_MODULES, (
        str(kuksa.get("id")),
        str(params.get("library")),
        str(params.get("tokenLabel")),
    ))
    keys = {(library, label, FLAGS) for _, library, label in modules}
    return tuple(sorted(keys))


def _macro_occurrences() -> dict[str, list[Path]]:
    result = {SESSION_POOL_MACRO: [], SESSIONS_PER_LIB_MACRO: []}
    metadata_suffixes = {".bb", ".bbappend", ".bbclass", ".conf", ".inc"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in metadata_suffixes:
            continue
        text = _read(path)
        for macro in result:
            if macro in text:
                result[macro].append(path)
    return result


def validate_recipe_scope() -> None:
    text = _read(IAM_APPEND)
    exact = (
        'CXXFLAGS:append = " '
        f'-D{SESSION_POOL_MACRO}={SESSION_POOL_MAX_SIZE} '
        f'-D{SESSIONS_PER_LIB_MACRO}={SESSIONS_PER_LIB}"'
    )
    if text.count(exact) != 1:
        raise ValidationError("IAM allocator override must occur exactly once")
    occurrences = _macro_occurrences()
    for macro, paths in occurrences.items():
        if paths != [IAM_APPEND]:
            rendered = ", ".join(str(path.relative_to(ROOT)) for path in paths)
            raise ValidationError(
                f"{macro} must be recipe-scoped to aos-iamanager, found: {rendered}"
            )


def validate_topology() -> None:
    keys = effective_session_keys()
    expected = (
        (SOFTHSM_LIBRARY, "aos-kuksa", FLAGS),
        (SOFTHSM_LIBRARY, "aoscloud", FLAGS),
        (SOFTHSM_LIBRARY, "aoscore", FLAGS),
    )
    if keys != expected:
        raise ValidationError(f"expected exact three session keys, got {keys!r}")
    if SESSION_POOL_MAX_SIZE < len(keys):
        raise ValidationError("session cache cannot retain every accepted key")
    if SESSIONS_PER_LIB < SESSION_POOL_MAX_SIZE + 1:
        raise ValidationError("allocator must preserve cache-plus-one headroom")
    if SESSION_POOL_MAX_SIZE != len(keys) or SESSIONS_PER_LIB != len(keys) + 1:
        raise ValidationError("allocator closure must remain exact, not merely sufficient")


def validate_pinned_source(source_root: Path) -> None:
    source_root = source_root.resolve()
    config = source_root / "src/core/common/config.hpp"
    pkcs11 = source_root / "src/core/common/pkcs11/pkcs11.cpp"
    certloader = source_root / "src/core/common/crypto/certloader.cpp"
    certmodule = (
        source_root
        / "src/core/iam/certhandler/certmodules/pkcs11/pkcs11.cpp"
    )
    for path in (config, pkcs11, certloader, certmodule):
        if not path.is_file():
            raise ValidationError(f"pinned source file is missing: {path}")

    config_text = _read(config)
    for macro, upstream_default in (
        (SESSIONS_PER_LIB_MACRO, 3),
        (SESSION_POOL_MACRO, 2),
    ):
        guarded = rf"#ifndef\s+{macro}\s+#define\s+{macro}\s+{upstream_default}\b"
        if re.search(guarded, config_text) is None:
            raise ValidationError(f"pinned guarded default changed for {macro}")

    pkcs11_text = _read(pkcs11)
    open_start = pkcs11_text.find("LibraryContext::OpenSession(")
    open_end = pkcs11_text.find("void LibraryContext::ClearSessions()", open_start)
    low_level_start = pkcs11_text.find("LibraryContext::PKCS11OpenSession(")
    low_level_end = pkcs11_text.find(
        "/***********************************************************************************************************************",
        low_level_start,
    )
    if min(open_start, open_end, low_level_start, low_level_end) < 0:
        raise ValidationError("pinned PKCS#11 session functions are missing")
    open_body = pkcs11_text[open_start:open_end]
    low_level_body = pkcs11_text[low_level_start:low_level_end]
    allocate_at = open_body.find("PKCS11OpenSession(slotID, flags)")
    push_at = open_body.find("mSessions.PushBack")
    replace_at = open_body.find("mSessions[mLRUInd] =")
    if (
        allocate_at < 0
        or push_at < 0
        or replace_at < 0
        or allocate_at >= push_at
        or allocate_at >= replace_at
    ):
        raise ValidationError(
            "pinned OpenSession no longer allocates before cache insertion/replacement"
        )
    if "MakeShared<SessionContext>(&mAllocator" not in low_level_body:
        raise ValidationError("pinned low-level session allocation changed")

    # CertLoader names its slot argument `slotID`; the cert module uses
    # `mSlotID`.  There must be exactly one low-level production call in each
    # file and no alternative flags at either boundary.
    callers = (
        (_read(certloader), "library", "slotID"),
        (_read(certmodule), "mPKCS11", "mSlotID"),
    )
    for text, receiver, slot in callers:
        exact_call = f"{receiver}->OpenSession({slot}, {FLAGS});"
        calls = re.findall(rf"{re.escape(receiver)}->OpenSession\([^;]+\);", text)
        if calls != [exact_call]:
            raise ValidationError(
                f"production PKCS#11 flags changed: expected {exact_call!r}, got {calls!r}"
            )


def replay_access_order(cache_capacity: int, allocator_capacity: int) -> int:
    """Replay the pinned sequence and return peak live SessionContexts.

    Native self-signed certificate modules retain their session.  KUKSA
    SetOwner clears the cache, but the diskencryption module still owns its
    aoscore session.  OpenSession allocates before cache insertion, so the IAM
    cache miss temporarily needs a fourth context even though only three keys
    are accepted.  The accepted cache holds all three keys and therefore never
    invokes LRU replacement.
    """

    if cache_capacity < 1 or allocator_capacity < 1:
        raise ValueError("capacities must be positive")
    cache: list[str] = []
    retained: list[str] = []
    allocated = 0
    high_water = 0

    def allocate(key: str, *, retain: bool = False) -> None:
        nonlocal allocated, high_water
        if key in cache:
            if retain and key not in retained:
                retained.append(key)
            return
        allocated += 1
        high_water = max(high_water, allocated)
        if allocated > allocator_capacity:
            raise MemoryError("SessionContext static allocator exhausted")
        if len(cache) >= cache_capacity:
            raise AssertionError("accepted access order must not invoke LRU")
        cache.append(key)
        if retain:
            retained.append(key)

    allocate("aoscore", retain=True)  # diskencryption self-signed
    cache.clear()  # KUKSA SetOwner calls the pinned global ClearSessions
    allocate("aos-kuksa", retain=True)  # KUKSA self-signed
    allocate("aoscloud")  # online CreateKey
    allocate("aoscloud")  # offline CreateKey reuses the same tuple
    allocate("aoscore")  # IAM miss while the old retained context is live
    allocate("aoscore")  # SM, CM and CertLoader reuse the cached tuple
    return high_water


def validate_access_order() -> None:
    try:
        replay_access_order(cache_capacity=2, allocator_capacity=3)
    except MemoryError:
        pass
    else:
        raise ValidationError("upstream 2/3 defaults did not reproduce exhaustion")
    high_water = replay_access_order(
        cache_capacity=SESSION_POOL_MAX_SIZE,
        allocator_capacity=SESSIONS_PER_LIB,
    )
    if high_water != SESSIONS_PER_LIB:
        raise ValidationError(f"unexpected SessionContext high-water: {high_water}")
    if high_water * SESSION_CONTEXT_BYTES != 256:
        raise ValidationError("accepted static SessionContext allocation is not 256 bytes")


def validate(source_root: Path | None = None) -> None:
    validate_recipe_scope()
    validate_topology()
    validate_access_order()
    if source_root is not None:
        validate_pinned_source(source_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        help="pinned aos_core_lib_cpp root for production-source assertions",
    )
    args = parser.parse_args()
    try:
        validate(args.source_root)
    except (OSError, ValidationError, ValueError) as error:
        print(f"IAM PKCS11 allocator validation failed: {error}")
        return 1
    print("IAM PKCS11 allocator validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
