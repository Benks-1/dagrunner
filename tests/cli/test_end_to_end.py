import unittest
import subprocess
import sys
import time
from pathlib import Path
import dagrunner

class TestCLIEndToEnd(unittest.TestCase):
    def test_run_test_job_creates_log_and_contains_returns(self):
        # Run dagrunner CLI for the provided test_job
        p = subprocess.run([sys.executable, "-m", "dagrunner", "run", "-j", "test_job"], capture_output=True, text=True)
        # Allow a moment for processes to finish and logs to be written
        time.sleep(1)
        # find newest log for test_job
        logs = list(Path(dagrunner.LOG_DIR).glob("dagrunner_*_test_job.log"))
        self.assertTrue(logs, "No test_job logs found")
        latest = sorted(logs)[-1]
        txt = latest.read_text()
        # Basic assertions
        self.assertIn("shell_hello", txt)
        self.assertIn("script_hello", txt)
        self.assertIn("func_plain", txt)
        # function return values should be present
        self.assertIn("RETURN VALUE", txt)

if __name__ == "__main__":
    unittest.main()
