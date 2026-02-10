# ⚙️ DAGRunner - Lightweight Local DAG Execution Tool

**DAGRunner** is a simple, standalone command-line tool for executing Directed Acyclic Graph (DAG)-based pipelines defined in a JSON file. It supports shell commands, Python scripts, and Python function calls using the interpreter found in your project environment.

---

## ✨ Features

- ✅ Local execution only – no cloud or orchestration platform dependencies
- 🧩 Define DAGs in `dagrunner.json`
- 🛠 Task types: `shell`, `script`, `function`
- 📜 Full stdout/stderr logging
- 🧵 Sequential tasks within jobs, parallel execution of jobs
- 🐍 Automatically resolves the appropriate Python interpreter
- 🔍 Dry-run mode for previewing execution plans
- 📁 Logs stored with timestamps per run
- 📦 PyInstaller compatible for standalone CLI tool
- 🔁 Task output placeholders: use previous function return values in later tasks
  (e.g. `${outputs.task_id.return_value}`) to pass results between tasks

---

## 📦 Installation

To install for development or to use the CLI from source, install the package in editable mode:

```powershell
py -3.11 -m pip install -e .
```

For packaging the project as a single-file Windows executable, see `PACKAGING.md` in the repository root for full instructions and recommendations.

---

## 🚀 CLI Usage

🆕 Initialize a Project

```bash
dagrunner init
```

Creates a sample dagrunner.json in the current directory.

You can also create the initial config at a custom location with `--file`:

```powershell
dagrunner init --file path\to\my_project\dagrunner.json
```

This will create parent directories as needed and write the sample config at the given path.

▶️ Run DAGs

```bash
dagrunner run
```

Executes all jobs in parallel, with sequential tasks within each job.


🧪 Dry Run

```bash
dagrunner run --dry-run
```

Shows execution plan, including interpreter resolution, task order, and types—without running anything.

✅ Validate Config

```bash
dagrunner validate
```

Checks the integrity and structure of your dagrunner.json.

📋 List Jobs and Tasks

```bash
dagrunner list
```

Prints all job IDs and their tasks with type annotations.

🧬 Example dagrunner.json

```json
{
  "jobs": {
    "example_job": {
      "id": "example_job",
      "tasks": [
        {
          "id": "task1",
          "type": "shell",
          "command": "echo 'Hello World'"
        },
        {
          "id": "task2",
          "type": "script",
          "path": "scripts/example.py",
          "depends_on": ["task1"]
        },
        {
          "id": "task3",
          "type": "function",
          "path": "my_module.entry.main",
          "depends_on": ["task2"]
        }
      ]
    }
  }
}
```

---

## 🧠 Task Types

- 🖥 shell: Executes a shell command

- 📜 script: Runs a Python script using the resolved interpreter

- 🔧 function: Executes a Python function from an importable module

---

**Placeholders (new)**

- You can reference the return value of a prior function task in later tasks using the placeholder syntax:

  - `${outputs.<task_id>.return_value}` — the entire return value from `<task_id>`
  - `${outputs.<task_id>.return_value.some_key}` — nested fields from a dict return value

- Placeholders may be used in:
  - function `args` and `kwargs` (the exact placeholder string will be replaced by the raw object when it is the entire argument),
  - shell `command` strings (will be stringified),
  - script `path` or other string fields if desired.

Example (in `dagrunner.json`):

```json
{
  "id": "use_result",
  "type": "function",
  "path": "mypkg.consumer.consume",
  "args": ["${outputs.producer.return_value}"],
  "depends_on": ["producer"]
}
```

This will substitute the return value from the `producer` task into the `consume` function.

Note: values returned by function tasks are serialized via JSON when executed in a subprocess. If a return value is not JSON-serializable the runner will fall back to its string representation.

---

## 🔎 Selection & Filters

When running `dagrunner run` you can narrow what executes using several flags:

- `-j`, `--job`: select one or more job IDs (repeatable or comma-separated)
- `-t`, `--task`: include specific task IDs (repeatable or comma-separated)
- `--task-glob`: fnmatch-style glob to include tasks by pattern
- `--exclude-task` / `--exclude-task-glob`: exclude tasks by id or glob
- `--no-deps`: do not auto-include transitive dependencies of selected tasks
- `--ignore-dependencies`: run dependent tasks even if upstream tasks failed
- `--help-all`: print help for the main command and all subcommands

If you request includes that match no tasks, `dagrunner` will error when the job was explicitly selected, otherwise it silently drops non-matching implicit jobs.

## ⚙️ Execution details

