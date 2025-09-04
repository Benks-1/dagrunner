import argparse
import json
import os
import subprocess
import sys
import time
import multiprocessing
from pathlib import Path
from datetime import datetime
import platform, shutil

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


def run_function(path, args=None, kwargs=None, interpreter: Path | None = None, project_dir: Path | None = None):
    """
    Execute module.function(*args, **kwargs) in a subprocess using the provided interpreter,
    with cwd=project_dir (defaults to Path.cwd()).
    """
    import json, subprocess, sys, io, importlib
    from contextlib import redirect_stdout, redirect_stderr

    project_dir = project_dir or Path.cwd()
    args = args or []
    kwargs = kwargs or []
    if isinstance(kwargs, list):  # guard if someone passed a list by mistake
        kwargs = {}

    if interpreter is None:
        interpreter = _ensure_real_python(None, project_dir)

    launcher = r"""
import importlib, json, sys, traceback, os
sys.path.insert(0, os.getcwd())
mod_name, func_name = "{mod_func}".rsplit(".", 1)
try:
    mod = importlib.import_module(mod_name)
    func = getattr(mod, func_name)
    a = json.loads(sys.argv[1])
    k = json.loads(sys.argv[2])
    rv = func(*a, **k)
    try:
        print("<<RETURN_VALUE_JSON>>" + json.dumps(rv, default=str))
    except Exception:
        print("<<RETURN_VALUE_JSON>>" + json.dumps(str(rv)))
except Exception:
    traceback.print_exc()
    sys.exit(1)
""".replace("{mod_func}", path)

    proc = subprocess.run(
        [str(interpreter), "-c", launcher, json.dumps(args), json.dumps(kwargs)],
        cwd=str(project_dir),
        text=True,
        capture_output=True
    )

    if proc.returncode != 0:
        return {"stdout": proc.stdout, "stderr": proc.stderr, "return_value": None, "returncode": proc.returncode}

    stdout = proc.stdout or ""
    ret_val = None
    marker = "<<RETURN_VALUE_JSON>>"
    if marker in stdout:
        i = stdout.rfind(marker)
        payload = stdout[i+len(marker):].strip()
        stdout = stdout[:i]
        try:
            ret_val = json.loads(payload)
        except Exception:
            ret_val = payload

    return {"stdout": stdout, "stderr": proc.stderr or "", "return_value": ret_val, "returncode": 0}



def _venv_env_for(interpreter_path: str):
    """
    Minimal env shim so console scripts/DLLs resolve like in normal venv runs.
    Safe no-op if 'interpreter_path' isn't a venv layout.
    """
    env = os.environ.copy()
    ip = Path(interpreter_path)
    scripts = ip.parent                      # .../Scripts or .../bin
    venv_root = scripts.parent
    # If it looks like a venv, set a couple of niceties
    if scripts.name in ("Scripts", "bin"):
        env["PATH"] = str(scripts) + os.pathsep + env.get("PATH", "")
        env["VIRTUAL_ENV"] = str(venv_root)
        env.pop("PYTHONHOME", None)
    return env


def run_task(task, interpreter, logf, dry_run=False):
    task_id = task["id"]
    task_type = task["type"]
    project_dir = Path.cwd()  # after A., this is the folder with dagrunner.json
    logf.write(f"\n--- Task {task_id} ---\n")

    start = time.time()
    try:
        if dry_run:
            logf.write(f"[DRY RUN] Would execute {task_type} task: {task}\n")
            return

        if task_type == "shell":
            result = run_shell(task["command"])  # ok; runs in project_dir due to cwd

        elif task_type == "script":
            real_py = _ensure_real_python(interpreter, project_dir)
            script_path = (project_dir / task["path"]).resolve()
            result = run_script(script_path, real_py)

        elif task_type == "function":
            real_py = _ensure_real_python(interpreter, project_dir)
            args = task.get("args", [])
            kwargs = task.get("kwargs", {})
            result = run_function(task["path"], args=args, kwargs=kwargs, interpreter=real_py, project_dir=project_dir)

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
    # Find dagrunner.json from CWD upward; then treat its folder as project root
    here = Path.cwd().resolve()
    cfg_path = None
    for p in [here] + list(here.parents):
        cand = p / "dagrunner.json"
        if cand.exists():
            cfg_path = cand
            os.chdir(p)  # <- make the project root the working directory
            break
    if cfg_path is None:
        raise FileNotFoundError("dagrunner.json not found in current directory or any parent")

    with open(cfg_path) as f:
        return json.load(f)

def _is_windows():
    return platform.system().lower().startswith("win")

def _find_project_python(project_dir: Path) -> Path | None:
    for name in ("python.exe", "python"):
        for p in project_dir.rglob(name):
            if p.parent.name in ("Scripts", "bin"):
                return p
    return None

def _fallback_system_python() -> Path | None:
    if _is_windows():
        try:
            out = subprocess.check_output(
                ["py", "-3", "-c", "import sys;print(sys.executable)"],
                text=True
            ).strip()
            if out and "python" in Path(out).name.lower():
                return Path(out)
        except Exception:
            pass
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if exe:
            return Path(exe)
    return None

def _ensure_real_python(interpreter: Path | str | None, project_dir: Path) -> Path:
    if interpreter:
        ip = Path(interpreter)
        if "python" in ip.name.lower():
            return ip
    py = _find_project_python(project_dir) or _fallback_system_python()
    if py:
        return py
    cur = Path(sys.executable)
    if "python" in cur.name.lower():
        return cur
    raise RuntimeError("No suitable Python interpreter found (avoid using dagrunner.exe).")


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
