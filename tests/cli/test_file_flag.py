import subprocess
import sys
import time
import json
from pathlib import Path
import tempfile


def test_run_with_file_writes_log():
    # Create a temporary folder with a dagrunner_test.json and run dagrunner pointing to it
    with tempfile.TemporaryDirectory() as td:
        tdpath = Path(td)
        cfg = tdpath / "dagrunner.json"
        sample = {
            "jobs": {
                "test_job": {
                    "id": "test_job",
                    "tasks": [
                        {"id": "shell_hello", "type": "shell", "command": "echo [file] hello-from-file"}
                    ]
                }
            }
        }
        cfg.write_text(json.dumps(sample))

        # Invoke the package using the same Python interpreter running the tests
        p = subprocess.run([sys.executable, "-m", "dagrunner", "run", "--file", str(cfg), "-j", "test_job"], capture_output=True, text=True)
        # Allow a moment for the runner to write the log
        time.sleep(1)

        # The runner should have set CWD to the config parent, so the log is placed in tdpath
        logs = list(tdpath.glob("dagrunner_*_test_job.log"))
        assert logs, f"No logs found in {tdpath} (stdout={p.stdout!r}, stderr={p.stderr!r})"
        latest = sorted(logs)[-1]
        txt = latest.read_text()
        assert "hello-from-file" in txt
