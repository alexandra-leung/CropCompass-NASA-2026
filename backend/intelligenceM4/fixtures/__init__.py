"""
Real M1/M2 response fixtures for M4 tests.

Every fixture is produced by build_fixtures.py through M4's own providers
(the same service-layer calls M4 uses at runtime) and serialised exactly as
the M1/M2 HTTP API would return it. manifest.json records the call, inputs
and generation time for each file. No fixture is hand-written or edited.
"""

import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent


def load_fixture(name: str) -> Any:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest() -> dict[str, Any]:
    return load_fixture("manifest.json")
