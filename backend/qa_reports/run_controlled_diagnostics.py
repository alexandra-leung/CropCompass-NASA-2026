"""Replay the recovery audit only in isolated temporary backend copies."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path
source = Path(__file__).resolve().parents[1]
def hashes():
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (source / "data").rglob("*") if p.is_file()}
before = hashes()
root = Path(tempfile.mkdtemp(prefix="cropcompass-repair-probes-")) / "backend"
shutil.copytree(source, root, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "qa_reports"))
shutil.copy2(source / "qa_reports/CODEX_BRANCH_RECOVERY_REPRODUCE.py", root / "audit_probe.py")
result = subprocess.run([sys.executable, "audit_probe.py"], cwd=root, capture_output=True, text=True)
print(result.stdout, result.stderr)
result.check_returncode()
raw = json.loads((root / "audit-workflow.json").read_text())
summary = {"isolated_backend": str(root), "statuses": {k:v["status"] for k,v in raw.items() if isinstance(v,dict) and "status" in v}, "missing_inputs_probe":raw["missing_inputs_probe"], "m5_exact_pass_through":raw.get("m5_exact_pass_through")}
stress = raw["stress_qa_cached"]["body"]
summary["stress_score_comparability"] = [{"scenario":r["scenario_id"], "changes":[{"rotation_id":c["rotation_id"], "score_comparable":c["score_comparable"], "score_change":c["score_change"]} for c in r["changes"]]} for r in stress.get("differences_vs_baseline",[])]
rescue = raw.get("rescue_qa_cached",{}).get("body",{})
summary["rescue_sequences"] = [{"sequence":r["rotation_sequence"], "status":r["sequence_status"]} for r in rescue.get("candidates",[])]
code = """
import json
from agricultureM2.plan_engine import monthly_climate
raw=json.load(open('audit-workflow.json'))
seasonal=raw['history_cached']['body']['seasonal']
rows=monthly_climate(seasonal)
json.dump({'january_rain_mm': rows[0]['rain_mm'], 'excluded_periods':[r['period'] for r in seasonal if r.get('completenessStatus') != 'complete' or r.get('completenessPct',0)<100]},open('seasonal_probe.json','w'))
"""
subprocess.run([sys.executable, "-c", code], cwd=root, check=True)
summary["seasonal_probe"] = json.loads((root / "seasonal_probe.json").read_text())
summary["original_data_hashes_unchanged"] = before == hashes()
assert summary["original_data_hashes_unchanged"]
(source / "qa_reports/CODEX_CONTROLLED_REPAIR_PROBES.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