- `shell` tasks run via the system shell (`subprocess.run(..., shell=True)`).
- `script` tasks run a Python script using the resolved interpreter.
- `function` tasks execute `module.function(*args, **kwargs)` in a subprocess using the resolved interpreter. The child process prints a marker (`<<RETURN_VALUE_JSON>>`) followed by a JSON payload that the parent process extracts as the task return value.
- If a function's return value is not JSON-serializable, the runner falls back to a string representation.
- Placeholders that are exactly a single placeholder are replaced by the raw value (which may be non-string). Placeholders embedded in larger strings are stringified.

## 🧵 Parallel jobs & Windows notes

- Jobs are executed in parallel using `multiprocessing.Process`; tasks within a job run sequentially in dependency order.
- On Windows, frozen executables and multiprocessing require `multiprocessing.freeze_support()`; `cli_entry.py` and `__main__.py` already call this to make frozen builds work correctly.

## 🐍 Interpreter discovery and overrides

Interpreter selection follows this priority:

1. `interpreter` field in `dagrunner.json` (if present)
2. First `python`/`python.exe` found in the project directory
3. Python path from `.code-workspace` settings (if present)
4. Fallback to global interpreter (`sys.executable`)

You can also force a specific interpreter at runtime by setting the `DAGRUNNER_PYTHON` environment variable (useful for packaged executables or CI). See `PACKAGING.md` for examples.

The runner also provides a minimal venv shim so that when it detects a virtualenv interpreter it adjusts `PATH` and `VIRTUAL_ENV` so console scripts and DLLs behave like a normal venv.

## 🧩 Programmatic API

You can import `dagrunner` as a library and call core functions directly. Exported helpers include:

- `main` — the CLI entry function
- `run_function`, `run_script`, `run_shell` — low-level executors
- `run_task`, `run_job`, `run_all_jobs` — higher-level runners
- `load_config`, `validate_config`, `build_parser` — config and CLI helpers
- `resolve_placeholders`, `_ensure_real_python`, `LOG_DIR`

These make it easy to embed or test small parts of the runner programmatically.


**Dependency failure behaviour (new)**

- By default, if a task fails (non-zero return code), any tasks that depend on it will be skipped and marked `Status: skipped` in the job log. This prevents accidental execution of tasks that expect successful prerequisites.

- Override this behavior with `--ignore-dependencies` to force execution of dependent tasks even if upstream tasks failed (useful for debugging):

```powershell
py -3.11 .\dagrunner.py run --ignore-dependencies -j my_job
```

---

**Dry Run**

```bash
dagrunner run --dry-run
```

Shows execution plan, including interpreter resolution, task order, and types—without running anything.

---

## 🧭 Interpreter Resolution

The interpreter is selected in this priority:

1. "interpreter" field in dagrunner.json (if present)

2. First python or python.exe found in the project directory

3. Python path from .code-workspace config (if available)

4. Fallback to global interpreter (sys.executable)

---

## 📂 Logging

Each run generates a file like:

```bash
dagrunner_2025-07-27T22-02-14_example_job.log
```

Log contents include:

- 🏷 Task ID

- 🟢 Status (done, failed)

- ⏱ Duration

- 📤 STDOUT

- 📥 STDERR

- 🔁 Return value (for function tasks)


---


## ✅ Best Practices

- Keep dagrunner.json under version control (e.g., Git)

- Organize scripts and functions as you see fit-

- Ensure import paths are resolvable relative to project root

- Use clear task IDs and define depends_on to enforce execution order

---

## 🧪 Testing

- This repository includes `unittest`-based tests under the `tests/` folder that exercise function/script/shell tasks, placeholder substitutions, and dependency behaviors.

- Run a single test module using:

```powershell
python -m unittest tests.unit.test_run_function -v
python -m unittest tests.unit.test_placeholders -v
python -m unittest tests.unit.test_dependency_skip -v
python -m unittest tests.unit.test_ignore_deps_flag -v
python -m unittest tests.cli.test_placeholder_usage -v
```

- If you prefer to run all tests, you can run each test module as shown above, or add `__init__.py` files under `tests/` to make them discoverable and then run:

```powershell
python -m unittest discover -v tests
```

Note: test modules invoke `dagrunner.py` (CLI) for integration tests using the system Python launcher (`py -3.11`). Adjust the commands if you use a different interpreter.


## ⚠️ Limitations

- 🚫 No distributed/cloud execution

- ❌ No retries, retries-on-failures, or scheduling

- 🖼 No DAG visualization

---

## 🪪 License
MIT