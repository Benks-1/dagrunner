import unittest
import os
from pathlib import Path
import tempfile
import dagrunner


class TestInterpreterOverride(unittest.TestCase):
    def test_dagrunner_python_env_used(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fakepython.exe"
            p.write_text("")
            os.environ["DAGRUNNER_PYTHON"] = str(p)
            try:
                res = dagrunner._ensure_real_python(None, Path.cwd())
                self.assertEqual(str(res), str(p))
            finally:
                os.environ.pop("DAGRUNNER_PYTHON", None)
