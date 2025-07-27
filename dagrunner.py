import argparse
import json
import os
import subprocess
import sys
import time
import multiprocessing
import importlib
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from datetime import datetime

LOG_DIR = Path.cwd()


def resolve_interpreter(config):
    if config.get("interpreter"):
        return Path(config["interpreter"])

    for p in Path.cwd().rglob("python.exe"):
        return p
    for p in Path.cwd().rglob("python"):
        if p.is_file() and os.access(p, os.X_OK):
            return p

    for f in Path.cwd().glob("*.code-workspace"):
        try:
            content = json.loads(f.read_text())
            interp = content.get("settings", {}).get("python.defaultInterpreterPath")
            if interp:
                return Path(interp)
        except Exception:
            continue

    return Path(sys.executable)


def run_shell(command):
    return subprocess.run(command, shell=True, capture_output=True, text=True)


def run_script(path, interpreter):
    return subprocess.run([str(interpreter), str(path)], capture_output=True, text=True)


def run_function(path, args=None, kwargs=None):
    module_name, func_name = path.rsplit('.', 1)
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    mod = importlib.import_module(module_name)
    func = getattr(mod, func_name)

    stdout_io = io.StringIO()
    stderr_io = io.StringIO()

    args = args or []
    kwargs = kwargs or {}

    with redirect_stdout(stdout_io), redirect_stderr(stderr_io):
        result = func(*args, **kwargs)

    return {
        "stdout": stdout_io.getvalue(),
        "stderr": stderr_io.getvalue(),
        "return_value": result,
        "returncode": 0
    }


def run_task(task, interpreter, logf, dry_run=False):
    task_id = task["id"]
    task_type = task["type"]
    logf.write(f"\n--- Task {task_id} ---\n")
    start = time.time()
    try:
        if dry_run:
            logf.write(f"[DRY RUN] Would execute {task_type} task: {task}\n")
            return

        if task_type == "shell":
            result = run_shell(task["command"])
        elif task_type == "script":
            result = run_script(task["path"], interpreter)
        elif task_type == "function":
            args = task.get("args", [])
            kwargs = task.get("kwargs", {})
            result = run_function(task["path"], args=args, kwargs=kwargs)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

        end = time.time()
        duration = round(end - start, 2)

        if isinstance(result, dict):
            if result.get("returncode", 1) != 0:
                raise RuntimeError(result.get("stderr", "Unknown error"))
            logf.write(f"Status: done\nDuration: {duration}s\n")
            logf.write(f"STDOUT:\n{result.get('stdout', '')}\n")
            logf.write(f"STDERR:\n{result.get('stderr', '')}\n")
            logf.write(f"RETURN VALUE:\n{result.get('return_value')}\n")
        else:
            if result.returncode != 0:
                raise RuntimeError(result.stderr)
            logf.write(f"Status: done\nDuration: {duration}s\n")
            logf.write(f"STDOUT:\n{result.stdout}\n")
            logf.write(f"STDERR:\n{result.stderr}\n")

    except Exception as e:
        end = time.time()
        logf.write(f"Status: failed\nError: {e}\nDuration: {round(end - start, 2)}s\n")


def resolve_dependencies(tasks):
    task_map = {t["id"]: t for t in tasks}
    resolved = []
    seen = set()

    def visit(task):
        if task["id"] in seen:
            return
        for dep in task.get("depends_on", []):
            visit(task_map[dep])
        seen.add(task["id"])
        resolved.append(task)

    for task in tasks:
        visit(task)

    return resolved


def run_job(job_id, job, interpreter, timestamp, dry_run=False):
    log_path = LOG_DIR / f"dagrunner_{timestamp}_{job_id}.log"
    with open(log_path, "w") as logf:
        logf.write(f"Interpreter: {interpreter}\n")
        logf.write(f"Job: {job_id}\nStart: {datetime.now()}\n")
        tasks = resolve_dependencies(job["tasks"])
        for task in tasks:
            run_task(task, interpreter, logf, dry_run=dry_run)
        logf.write(f"Job: {job_id} complete\n")


def run_all_jobs(config, dry_run=False):
    interpreter = resolve_interpreter(config)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    jobs = config.get("jobs", {})
    procs = []
    for job_id, job in jobs.items():
        proc = multiprocessing.Process(target=run_job, args=(job_id, job, interpreter, timestamp, dry_run))
        proc.start()
        procs.append(proc)
    for p in procs:
        p.join()


def validate_config(config):
    assert "jobs" in config, "Missing 'jobs' key"
    for job_id, job in config["jobs"].items():
        assert "tasks" in job, f"Missing tasks in job {job_id}"
        for task in job["tasks"]:
            assert "id" in task, f"Missing task id in job {job_id}"
            assert "type" in task, f"Missing task type in {task['id']}"


def load_config():
    with open("dagrunner.json") as f:
        return json.load(f)


def init_config():
    base_config = {
        "jobs": {
            "example_job": {
                "id": "example_job",
                "tasks": [
                    {"id": "task1", "type": "shell", "command": "echo 'Hello World'"},
                    {"id": "task2", "type": "script", "path": "scripts/example.py", "depends_on": ["task1"]},
                    {"id": "task3", "type": "function", "path": "my_module.entry.main", "depends_on": ["task2"], "args": ["value1"], "kwargs": {"arg2": "value2"}}
                ]
            }
        }
    }
    with open("dagrunner.json", "w") as f:
        json.dump(base_config, f, indent=2)
    print("Initialized dagrunner.json")


def main():
    parser = argparse.ArgumentParser(description="DAGRunner - Python-based DAG runner")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run all jobs")
    run_parser.add_argument("--dry-run", action="store_true", help="Dry run - show what would be executed")

    subparsers.add_parser("validate", help="Validate DAG config")
    subparsers.add_parser("list", help="List all jobs and tasks")
    subparsers.add_parser("init", help="Initialize a basic dagrunner.json")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "init":
        init_config()
        return

    config = load_config()

    if args.command == "run":
        run_all_jobs(config, dry_run=args.dry_run)
    elif args.command == "validate":
        try:
            validate_config(config)
            print("dagrunner.json is valid ✅")
        except AssertionError as e:
            print(f"Validation error ❌: {e}")
    elif args.command == "list":
        for job_id, job in config.get("jobs", {}).items():
            print(f"Job: {job_id}")
            for task in job.get("tasks", []):
                print(f"  - {task['id']} ({task['type']})")


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
