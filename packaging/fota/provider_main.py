# SPDX-FileCopyrightText: 2026 maninblack
# SPDX-License-Identifier: Apache-2.0

"""Start the provider from its immutable component-local Python tree."""

from __future__ import annotations

import sys
from pathlib import Path


PYTHON_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PYTHON_ROOT / "site-packages"))
sys.path.insert(0, str(PYTHON_ROOT))

from carla_viss_kuksa_provider.runtime import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
