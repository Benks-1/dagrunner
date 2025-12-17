import unittest
import tempfile
import os
from pathlib import Path
import dagrunner


class TestRunScriptShell(unittest.TestCase):
    def test_run_script_and_shell_capture_output(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # create a small script
            script = td_path / "script.py"
            script.write_text("import sys\nprint('OUT')\nprint('ERR', file=sys.stderr)\n")
            # run script using resolved interpreter
            interp = dagrunner._ensure_real_python(None, Path.cwd())
            res = dagrunner.run_script(script, interp, env=None)
            self.assertEqual(res.get("returncode"), 0)
            self.assertIn("OUT", res.get("stdout"))
            self.assertIn("ERR", res.get("stderr"))

            # run shell command
            shell_res = dagrunner.run_shell("python -c \"print('SHELL_OUT')\"")
            # returncode may be non-zero if 'python' not found; assert stdout content if rc==0
            if shell_res.get("returncode") == 0:
                self.assertIn("SHELL_OUT", shell_res.get("stdout"))
