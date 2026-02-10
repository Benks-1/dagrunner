import unittest
import subprocess
import sys
import time
from pathlib import Path
import dagrunner
from tests.tools.compare_log import latest_log_for, contains_in_order

class TestPlaceholderUsage(unittest.TestCase):
    def test_placeholder_used_in_function_and_shell(self):
        # Run the job which includes tasks that use placeholders
        p = subprocess.run([sys.executable, "-m", "dagrunner", "run", "-j", "test_job"], capture_output=True, text=True)
        time.sleep(1)
        log = latest_log_for("test_job", Path(dagrunner.LOG_DIR))
        self.assertIsNotNone(log, "Expected a log file for test_job")
        txt = log.read_text()
        # The consume function should have been called with the value from func_with_args (40+2=42), and returned doubled (84)
        self.assertIn("[mypkg.entry.consume] got value", txt)
        # Shell consumer should echo the value (stringified)
        self.assertIn("[shell] consumed=42", txt)
        # Ensure order: func_with_args then use_in_function then use_in_shell
        self.assertTrue(contains_in_order(txt, ["func_with_args", "use_in_function", "use_in_shell"]))

if __name__ == "__main__":
    unittest.main()
