import unittest
import dagrunner


class TestValidateConfig(unittest.TestCase):
    def test_missing_tasks_key_raises(self):
        cfg = {"jobs": {"j": {}}}
        with self.assertRaises(AssertionError):
            dagrunner.validate_config(cfg)

    def test_duplicate_task_ids_raise(self):
        cfg = {
            "jobs": {
                "j": {
                    "id": "j",
                    "tasks": [
                        {"id": "t1", "type": "shell", "command": "echo 1"},
                        {"id": "t1", "type": "shell", "command": "echo 2"},
                    ]
                }
            }
        }
        with self.assertRaises(AssertionError):
            dagrunner.validate_config(cfg)

    def test_missing_task_type_raises(self):
        cfg = {"jobs": {"j": {"id": "j", "tasks": [{"id": "t"}]}}}
        with self.assertRaises(AssertionError):
            dagrunner.validate_config(cfg)
