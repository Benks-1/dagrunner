import os
import json
import tempfile
import unittest
from pathlib import Path

import dagrunner.runner as runner


class TestInitAndLoadFile(unittest.TestCase):
    def test_init_writes_file_at_path(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "nested" / "mydag.json"
            # ensure does not exist yet
            self.assertFalse(target.exists())
            runner.init_config(str(target))
            self.assertTrue(target.exists())
            data = json.loads(target.read_text())
            self.assertIn("jobs", data)

    def test_load_config_with_file_sets_cwd(self):
        oldcwd = os.getcwd()
        with tempfile.TemporaryDirectory() as td:
            tdpath = Path(td)
            cfg = tdpath / "dag.json"
            sample = {"jobs": {"j": {"id": "j", "tasks": []}}}
            cfg.write_text(json.dumps(sample))
            try:
                result = runner.load_config(str(cfg))
                # load_config should return the parsed content
                self.assertEqual(result, sample)
                # and should have changed CWD to the config's parent
                self.assertEqual(Path.cwd().resolve(), tdpath.resolve())
            finally:
                # restore cwd before TemporaryDirectory cleanup
                os.chdir(oldcwd)


if __name__ == "__main__":
    unittest.main()
