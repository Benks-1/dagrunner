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
import fnmatch
from typing import Iterable, Sequence, Set, Dict, Any
import difflib


LOG_DIR = Path.cwd()


def _index_tasks(tasks: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in tasks}


def _normalize_id_list(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for v in values:
        if v is None:
            continue
        # Support comma-separated & repeats: -t a,b -t c
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        out.extend(parts)
    return out


def _fnmatch_any(name: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _select_task_ids(
    all_ids: Sequence[str],
    include_ids: Sequence[str],
    include_globs: Sequence[str],
    exclude_ids: Sequence[str],
    exclude_globs: Sequence[str],
) -> Set[str]:
    ids = set(all_ids)

    if include_ids or include_globs:
        inc: Set[str] = set()
        if include_ids:
            inc.update([i for i in include_ids if i in ids])
        if include_globs:
            inc.update([i for i in all_ids if _fnmatch_any(i, include_globs)])
        selected = inc
    else:
        selected = set(ids)

    # Exclusions
    if exclude_ids:
        selected.difference_update(exclude_ids)
    if exclude_globs:
        selected = {i for i in selected if not _fnmatch_any(i, exclude_globs)}

    return selected


def _dependency_closure(start_ids: Set[str], task_map: Dict[str, Dict[str, Any]]) -> Set[str]:
    """
    Given a set of task ids, include all their transitive dependencies.
    Unknown deps raise a clear error with suggestions.
    """
    result = set()
    stack = list(start_ids)

    while stack:
        tid = stack.pop()
        if tid in result:
            continue
        if tid not in task_map:
            # Suggest closest names
            choices = list(task_map.keys())
            hint = difflib.get_close_matches(tid, choices, n=5)
            msg = f"Task '{tid}' not found. Did you mean: {', '.join(hint) if hint else 'no close matches'}"
            raise KeyError(msg)
        result.add(tid)
        for dep in task_map[tid].get("depends_on", []) or []:
            stack.append(dep)

    return result


def _filter_config_by_args(config: Dict[str, Any], args) -> Dict[str, Any]:
    jobs = config.get("jobs", {})
    if not jobs:
        return config

    # 1) Filter jobs
    job_ids = list(jobs.keys())
    explicitly_selected_jobs = []
    if getattr(args, "jobs", None):
        explicitly_selected_jobs = _normalize_id_list(args.jobs)
        unknown = [j for j in explicitly_selected_jobs if j not in jobs]
        if unknown:
            hint = difflib.get_close_matches(unknown[0], job_ids, n=5)
            raise SystemExit(
                f"Unknown job: {unknown[0]}. Did you mean: {', '.join(hint) if hint else 'no close matches'}"
            )
        selected_jobs = explicitly_selected_jobs
    else:
        selected_jobs = job_ids  # all jobs when none specified

    # Gather task filters
    include_tasks = _normalize_id_list(getattr(args, "tasks", None))
    include_task_globs = _normalize_id_list(getattr(args, "task_globs", None))
    exclude_tasks = _normalize_id_list(getattr(args, "exclude_tasks", None))
    exclude_task_globs = _normalize_id_list(getattr(args, "exclude_task_globs", None))
    with_deps = not getattr(args, "no_deps", False)

    new_jobs: Dict[str, Any] = {}
    for jid in selected_jobs:
        job = jobs[jid]
        tasks = job.get("tasks", [])
        if not tasks:
            # no tasks at all -> keep job only if no includes were requested
            if include_tasks or include_task_globs:
                # drop silently if job was not explicitly requested; error if it was
                if explicitly_selected_jobs:
                    raise SystemExit(
                        f"No tasks available in explicitly selected job '{jid}'."
                    )
                continue
            else:
                new_jobs[jid] = job
                continue

        task_ids = [t["id"] for t in tasks]
        task_map = _index_tasks(tasks)

        # 2) Select tasks for this job
        selected_task_ids = _select_task_ids(
            task_ids,
            include_tasks,
            include_task_globs,
            exclude_tasks,
            exclude_task_globs,
        )

        # 3) Include dependencies if requested (default)
        if with_deps and selected_task_ids:
            selected_task_ids = _dependency_closure(selected_task_ids, task_map)

        # 4) Keep original order, filter to chosen set
        filtered_tasks = [t for t in tasks if t["id"] in selected_task_ids] if (include_tasks or include_task_globs or exclude_tasks or exclude_task_globs) else tasks

        # --- CHANGED behavior ---
        # If includes were provided and nothing matched:
        #   - If the job was explicitly specified via -j/--job, error.
        #   - Otherwise (implicit "all jobs"), silently DROP this job.
        if (include_tasks or include_task_globs) and not filtered_tasks:
            if explicitly_selected_jobs and jid in explicitly_selected_jobs:
                raise SystemExit(
                    f"No tasks matched selection in explicitly selected job '{jid}'. "
                    f"Requested IDs: {include_tasks or '[]'}, globs: {include_task_globs or '[]'}"
                )
            # drop job silently
            continue
        # --- end CHANGED ---

        # Only add the job if it has any tasks after filtering
        if filtered_tasks:
            new_jobs[jid] = {**job, "tasks": filtered_tasks}

    if not new_jobs:
        # Helpful overall message
        inc_ids = include_tasks or []
        inc_globs = include_task_globs or []
        j_hint = f" among jobs: {', '.join(selected_jobs)}" if selected_jobs else ""
        raise SystemExit(
            f"No jobs/tasks matched the selection{j_hint}. "
            f"Requested task IDs: {inc_ids or '[]'}, globs: {inc_globs or '[]'}"
        )

    return {**config, "jobs": new_jobs}


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
        assert "tasks" in job and isinstance(job["tasks"], list), f"Missing or invalid tasks in job {job_id}"
        ids = [t.get("id") for t in job["tasks"]]
        assert len(ids) == len(set(ids)), f"Duplicate task ids in job {job_id}"
        task_map = {t["id"]: t for t in job["tasks"]}
        for task in job["tasks"]:
            assert "id" in task, f"Missing task id in job {job_id}"
            assert "type" in task, f"Missing task type in {task.get('id')}"
            ttype = task["type"]
            if ttype == "shell":
                assert "command" in task and isinstance(task["command"], str), f"shell task {task['id']} missing 'command'"
            elif ttype == "script":
                assert "path" in task, f"script task {task['id']} missing 'path'"
            elif ttype == "function":
                assert "path" in task, f"function task {task['id']} missing 'path' (module:function)"
            else:
                raise AssertionError(f"Unknown task type: {ttype} (task {task['id']})")
            for dep in task.get("depends_on", []) or []:
                assert dep in task_map, f"Task {task['id']} depends on unknown task '{dep}' in job {job_id}"
    # (Optional) add a cycle check here


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


def build_parser() -> argparse.ArgumentParser:
    desc = "DAGRunner - Python-based DAG runner"
    epilog = (
        "Examples:\n"
        "  # show all help including subcommands\n"
        "  python dagrunner.py --help-all\n\n"
        "  # run only two tasks in one job\n"
        "  python dagrunner.py run -j fetching_scripts_and_executing_pipelines \\\n"
        "      -t fetching_from_wsif_thaioil_prod_44 -t fetching_from_wsif_thaioil\n\n"
        "  # same via glob\n"
        "  python dagrunner.py run -j fetching_scripts_and_executing_pipelines \\\n"
        "      --task-glob 'fetching_from_wsif_*'\n\n"
        "  # preview the selection (no execution)\n"
        "  python dagrunner.py list -j fetching_scripts_and_executing_pipelines \\\n"
        "      --task-glob 'fetching_from_wsif_*'\n"
    )

    parser = argparse.ArgumentParser(
        prog="dagrunner.py",
        description=desc,
        epilog=epilog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Global “print everything” helper
    parser.add_argument(
        "--help-all",
        action="store_true",
        help="Show help for the main command and all subcommands, then exit.",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
    )

    # ---------------------------
    # run
    # ---------------------------
    run_parser = subparsers.add_parser(
        "run",
        help="Run jobs (optionally filtered by job/task).",
        description="Run jobs with optional job/task filtering and dependency handling.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and resolve, but do not execute tasks.",
    )
    run_parser.add_argument(
        "-j", "--job",
        dest="jobs",
        action="append",
        help="Job ID to run (repeatable, or comma-separated). If omitted, all jobs run.",
    )
    run_parser.add_argument(
        "-t", "--task",
        dest="tasks",
        action="append",
        help="Task ID to include (repeatable, or comma-separated). Applies to selected jobs.",
    )
    run_parser.add_argument(
        "--task-glob",
        dest="task_globs",
        action="append",
        help="fnmatch-style pattern for task IDs to include (repeatable).",
    )
    run_parser.add_argument(
        "--exclude-task",
        dest="exclude_tasks",
        action="append",
        help="Task ID to exclude (repeatable, or comma-separated).",
    )
    run_parser.add_argument(
        "--exclude-task-glob",
        dest="exclude_task_globs",
        action="append",
        help="fnmatch-style pattern for task IDs to exclude (repeatable).",
    )
    run_parser.add_argument(
        "--no-deps",
        action="store_true",
        help="Do not auto-include transitive dependencies of selected tasks.",
    )

    # ---------------------------
    # validate
    # ---------------------------
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate DAG config.",
        description="Validate the DAG configuration and fail fast on structural issues.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ---------------------------
    # list
    # ---------------------------
    list_parser = subparsers.add_parser(
        "list",
        help="List jobs/tasks (supports the same filters as 'run').",
        description="List jobs and tasks after applying the same filters as 'run' (no execution).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Reuse the same selection flags so 'list' previews exactly what would run.
    list_parser.add_argument(
        "-j", "--job",
        dest="jobs",
        action="append",
        help="Job ID to show (repeatable, or comma-separated). If omitted, all jobs are shown.",
    )
    list_parser.add_argument(
        "-t", "--task",
        dest="tasks",
        action="append",
        help="Task ID to include (repeatable, or comma-separated).",
    )
    list_parser.add_argument(
        "--task-glob",
        dest="task_globs",
        action="append",
        help="fnmatch-style pattern for task IDs to include (repeatable).",
    )
    list_parser.add_argument(
        "--exclude-task",
        dest="exclude_tasks",
        action="append",
        help="Task ID to exclude (repeatable, or comma-separated).",
    )
    list_parser.add_argument(
        "--exclude-task-glob",
        dest="exclude_task_globs",
        action="append",
        help="fnmatch-style pattern for task IDs to exclude (repeatable).",
    )
    list_parser.add_argument(
        "--no-deps",
        action="store_true",
        help="Do not auto-include dependencies when previewing selection.",
    )

    # ---------------------------
    # init
    # ---------------------------
    subparsers.add_parser(
        "init",
        help="Initialize a basic dagrunner.json.",
        description="Create a minimal dagrunner.json in the current directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    return parser


def main():
    parser = build_parser()

    # Support --help-all regardless of subcommands.
    # We parse only known args first to catch --help-all without errors on missing subcommand.
    if "--help-all" in sys.argv:
        # Print main help
        parser.print_help()
        print("\n\n# Subcommand help\n")

        # Print each subparser's help
        subparsers_action = next(
            a for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)  # type: ignore[attr-defined]
        )
        for name, sp in subparsers_action.choices.items():
            print(f"\n## {name}\n")
            sp.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if args.command == "run":
        config = load_config()
        try:
            validate_config(config)
        except AssertionError as e:
            raise SystemExit(f"Validation error ❌: {e}")
        
        try:
            config = _filter_config_by_args(config, args)
        except KeyError as e:
            raise SystemExit(str(e))
        
        run_all_jobs(config, dry_run=args.dry_run)

    elif args.command == "validate":
        try:
            config = load_config()
            validate_config(config)
            print("dagrunner.json is valid ✅")
        except AssertionError as e:
            print(f"Validation error ❌: {e}")

    elif args.command == "list":
        config = load_config()
        try:
            config = _filter_config_by_args(config, args)
        except Exception:
            pass
        for job_id, job in (config.get("jobs") or {}).items():
            print(f"Job: {job_id}")
            for t in job.get("tasks", []):
                print(f"  - {t['id']} ({t['type']})")

    elif args.command == "init":
        init_config()

    else:
        parser.print_help()
        sys.exit(2)

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
