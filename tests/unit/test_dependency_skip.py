import unittest
import tempfile
import os
from pathlib import Path
import dagrunner
from datetime import datetime

class TestDependencySkip(unittest.TestCase):
    def test_failed_task_skips_dependent(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # create a small module with a failing and a succeeding function
            mod_file = td_path / "mymod.py"
            mod_file.write_text(
                "def fail():\n    raise RuntimeError('boom')\n\ndef ok():\n    return {'msg':'ok'}\n"
            )
            # build job
            job = {
                "id": "j1",
                "tasks": [
                    {"id": "t1", "type": "function", "path": "mymod.fail"},
                    {"id": "t2", "type": "function", "path": "mymod.ok", "depends_on": ["t1"]},
                ]
            }
            # chdir into td so subprocess-imports see mymod
            cur = Path.cwd()
            os.chdir(td)
            try:
                interp = dagrunner._ensure_real_python(None, Path.cwd())
                timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
                dagrunner.run_job("j1", job, interp, timestamp, dry_run=False, ignore_deps=False)
                # find log in global LOG_DIR
                logs = list(dagrunner.LOG_DIR.glob(f"dagrunner_*_j1.log"))
                self.assertTrue(logs, "Expected a log file for job j1")
                latest = sorted(logs)[-1]
                text = latest.read_text()
                self.assertIn("Task t1", text)
                self.assertIn("Status: failed", text)
                self.assertIn("Task t2", text)
                self.assertIn("Status: skipped", text)
            finally:
                os.chdir(cur)

if __name__ == "__main__":
    unittest.main()
