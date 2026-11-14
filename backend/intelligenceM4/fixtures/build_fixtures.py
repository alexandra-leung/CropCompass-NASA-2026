"""
Regenerate M4 test fixtures from REAL M1/M2 outputs.

Run from backend/:
    python -m intelligenceM4.fixtures.build_fixtures

Each fixture is fetched through M4's providers and serialised with
`model_dump(by_alias=True, mode="json")`, i.e. the same JSON the M1/M2 HTTP
endpoints return. A provider that is not "ok"/"partial" is skipped (and
reported) — no fixture is ever filled in by hand.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from intelligenceM4.providers import agriculture_provider, climate_provider

FIXTURE_DIR = Path(__file__).resolve().parent
LOCATION_ID = "pamplemousses-04"

# Inputs below are test requests, not recommendations.
M2_CASES = [
    ("m2_rotation__maize-cowpea-cabbage.json",
     lambda: agriculture_provider.evaluate_rotation(["maize", "cowpea", "cabbage"]),
     {"crop_ids": ["maize", "cowpea", "cabbage"]}),
    ("m2_rotation__maize-maize-maize.json",
     lambda: agriculture_provider.evaluate_rotation(["maize", "maize", "maize"]),
     {"crop_ids": ["maize", "maize", "maize"]}),
    ("m2_generate__maize-maize-maize__max3.json",
     lambda: agriculture_provider.generate_alternatives(["maize", "maize", "maize"], 3),
     {"current_rotation": ["maize", "maize", "maize"], "max_alternatives": 3}),
    ("m2_suitability__cowpea__no-inputs.json",
     lambda: agriculture_provider.check_suitability("cowpea"),
     {"crop_id": "cowpea", "temperature_c": None, "soil_ph": None}),
    ("m2_suitability__cowpea__temp25-ph6.5.json",
     lambda: agriculture_provider.check_suitability("cowpea", 25.0, 6.5),
     {"crop_id": "cowpea", "temperature_c": 25.0, "soil_ph": 6.5,
      "note": "temperature/pH are test inputs, not observed farm values"}),
]


def _write(name: str, result, inputs: dict, manifest: dict) -> None:
    if not result.usable:
        print(f"SKIP {name}: {result.module} {result.status} — {result.error}")
        return
    payload = result.data.model_dump(by_alias=True, mode="json")
    with (FIXTURE_DIR / name).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    manifest[name] = {
        "module": result.module,
        "called": result.called,
        "inputs": inputs,
        "provider_status": result.status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"OK   {name}: {result.module} {result.status}")


async def main() -> None:
    manifest_path = FIXTURE_DIR / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists() else {}
    )

    _write(
        f"m1_scenarios__{LOCATION_ID}.json",
        await climate_provider.get_scenarios(LOCATION_ID),
        {"location_id": LOCATION_ID}, manifest,
    )
    _write(
        f"m1_history__{LOCATION_ID}.json",
        await climate_provider.get_history(LOCATION_ID),
        {"location_id": LOCATION_ID,
         "start": climate_provider.HISTORY_DEFAULT_START.isoformat(),
         "end": climate_provider.HISTORY_DEFAULT_END.isoformat()},
        manifest,
    )
    for name, call, inputs in M2_CASES:
        _write(name, call(), inputs, manifest)

    manifest_path.write_text(
        json.dumps(dict(sorted(manifest.items())), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())
