import unittest
from pathlib import Path
import dagrunner

class TestRunFunction(unittest.TestCase):
    def test_run_function_captures_return_and_stdout(self):
        # Use an existing test module in repo: tests.mypkg.entry
        interp = dagrunner._ensure_real_python(None, Path.cwd())
        res = dagrunner.run_function("tests.mypkg.entry.say_hello", interpreter=interp, project_dir=Path.cwd())
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("returncode"), 0)
        # return_value from say_hello should be a dict or string representation
        self.assertIsNotNone(res.get("return_value"))
        # stdout should contain a hello string
        self.assertIn("hello", res.get("stdout", "").lower())

if __name__ == "__main__":
    unittest.main()
