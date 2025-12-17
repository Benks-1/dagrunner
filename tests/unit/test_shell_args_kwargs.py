import unittest
import io
from dagrunner import runner


class TestShellArgsKwargs(unittest.TestCase):
    def test_shell_args_and_kwargs_applied(self):
        # Prepare a shell task that echoes its args and kwargs
        task = {
            "id": "s1",
            "type": "shell",
            "command": "echo got ${kwargs.x}",
            "args": ["alpha", "beta"],
            "kwargs": {"x": "y"},
        }
        logbuf = io.StringIO()
        res = runner.run_task(task, interpreter=None, logf=logbuf, dry_run=False)
        # stdout should contain the tokens (order: alpha beta --x y)
        out = res.get("stdout", "")
        # embedded kwarg substitution should appear
        self.assertIn("got y", out)
        # positional args still appended
        self.assertIn("alpha", out)
        self.assertIn("beta", out)


if __name__ == "__main__":
    unittest.main()
