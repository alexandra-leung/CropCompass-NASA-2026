"""Run checks in a new backend copy; never write source caches."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path
source = Path(__file__).resolve().parents[1]
protected = list((source / "data").rglob("*"))
def hashes():
    return {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()}
before = hashes()
root = Path(tempfile.mkdtemp(prefix="cropcompass-repair-"))
copy = root / "backend"
shutil.copytree(source, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "qa_reports"))
args = sys.argv[1:] or ["tests"]
result = subprocess.run([sys.executable, "-m", "pytest", "-q", *args, "-ra", "--basetemp=" + str(root / "pytest")], cwd=copy, capture_output=True, text=True)
print(result.stdout, result.stderr)
print("ISOLATED_BACKEND=" + str(copy))
assert before == hashes(), "Original evidence changed"
(source / "qa_reports" / "CONTROLLED_LATEST_TESTS.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
sys.exit(result.returncode)
