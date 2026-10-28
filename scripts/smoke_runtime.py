"""Run one short CPU task per released baseline; timeouts are valid outcomes."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def main():
    out = ROOT / "outputs" / "runtime_smoke"
    if out.exists():
        raise SystemExit("Smoke output exists; choose a fresh checkout for this test")
    plan_path = ROOT / "outputs" / "smoke_plan.json"
    subprocess.check_call([sys.executable, str(ROOT / "scripts/build_job_plan.py"),
                           "--device", "cpu", "-o", str(plan_path)])
    plan = json.loads(plan_path.read_text())
    iid = plan["jobs"][0]["instance_id"]
    plan["jobs"] = [j for j in plan["jobs"] if j["instance_id"] == iid and j["seed"] == 0]
    plan.update(n_jobs=len(plan["jobs"]), n_units=1, seeds=[0], max_days=1,
                task_seconds=3.0, slot_seconds=3.0, phase="public_runtime_development_smoke")
    plan_path.write_text(json.dumps(plan, indent=2))
    subprocess.check_call([sys.executable, "-m", "dmp4p_runtime.batch", "--plan",
                           str(plan_path), "--out", str(out)], cwd=ROOT)
    summary = json.loads((out / "summary.json").read_text())
    assert summary["completed"] == 10 and summary["program_errors"] == 0, summary
    print("Runtime smoke passed; this is an execution check, not an algorithm comparison.")

if __name__ == "__main__":
    main()
