"""Wrapped copy of the original dagrunner implementation moved into package.
This file was created by refactoring the top-level script into a package layout.
"""
# The original dagrunner.py content is copied here to form the package implementation.
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
import re
from typing import Iterable, Sequence, Set, Dict, Any
import difflib


def _quote_token_for_shell(token: object) -> str:
    """Quote a single token for the current platform's shell."""
    s = "" if token is None else str(token)
    if _is_windows():
        # subprocess.list2cmdline quotes a list of arguments for Windows cmd.exe
        return subprocess.list2cmdline([s])
    else:
        import shlex

        return shlex.quote(s)


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


_PLACEHOLDER_RE = re.compile(r"\$\{outputs\.([A-Za-z0-9_\-]+)\.([A-Za-z0-9_\.]+)\}")
_KWARG_RE = re.compile(r"\$\{kwargs\.([A-Za-z0-9_\-]+)\}")


def _get_output_field(outputs: Dict[str, Dict[str, Any]], task_id: str, field_path: str):
    """Retrieve nested field from stored task outputs. field_path is like 'return_value.x.y'"""
    if task_id not in outputs:
        raise KeyError(f"No outputs for task '{task_id}'")
    cur = outputs[task_id].get("return_value")
    if cur is None:
        return None
    # allow callers to reference 'return_value.x' or just 'x'
    if not field_path:
        return cur
    if field_path.startswith("return_value"):
        # strip leading 'return_value' and optional dot
        field_path = field_path[len("return_value"):]
        if field_path.startswith("."):
            field_path = field_path[1:]
    if not field_path:
        return cur
    for part in field_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            # cannot descend — return None
            return None
    return cur


