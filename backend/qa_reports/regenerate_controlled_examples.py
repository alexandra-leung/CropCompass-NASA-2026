"""Regenerate only M4 examples from running endpoints in an isolated backend."""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path
source = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix="cropcompass-m4-examples-")) / "backend"
shutil.copytree(source, root, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "qa_reports"))
code = """
import asyncio, json
from pathlib import Path
import httpx
import climateM1.services.cache as cache
cache.CACHE_TTL_SECONDS = 10**12
async def blocked(*args, **kwargs):
    raise httpx.ConnectError('controlled fixture regeneration: network blocked')
httpx.AsyncClient.send = blocked
from intelligenceM4.fixtures.build_fixtures import main
asyncio.run(main(example_only=True))
"""
subprocess.run([sys.executable, "-c", code], cwd=root, check=True)
fixtures = Path("intelligenceM4/fixtures")
for name in ("example_evidence_response.json", "example_blind_spots_response.json", "example_assistant_response.json", "example_analyze_response.json", "manifest.json"):
    shutil.copy2(root / fixtures / name, source / fixtures / name)
print("ISOLATED_BACKEND=" + str(root))
