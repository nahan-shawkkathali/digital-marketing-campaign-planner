"""Read-only checks of existing records and before/after file hashes."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
baseline = json.loads((OUT / "baseline-hashes.json").read_text(encoding="utf-8-sig"))
hash_checks = []
for entry in baseline:
    path = Path(entry["Path"])
    current = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    hash_checks.append({"file": str(path.relative_to(ROOT)), "unchanged": current == entry["Hash"]})
assert all(item["unchanged"] for item in hash_checks), hash_checks
original_media = {Path(entry["Path"]) for entry in baseline if Path(entry["Path"]).is_relative_to(ROOT / "media")}
assert set(path for path in (ROOT / "media").rglob("*") if path.is_file()) == original_media

connection = sqlite3.connect((ROOT / "db.sqlite3").as_uri() + "?mode=ro", uri=True)
connection.execute("PRAGMA query_only=ON")
integrity = connection.execute("PRAGMA integrity_check").fetchall()
foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
assert integrity == [("ok",)] and foreign_keys == []
counts = {name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in
          ("auth_user", "campaigns_employeeprofile", "campaigns_campaign", "campaigns_task", "campaigns_deliverable")}
columns = {row[1]: row[2] for row in connection.execute("PRAGMA table_info(campaigns_campaign)")}
assert columns["platforms"] == "varchar(255)" and columns["campaign_goal"] == "TEXT"
applied = connection.execute("SELECT name FROM django_migrations WHERE app='campaigns' ORDER BY name").fetchall()
assert len(applied) == 7 and applied[-1][0] == "0007_campaign_campaign_goal_campaign_platforms"
invalid_campaigns = connection.execute("""SELECT COUNT(*) FROM campaigns_campaign WHERE
    progress_percentage < 0 OR progress_percentage > 100 OR
    (status = 'completed' AND progress_percentage != 100) OR
    (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date > end_date) OR budget < 0""").fetchone()[0]
stale_tasks = connection.execute("""SELECT COUNT(*) FROM campaigns_task t JOIN campaigns_campaign c ON t.campaign_id=c.id
    WHERE t.assigned_employee_id IS NOT c.assigned_employee_id""").fetchone()[0]
assert invalid_campaigns == stale_tasks == 0
files = connection.execute("SELECT uploaded_file FROM campaigns_deliverable").fetchall()
assert all((ROOT / "media" / path).is_file() for (path,) in files)
connection.close()
raw_log = (OUT / "complete-tests.txt").read_bytes()
log = raw_log.decode("utf-16" if raw_log.startswith((b'\xff\xfe', b'\xfe\xff')) else "utf-8-sig")
total, duration = re.search(r"Ran (\d+) tests in ([\d.]+)s", log).groups()
passed = len(re.findall(r"\.\.\.\s+ok\b", log))
assert int(total) == passed == 169 and re.search(r"(?m)^OK\s*$", log)
result = {"result": "PASS", "file_hashes": hash_checks, "existing_counts": counts,
          "sqlite_integrity": "ok", "foreign_key_violations": 0, "invalid_campaigns": invalid_campaigns,
          "stale_task_assignments": stale_tasks, "existing_deliverable_files_present": len(files),
          "campaign_columns": {name: columns[name] for name in ("platforms", "campaign_goal")},
          "campaign_migrations": [row[0] for row in applied],
          "complete_tests": {"total": int(total), "passed": passed, "failed": 0, "errors": 0, "skipped": 0, "seconds": float(duration)}}
(OUT / "preservation-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
