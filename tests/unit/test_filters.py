import unittest
from types import SimpleNamespace
from pathlib import Path
from dagrunner.runner import _filter_config_by_args



class TestFilters(unittest.TestCase):
    def setUp(self):
        # minimal config with two jobs
        self.config = {
            "jobs": {
                "job1": {"id": "job1", "tasks": [{"id": "a", "type": "shell", "command": "echo a"}]},
                "job2": {"id": "job2", "tasks": [{"id": "b", "type": "shell", "command": "echo b"}]},
            }
        }

    def test_unknown_job_raises(self):
        args = SimpleNamespace(jobs=["nope"], tasks=None, task_globs=None, exclude_tasks=None, exclude_task_globs=None, no_deps=False)
        with self.assertRaises(SystemExit):
            _filter_config_by_args(self.config, args)

    def test_include_task_explicit_job_errors_when_missing(self):
        args = SimpleNamespace(jobs=["job1"], tasks=["missing"], task_globs=None, exclude_tasks=None, exclude_task_globs=None, no_deps=False)
        with self.assertRaises(SystemExit) as cm:
            _filter_config_by_args(self.config, args)
        self.assertIn("No tasks matched selection", str(cm.exception))

    def test_task_glob_includes(self):
        # add a task with id 'file_x' to job1 and a task 'file_y' to job2
        self.config["jobs"]["job1"]["tasks"] = [{"id": "file_x", "type": "shell", "command": "echo x"}]
        self.config["jobs"]["job2"]["tasks"] = [{"id": "file_y", "type": "shell", "command": "echo y"}]
        args = SimpleNamespace(jobs=None, tasks=None, task_globs=["file_*"], exclude_tasks=None, exclude_task_globs=None, no_deps=False)
        newcfg = _filter_config_by_args(self.config, args)
        # both jobs should be present and their single task included
        self.assertIn("job1", newcfg["jobs"])
        self.assertIn("job2", newcfg["jobs"])
        self.assertEqual(newcfg["jobs"]["job1"]["tasks"][0]["id"], "file_x")
