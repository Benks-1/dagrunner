import unittest
import tempfile
import os
from pathlib import Path
import dagrunner
from datetime import datetime

class TestIgnoreDepsFlag(unittest.TestCase):
    def test_ignore_deps_allows_dependent_to_run(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            mod_file = td_path / "mymod2.py"
            mod_file.write_text(
                "def fail():\n    raise RuntimeError('boom')\n\ndef ok(x):\n    print('ok got', x)\n    return x\n"
            )
            job = {
                "id": "j2",
                "tasks": [
                    {"id": "t1", "type": "function", "path": "mymod2.fail"},
                    {"id": "t2", "type": "function", "path": "mymod2.ok", "args": ["${outputs.t1.return_value}"], "depends_on": ["t1"]},
                ]
            }
            cur = Path.cwd()
            os.chdir(td)
            try:
                interp = dagrunner._ensure_real_python(None, Path.cwd())
                timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
                # Run with ignore_deps=True — dependent should still be executed
                dagrunner.run_job("j2", job, interp, timestamp, dry_run=False, ignore_deps=True)
                logs = list(dagrunner.LOG_DIR.glob(f"dagrunner_*_j2.log"))
                self.assertTrue(logs)
                txt = sorted(logs)[-1].read_text()
                self.assertIn("Task t1", txt)
                self.assertIn("Status: failed", txt)
                self.assertIn("Task t2", txt)
                # Because we ignored dependencies, t2 should attempt to run — look for Status: done or failed but not 'skipped'
                self.assertNotIn("Status: skipped", txt)
            finally:
                os.chdir(cur)

if __name__ == "__main__":
    unittest.main()