def resolve_placeholders(obj, outputs: Dict[str, Dict[str, Any]]):
    """Recursively resolve placeholders in strings inside obj using outputs.
    If a string is exactly a single placeholder, return the raw value (could be non-string).
    Otherwise substitute the stringified value into the containing string.
    """
    if isinstance(obj, dict):
        return {k: resolve_placeholders(v, outputs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_placeholders(v, outputs) for v in obj]
    if isinstance(obj, str):
        # If the whole string is exactly one placeholder, return raw object
        m = _PLACEHOLDER_RE.fullmatch(obj)
        if m:
            tid, field = m.group(1), m.group(2)
            return _get_output_field(outputs, tid, field)

        # Otherwise perform replacements inside the string
        def _sub(mobj):
            tid, field = mobj.group(1), mobj.group(2)
            try:
                val = _get_output_field(outputs, tid, field)
            except KeyError:
                return mobj.group(0)
            return str(val)

        return _PLACEHOLDER_RE.sub(_sub, obj)
    return obj


def run_shell(command):
    cp = subprocess.run(command, shell=True, capture_output=True, text=True)
    return {"returncode": cp.returncode, "stdout": cp.stdout or "", "stderr": cp.stderr or ""}


def run_script(path, interpreter, env=None):
    cp = subprocess.run([str(interpreter), str(path)], capture_output=True, text=True, env=env)
    return {"returncode": cp.returncode, "stdout": cp.stdout or "", "stderr": cp.stderr or ""}


def run_function(path, args=None, kwargs=None, interpreter: Path | None = None, project_dir: Path | None = None, env=None):
    """
    Execute module.function(*args, **kwargs) in a subprocess using the provided interpreter,
    with cwd=project_dir (defaults to Path.cwd()).
    """
    import json, subprocess, sys, io, importlib
    from contextlib import redirect_stdout, redirect_stderr

    project_dir = project_dir or Path.cwd()
    args = args or []
    kwargs = kwargs or {}
    if isinstance(kwargs, list):  # guard if someone passed a list by mistake
        kwargs = {}

    # Allow in-process execution when running as a frozen exe or when explicitly requested.
    # This is useful when packaging with PyInstaller and bundling compiled extensions
    # (e.g. pyodbc) into the executable. In-process execution imports and calls the
    # target function directly instead of spawning a subprocess.
    # Only run in-process when explicitly requested via environment variable.
    # Avoid enabling in-process automatically for frozen executables so that
    # the default behavior remains to spawn an external interpreter. This
    # makes packaging simpler: the EXE can remain a thin launcher and allow
    # function tasks to use an external venv with compiled extensions like
    # pyodbc without bundling them into the executable.
    inproc_env = os.environ.get("DAGRUNNER_INPROCESS", "").lower() in ("1", "true", "yes")
    inprocess = inproc_env

    if inprocess:
        try:
            # Ensure project_dir is on sys.path so local modules import correctly
            sys.path.insert(0, str(project_dir))
            mod_name, func_name = path.rsplit(".", 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)
            buf_out = io.StringIO()
            buf_err = io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                rv = func(*args, **(kwargs or {}))
            out = buf_out.getvalue()
            err = buf_err.getvalue()
            return {"stdout": out, "stderr": err, "return_value": rv, "returncode": 0}
        except Exception:
            tb = io.StringIO()
            import traceback as _tb

            _tb.print_exc(file=tb)
            return {"stdout": "", "stderr": tb.getvalue(), "return_value": None, "returncode": 1}

    # Default behavior: spawn a subprocess using a real Python interpreter
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
        capture_output=True,
        env=env,
    )

    if proc.returncode != 0:
        return {"stdout": proc.stdout or "", "stderr": proc.stderr or "", "return_value": None, "returncode": proc.returncode}

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
            return {"returncode": 0, "stdout": "", "stderr": "", "return_value": None}

        # Build env from interpreter (venv) when available
        env = None
        try:
            if interpreter:
                env = _venv_env_for(str(interpreter))
        except Exception:
            env = None

        if task_type == "shell":
            # Support optional args (list) and kwargs (dict) for shell tasks.
            # kwargs are appended as `--key value` pairs.
            base_cmd = task.get("command", "")
            args_list = task.get("args", []) or []
            kwargs_map = task.get("kwargs", {}) or {}

            # First, substitute kwargs into the base command if placeholders are present.
            final_cmd = base_cmd
            if isinstance(kwargs_map, dict) and "${kwargs." in base_cmd:
                def _sub_kw(m):
                    key = m.group(1)
                    if key in kwargs_map:
                        val = kwargs_map[key]
                        return "" if val is None else str(val)
                    return m.group(0)

                final_cmd = _KWARG_RE.sub(_sub_kw, final_cmd)

            # Positional args are appended as tokens (quoted). If kwargs were not
            # embedded into the command, append them as --key value pairs as a
            # fallback for backward compatibility.
            extra_tokens: list[str] = []
            for a in args_list:
                extra_tokens.append(_quote_token_for_shell(a))

            if isinstance(kwargs_map, dict) and "${kwargs." not in base_cmd:
                for k, v in kwargs_map.items():
                    extra_tokens.append(_quote_token_for_shell(f"--{k}"))
                    extra_tokens.append(_quote_token_for_shell(v))

            if extra_tokens:
                final_cmd = final_cmd + " " + " ".join(extra_tokens)

            result = run_shell(final_cmd)  # ok; runs in project_dir due to cwd

        elif task_type == "script":
            real_py = _ensure_real_python(interpreter, project_dir)
            script_path = (project_dir / task["path"]).resolve()
            result = run_script(script_path, real_py, env=env)

        elif task_type == "function":
            real_py = _ensure_real_python(interpreter, project_dir)
            args = task.get("args", [])
            kwargs = task.get("kwargs", {})
            result = run_function(task["path"], args=args, kwargs=kwargs, interpreter=real_py, project_dir=project_dir, env=env)

        else:
            raise ValueError(f"Unknown task type: {task_type}")

        end = time.time()
        duration = round(end - start, 2)

        # Normalized result is dict-like
        if isinstance(result, dict):
            if result.get("returncode", 1) == 0:
                logf.write(f"Status: done\nDuration: {duration}s\n")
            else:
                logf.write(f"Status: failed\nDuration: {duration}s\n")
            logf.write(f"STDOUT:\n{result.get('stdout', '')}\n")
            logf.write(f"STDERR:\n{result.get('stderr', '')}\n")
            # Only show return value if present
            if "return_value" in result:
                logf.write(f"RETURN VALUE:\n{result.get('return_value')}\n")
            return result
        else:
            # Unexpected, but try to normalize
            rc = getattr(result, "returncode", 0)
            out = getattr(result, "stdout", "")
            err = getattr(result, "stderr", "")
            if rc == 0:
                logf.write(f"Status: done\nDuration: {duration}s\n")
            else:
                logf.write(f"Status: failed\nDuration: {duration}s\n")
            logf.write(f"STDOUT:\n{out}\n")
            logf.write(f"STDERR:\n{err}\n")
            return {"returncode": rc, "stdout": out, "stderr": err, "return_value": None}

    except Exception as e:
        end = time.time()
        logf.write(f"Status: failed\nError: {e}\nDuration: {round(end - start, 2)}s\n")
        return {"returncode": 1, "stdout": "", "stderr": str(e), "return_value": None}


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


def run_job(job_id, job, interpreter, timestamp, dry_run=False, ignore_deps=False):
    log_path = LOG_DIR / f"dagrunner_{timestamp}_{job_id}.log"
    with open(log_path, "w") as logf:
        logf.write(f"Interpreter: {interpreter}\n")
        logf.write(f"Job: {job_id}\nStart: {datetime.now()}\n")
        tasks = resolve_dependencies(job["tasks"])
        task_outputs: Dict[str, Dict[str, Any]] = {}
        for task in tasks:
            # Resolve placeholders in the task using previous outputs
            try:
                task = resolve_placeholders(task, task_outputs)
            except Exception as e:
                logf.write(f"Placeholder resolution error for task {task.get('id')}: {e}\n")
            # Check dependencies: if any dependency failed, skip this task (unless ignore_deps)
            deps = task.get("depends_on", []) or []
            if deps and not ignore_deps:
                failed = [d for d in deps if task_outputs.get(d, {}).get("returncode", 0) != 0]
                if failed:
                    logf.write(f"--- Task {task['id']} ---\n")
                    logf.write(f"Status: skipped\nReason: failed dependencies: {failed}\n")
                    task_outputs[task["id"]] = {"returncode": 2, "stdout": "", "stderr": "skipped due to failed dependency", "return_value": None}
                    continue

            result = run_task(task, interpreter, logf, dry_run=dry_run)
            # store result for later placeholders
            tid = task.get("id")
            if isinstance(result, dict):
                task_outputs[tid] = result
            else:
                task_outputs[tid] = {"returncode": 1, "stdout": "", "stderr": "unknown result", "return_value": None}

        logf.write(f"Job: {job_id} complete\n")


