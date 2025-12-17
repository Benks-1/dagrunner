import unittest
import tempfile
import os
from pathlib import Path
import dagrunner


class TestLoadConfig(unittest.TestCase):
    def test_load_config_raises_when_missing(self):
        cur = Path.cwd()
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                with self.assertRaises(FileNotFoundError):
                    dagrunner.load_config()
            finally:
                os.chdir(cur)