def run_all_jobs(config, dry_run=False, ignore_deps=False):
    interpreter = resolve_interpreter(config)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    jobs = config.get("jobs", {})
    procs = []
    for job_id, job in jobs.items():
        proc = multiprocessing.Process(target=run_job, args=(job_id, job, interpreter, timestamp, dry_run, ignore_deps))
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


def load_config(config_path: str | None = None):
    """Load configuration.

    If `config_path` is provided, load that file and set the CWD to its parent.
    Otherwise search upward from CWD for `dagrunner.json` and set the CWD
    to the directory containing it.
    """
    if config_path:
        cand = Path(config_path)
        if not cand.is_file():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        # Make the file's directory the project root
        os.chdir(cand.parent)
        with open(cand) as f:
            return json.load(f)

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
    # Honor explicit env override for packaged apps or CI: DAGRUNNER_PYTHON
    env_override = os.environ.get("DAGRUNNER_PYTHON")
    if env_override:
        try:
            p = Path(env_override)
            if p.exists():
                return p
        except Exception:
            pass

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


def init_config(path: str | None = None):
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
    if path:
        p = Path(path)
        # Ensure parent exists
        if not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            json.dump(base_config, f, indent=2)
        print(f"Initialized dagrunner config at: {p}")
    else:
        with open("dagrunner.json", "w") as f:
            json.dump(base_config, f, indent=2)
        print("Initialized dagrunner.json")


def build_parser() -> argparse.ArgumentParser:
    desc = "DAGRunner - Python-based DAG runner"
    epilog = """
Examples:
  # show all help including subcommands
  python dagrunner.py --help-all

  # run only two tasks in one job
  python dagrunner.py run -j fetching_scripts_and_executing_pipelines \
      -t fetching_from_wsif_thaioil_prod_44 -t fetching_from_wsif_thaioil

  # same via glob
  python dagrunner.py run -j fetching_scripts_and_executing_pipelines \
      --task-glob 'fetching_from_wsif_*'

  # preview the selection (no execution)
  python dagrunner.py list -j fetching_scripts_and_executing_pipelines \
      --task-glob 'fetching_from_wsif_*'
"""

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
        "--file",
        dest="config_file",
        help="Path to a dagrunner JSON config file to use instead of searching for dagrunner.json",
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
    run_parser.add_argument(
        "--ignore-dependencies",
        action="store_true",
        help="Ignore failed dependencies and continue executing dependent tasks.",
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
    validate_parser.add_argument(
        "--file",
        dest="config_file",
        help="Path to a dagrunner JSON config file to validate instead of searching for dagrunner.json",
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
    list_parser.add_argument(
        "--file",
        dest="config_file",
        help="Path to a dagrunner JSON config file to list instead of searching for dagrunner.json",
    )

    # ---------------------------
    # init
    # ---------------------------
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a basic dagrunner.json.",
        description="Create a minimal dagrunner.json in the current directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    init_parser.add_argument(
        "--file",
        dest="config_file",
        help="Path to write the initial dagrunner JSON file (creates parent dirs if needed)",
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
        config = load_config(getattr(args, "config_file", None))
        try:
            validate_config(config)
        except AssertionError as e:
            raise SystemExit(f"Validation error ❌: {e}")
        
        try:
            config = _filter_config_by_args(config, args)
        except KeyError as e:
            raise SystemExit(str(e))
        
        run_all_jobs(config, dry_run=args.dry_run, ignore_deps=getattr(args, "ignore_dependencies", False))

    elif args.command == "validate":
        try:
            config = load_config(getattr(args, "config_file", None))
            validate_config(config)
            print("dagrunner.json is valid ✅")
        except AssertionError as e:
            print(f"Validation error ❌: {e}")

    elif args.command == "list":
        config = load_config(getattr(args, "config_file", None))
        try:
            config = _filter_config_by_args(config, args)
        except Exception:
            pass
        for job_id, job in (config.get("jobs") or {}).items():
            print(f"Job: {job_id}")
            for t in job.get("tasks", []):
                print(f"  - {t['id']} ({t['type']})")

    elif args.command == "init":
        init_config(getattr(args, "config_file", None))

    else:
        parser.print_help()
        sys.exit(2)


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
