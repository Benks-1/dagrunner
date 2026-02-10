# DAGRunner: Hands-on smoke tests (commands start with `dagrunner run`)

This document contains copy-pasteable PowerShell commands that run `dagrunner` itself (not unittest). Each example runs a job from the repository `dagrunner.json` (created in the repo root) and shows the exact log excerpt created when I ran the same command here. Use these examples to verify the runner and to inspect the produced logs.

Prerequisites
- Windows PowerShell
- Activate the same venv used for development so the `dagrunner` console script is on PATH. Example used in these examples:

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
```

Make sure `dagrunner.json` exists at the repository root. This repo includes a ready-made `dagrunner.json` with demo jobs: `test_job`, `j1`, `j2`, `parallel_a`, and `parallel_b`.

Where logs are written
- Each job produces a log file under the current working directory (or wherever `LOG_DIR` is set). Filenames look like:

```
dagrunner_YYYY-MM-DDTHH-MM-SS_<job_id>.log
```

Common helper to print the last log for a job (PowerShell):

```powershell
$p=(gci -File -Filter "dagrunner_*_<jobid>.log" | Sort-Object LastWriteTime | Select-Object -Last 1)
if ($p) { Get-Content $p.FullName -Raw } else { Write-Host "No log found for <jobid>" }
```

1) Full example — `test_job` (shell, script, function, placeholders)

Command (copy/paste):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
dagrunner run -j test_job

# view the most recent test_job log
$p=(gci -File -Filter 'dagrunner_*_test_job.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Raw
```

Exact log excerpt I obtained when running this command here:

```
Interpreter: F:\Environemts\Python\Venvs\dagrunner\Scripts\python.exe
Job: test_job
Start: 2025-11-27 23:17:08.394316

--- Task shell_hello ---
Status: done
Duration: 0.01s
STDOUT:
[shell] hello from shell task

STDERR:

--- Task script_hello ---
Status: done
Duration: 0.04s
STDOUT:
[scripts.hello] Hello from script at 2025-11-27T23:17:08
[scripts.hello] This is STDOUT.

STDERR:
[scripts.hello] Writing something to STDERR...

--- Task func_plain ---
Status: done
Duration: 0.05s
STDOUT:
[mypkg.entry.say_hello] Hi from function at 2025-11-27T23:17:08

STDERR:

RETURN VALUE:
{'status': 'ok', 'source': 'say_hello'}

--- Task func_with_args ---
Status: done
Duration: 0.05s
STDOUT:
[mypkg.entry.add] a=40, b=2, total=42

STDERR:

RETURN VALUE:
42

--- Task func_with_args_kwargs ---
Status: done
Duration: 0.05s
STDOUT:
[mypkg.entry.echo_args_kwargs] args=(1, 2, 3) kwargs={'x': 'alpha', 'y': 99}

STDERR:

RETURN VALUE:
{'args': [1, 2, 3], 'kwargs': {'x': 'alpha', 'y': 99}}

--- Task func_stderr ---
Status: done
Duration: 0.05s
STDOUT:
[mypkg.entry.noisy] normal print to STDOUT

STDERR:
[mypkg.entry.noisy] simulated warning on STDERR

RETURN VALUE:
done

--- Task use_in_function ---
Status: done
Duration: 0.05s
STDOUT:
[mypkg.entry.consume] got value: 42

STDERR:

RETURN VALUE:
84

--- Task use_in_shell ---
Status: done
Duration: 0.01s
STDOUT:
[shell] consumed=42

STDERR:

Job: test_job complete
```

What to expect: the log shows each task's status, STDOUT/STDERR, durations, and return values for function tasks. Note the placeholder substitution: `use_in_shell` receives stringified `42`.

2) Dependency-skip example — `j1` (failing task causes dependent to be skipped)

Command (copy/paste):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
dagrunner run -j j1

# view the j1 log
$p=(gci -File -Filter 'dagrunner_*_j1.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Raw
```

Exact log excerpt I obtained here:

```
Interpreter: F:\Environemts\Python\Venvs\dagrunner\Scripts\python.exe
Job: j1
Start: 2025-11-27 23:17:26.365251

--- Task t1 ---
Status: failed
Duration: 0.06s
STDOUT:

STDERR:
Traceback (most recent call last):
  File "<string>", line 10, in <module>
  File "F:\Code\dagrunner\demo_tasks.py", line 2, in fail
    raise RuntimeError("boom")
RuntimeError: boom

RETURN VALUE:
None
--- Task t2 ---
Status: skipped
Reason: failed dependencies: ['t1']
Job: j1 complete
```

What to expect: `t1` fails and `t2` is skipped. The log contains the traceback from the failing child process and a `Status: skipped` note for `t2`.

3) Dependency-ignore example — `j2` (`--ignore-dependencies` allows dependent to run)

Command (copy/paste):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
dagrunner run -j j2 --ignore-dependencies

# view the j2 log
$p=(gci -File -Filter 'dagrunner_*_j2.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Raw
```

Exact log excerpt I obtained here:

```
Interpreter: F:\Environemts\Python\Venvs\dagrunner\Scripts\python.exe
Job: j2
Start: 2025-11-27 23:17:40.626455

--- Task t1 ---
Status: failed
Duration: 0.05s
STDOUT:

STDERR:
Traceback (most recent call last):
  File "<string>", line 10, in <module>
  File "F:\Code\dagrunner\demo_tasks.py", line 2, in fail
    raise RuntimeError("boom")
RuntimeError: boom

RETURN VALUE:
None

--- Task t2 ---
Status: done
Duration: 0.05s
STDOUT:
ok got None

STDERR:

RETURN VALUE:
None
Job: j2 complete
```

What to expect: the failing `t1` is recorded but `t2` still executes because `--ignore-dependencies` was supplied; you see `Status: done` for `t2` and its stdout.

4) Parallel jobs (run all jobs)

Command (copy/paste):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
dagrunner run

# list the most recent logs (last 6)
gci -File -Filter 'dagrunner_*_*.log' | Sort-Object LastWriteTime | Select-Object -Last 6 | Format-List Name,LastWriteTime
```

Example recent logs I saw after running `dagrunner run`:

```
dagrunner_2025-11-27T23-17-40_j2.log
dagrunner_2025-11-27T23-17-58_parallel_a.log
dagrunner_2025-11-27T23-17-58_parallel_b.log
dagrunner_2025-11-27T23-17-58_j1.log
dagrunner_2025-11-27T23-17-58_j2.log
dagrunner_2025-11-27T23-17-58_test_job.log
```

What to expect: multiple job logs created in parallel — `parallel_a` and `parallel_b` run concurrently with other jobs. Inspect each log for the usual markers (`Status: done/failed/skipped`, `STDOUT`, `STDERR`, `RETURN VALUE:`).

5) Forcing a specific Python interpreter (`DAGRUNNER_PYTHON`)

Command (copy/paste):

```powershell
$env:DAGRUNNER_PYTHON = 'C:\Python311\python.exe'
dagrunner run -j test_job

# show top of the most recent test_job log
$p=(gci -File -Filter 'dagrunner_*_test_job.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -TotalCount 3
```

Expected: the first line in the log shows `Interpreter: C:\Python311\python.exe` (or whatever you set `DAGRUNNER_PYTHON` to).

7) Creating an init file at a custom path

Command (copy/paste):

```powershell
dagrunner init --file C:\full\path\to\project\dagrunner.json

# then run that config explicitly
dagrunner run --file C:\full\path\to\project\dagrunner.json -j example
```

What to expect: `init --file` writes the sample `dagrunner.json` at the supplied path (creating parent dirs). When you run with `--file`, the runner treats that file's parent folder as the project root, so relative script imports, paths and placeholder resolution behave the same as the default upward-search behavior.

6) Quick troubleshooting steps

- If a command creates no log, ensure you ran it from the folder containing `dagrunner.json` (the runner searches upward from CWD).
- If function/script tasks fail to import modules, ensure the working directory contains the modules or set `PYTHONPATH` accordingly.
- To check the last 200 lines of the most recent log for a job:

```powershell
$p=(gci -File -Filter 'dagrunner_*_test_job.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Tail 200
```

If you want, I can add a `scripts/collect_test_logs.ps1` helper that runs these smoke commands and copies the resulting logs into `tests/logs/` for archiving or CI upload — say the word and I'll add it.
# Tests — How to run and what to expect

This document explains how to run the test suite for `dagrunner`, how to run specific tests, what to pass on the console, expected outputs, and how to verify test artifacts (logs and packaged exe). It covers positive and negative cases for all capabilities implemented by the runner.

Prerequisites
- Windows (instructions use PowerShell)
- Python 3.11 (the repo was developed against 3.11.x)
- A virtual environment with project dependencies (optional but recommended)
- `PyInstaller` (optional — only required for packaging-related checks)

Activate your venv (example path used in this repo):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
```

Install test deps (if needed):

```powershell
py -3.11 -m pip install -e .
py -3.11 -m pip install pyinstaller
```

Run the full test suite
-----------------------

This repository uses the builtin `unittest` discovery. From the repository root run:

```powershell
python -m unittest discover -v tests
```

Expected outcome (green):

```
----------------------------------------------------------------------
Ran N tests in X.XXXs

OK
```

If any test fails you'll receive a traceback and unittest will list failing tests and errors.

Run only unit tests
-------------------

```powershell
python -m unittest discover -v tests.unit
```

Run CLI/integration tests
-------------------------

CLI tests execute the package via the `py -3.11 -m dagrunner` launcher or the packaged exe. Run them with:

```powershell
python -m unittest -v tests.cli.test_end_to_end
python -m unittest -v tests.cli.test_placeholder_usage
```

These tests spawn the actual CLI and then inspect log files produced in the repository root.

Running an individual test file
------------------------------

```powershell
python -m unittest -v tests.unit.test_placeholders
```

Using tests in VS Code
----------------------

- Open the repo in VS Code.
- Ensure the Python interpreter is set to your venv (see `.vscode/settings.json`).
- The workspace `.env` contains `PYTHONPATH=src` so the test runner sees the package source.
- Use the Testing UI (beaker icon) to run tests or run the same `python -m unittest` commands in the integrated terminal.

What the tests cover (capabilities)
----------------------------------

The tests exercise the following capabilities. For each capability the document below includes how to run it and the expected artifacts.

- Selection & filters
  - Flags: `-j/--job`, `-t/--task`, `--task-glob`, `--exclude-task`, `--exclude-task-glob`, `--no-deps`, `--ignore-dependencies`, `--help-all`.
  - Tests: `tests/unit/test_filters.py` (positive/negative cases for missing includes and globs).
  - How to run manually: `dagrunner run -j test_job -t func_with_args` (or via the unittest CLI tests that already exercise behaviour).

- Dependency handling
  - Default behaviour: if a task fails, dependent tasks are skipped.
  - Override: `--ignore-dependencies` forces dependent tasks to run.
  - Tests: `tests/unit/test_dependency_skip.py`, `tests/unit/test_ignore_deps_flag.py`.
  - Manual check: run job containing a failing function and then inspect the generated log file (see Log Format below).

- Placeholder resolution
  - Syntax: `${outputs.<task_id>.<field_path>}`
  - Exact-match placeholders return raw objects; embedded placeholders are stringified.
  - Tests: `tests/unit/test_placeholders.py`, `tests/unit/test_placeholders_missing.py`, `tests/cli/test_placeholder_usage.py`.

- Task types (execution)
  - `shell`: executed via shell (`subprocess.run(..., shell=True)`). Tests: `tests/unit/test_run_script_shell.py` and CLI tests.
  - `script`: executed by invoking a real Python interpreter on the script path (`run_script`).
  - `function`: executed by importing and calling `module.func` inside a child Python subprocess. The runner extracts the return value using a marker `<<RETURN_VALUE_JSON>>`.
  - Tests: `tests/unit/test_run_function.py` (function subprocess behaviour) and other integration tests.

- Interpreter discovery and override
  - Priority: `interpreter` in `dagrunner.json` → project-local `python` → `.code-workspace` setting → global `sys.executable`.
  - Override via env var: `DAGRUNNER_PYTHON` (useful for packaged exe). Tests: `tests/unit/test_interpreter_override.py`.
  - Example (PowerShell):

    ```powershell
    $env:DAGRUNNER_PYTHON = 'C:\Python311\python.exe'
    dist\dagrunner.exe run -j test_job
    ```

- Validation / config errors
  - `validate_config()` raises on missing keys, duplicate task IDs, or missing task fields.
  - Tests: `tests/unit/test_validate_config.py`.

- Loading config
  - `load_config()` searches upward from CWD for `dagrunner.json` and sets the project root as CWD.
  - Test: `tests/unit/test_load_config.py` (ensures FileNotFoundError when missing).

- Logging
  - Each job run writes a log file to `LOG_DIR` (defaults to `Path.cwd()`), e.g.:

    ```text
    dagrunner_2025-11-27T22-39-45_test_job.log
    ```

  - Log file format (example snippet):

    ```text
    Interpreter: F:\Code\dagrunner\dist\dagrunner.exe
    Job: test_job
    Start: 2025-11-27 22:39:45.226730

    --- Task shell_hello ---
    Status: done
    Duration: 0.01s
    STDOUT:
    [shell] hello from shell task

    STDERR:

    --- Task func_with_args ---
    Status: done
    Duration: 0.09s
    STDOUT:
    [mypkg.entry.add] a=40, b=2, total=42

    RETURN VALUE:
    42
    ```

  - Tests look for these markers (`Status: done`, `Status: failed`, `Status: skipped`, `RETURN VALUE:`) and for task IDs present in the log.

- Packaging / PyInstaller
  - The repo contains `cli_entry.py` and `build_exe.ps1` to aid packaging.
  - `PACKAGING.md` contains instructions and notes about `DAGRUNNER_PYTHON` and distributing to machines without Python.
  - To build locally (PowerShell):

    ```powershell
    .\build_exe.ps1 -VenvActivate 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
    # or simply
    .\build_exe.ps1
    ```

  - After a successful build the single-file exe is at `dist\dagrunner.exe`.

Negative/edge-case test behaviours and expected console outputs
--------------------------------------------------------------

- Missing `dagrunner.json`:
  - `load_config()` raises `FileNotFoundError`.
  - Test: `tests/unit/test_load_config.py`.

- Unknown job specified with `-j`:
  - When `-j` contains an unknown job id, `_filter_config_by_args()` triggers a `SystemExit` with helpful suggestion. The CLI will print the error and exit.

- Includes that match no tasks:
  - If you explicitly selected a job with `-j` and then used `-t`/`--task`/`--task-glob` that matches nothing in that job, `dagrunner` raises `SystemExit` (tested in `tests/unit/test_filters.py`). If no explicit job is given, non-matching jobs are silently dropped.

- Placeholders referencing missing outputs:
  - Exact-match placeholder (the entire string) referencing an unknown task raises `KeyError` during placeholder resolution (test `tests/unit/test_placeholders_missing.py`).
  - Embedded placeholder (inside a larger string) leaves the placeholder text intact (the substitution function returns the original placeholder text if it cannot resolve it).

Tips for debugging failing tests
-------------------------------

- Re-run a failing test with verbosity to see stack traces:

```powershell
python -m unittest -v tests.unit.test_filters.TestFilters.test_unknown_job_raises
```

- Inspect recently written log files in the repository root:

```powershell
Get-ChildItem -File -Filter 'dagrunner_*_*.log' | Sort-Object LastWriteTime | Select-Object -Last 5
```

- When CLI tests spawn subprocesses, the `PATH` and `PYTHONPATH` used by those subprocesses can affect results; ensure the venv is activated or `DAGRUNNER_PYTHON` points to a valid interpreter.

CI Recommendations
------------------

- Use a runner with Python 3.11 installed.
- Activate a venv and install the project with `pip install -e .` before running tests.
- Optionally run the packaging step (PyInstaller) if you want to validate the `dist\dagrunner.exe` behaviour — this is slower and may be omitted from quick CI runs.

Example CI script (PowerShell-like pseudocode):

```powershell
# install
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
py -3.11 -m pip install -e .

# run tests
python -m unittest discover -v tests

# (optional) build exe
py -3.11 -m pip install pyinstaller
.\build_exe.ps1
```

Summary
-------

The test suite covers the critical behaviours of `dagrunner` including selection and filtering, dependency handling, placeholder semantics, task execution modes (shell/script/function), interpreter discovery/override, validation, and logging. Use the `unittest` commands above to run everything or individual modules, inspect log files for integration tests, and set `DAGRUNNER_PYTHON` when you need to force an external interpreter for spawned script/function tasks.

Copy‑pasteable examples (run these now)
-------------------------------------

Below are concrete, copy-pasteable PowerShell commands you can run now. After each command I show the exact log excerpt produced by the run I executed on this repository (so you can compare). Use these to validate your environment and the runner behaviour.

1) Run `test_job` (full job with shell/script/function tasks)

Command (PowerShell):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
python -m dagrunner run -j test_job
```

Find the latest `test_job` log and view it:

```powershell
$p = (gci -File -Filter 'dagrunner_*_test_job.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Raw
```

Expected excerpt (this is an actual log produced when I ran the command):

```text
Interpreter: F:\Environemts\Python\Venvs\dagrunner\Scripts\python.exe
Job: test_job
Start: 2025-11-27 23:04:28.466158

--- Task shell_hello ---
Status: done
Duration: 0.01s
STDOUT:
[shell] hello from shell task

STDERR:

--- Task script_hello ---
Status: done
Duration: 0.03s
STDOUT:
[scripts.hello] Hello from script at 2025-11-27T23:04:28
[scripts.hello] This is STDOUT.

STDERR:
[scripts.hello] Writing something to STDERR...

--- Task func_with_args ---
Status: done
Duration: 0.05s
STDOUT:
[mypkg.entry.add] a=40, b=2, total=42

RETURN VALUE:
42

Job: test_job complete
```

2) Dependency-skip negative case (explicit failing task — dependent should be skipped)

Command (run just the specific unit test that creates `j1`):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
python -m unittest -v tests.unit.test_dependency_skip.TestDependencySkip.test_failed_task_skips_dependent
```

Then view the most recent `j1` log:

```powershell
$p=(gci -File -Filter 'dagrunner_*_j1.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Raw
```

Expected excerpt (actual log I generated):

```text
Interpreter: C:\Program Files\Python314\python3.14t.exe
Job: j1
Start: 2025-11-27 23:03:51.807320

--- Task t1 ---
Status: failed
Duration: 0.05s
STDOUT:

STDERR:
Traceback (most recent call last):
  File "<string>", line 10, in <module>
    rv = func(*a, **k)
  File "C:\Users\damir\AppData\Local\Temp\tmpv8lppv47\mymod.py", line 2, in fail
    raise RuntimeError('boom')
RuntimeError: boom

RETURN VALUE:
None
--- Task t2 ---
Status: skipped
Reason: failed dependencies: ['t1']
Job: j1 complete
```

3) Dependency-ignore positive case (dependent runs despite upstream failure)

Command (run just the specific unit test that creates `j2`):

```powershell
& 'F:\Environemts\Python\Venvs\dagrunner\Scripts\Activate.ps1'
python -m unittest -v tests.unit.test_ignore_deps_flag.TestIgnoreDepsFlag.test_ignore_deps_allows_dependent_to_run
```

Then inspect the latest `j2` log:

```powershell
$p=(gci -File -Filter 'dagrunner_*_j2.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -Raw
```

Expected excerpt (actual log I generated):

```text
Interpreter: C:\Program Files\Python314\python3.14t.exe
Job: j2
Start: 2025-11-27 23:04:05.998001

--- Task t1 ---
Status: failed
Duration: 0.05s
STDOUT:

STDERR:
Traceback (most recent call last):
  File "<string>", line 10, in <module>
    rv = func(*a, **k)
  File "C:\Users\damir\AppData\Local\Temp\tmp78pphfnq\mymod2.py", line 2, in fail
    raise RuntimeError('boom')
RuntimeError: boom

RETURN VALUE:
None

--- Task t2 ---
Status: done
Duration: 0.05s
STDOUT:
ok got None

STDERR:

RETURN VALUE:
None
Job: j2 complete
```

4) Interpreter override example (set `DAGRUNNER_PYTHON`)

This shows how to force a specific interpreter to be used by spawned `script` and `function` tasks. Example:

```powershell
$env:DAGRUNNER_PYTHON = 'C:\Python311\python.exe'
python -m dagrunner run -j test_job

# Check the top of the log to confirm the interpreter path
$p=(gci -File -Filter 'dagrunner_*_test_job.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
Get-Content $p.FullName -TotalCount 5
```

Expected top-of-log line (Interpreter:) will show the path you provided, e.g.:

```text
Interpreter: C:\Python311\python.exe
```

5) Run the test for placeholder exact-match missing (unit test)

Command:

```powershell
python -m unittest -v tests.unit.test_placeholders_missing
```

Expected console output:

```
test_embedded_placeholder_missing_keeps_literal ... ok
test_exact_placeholder_missing_raises ... ok

----------------------------------------------------------------------
Ran 2 tests in X.XXXs

OK
```

6) Run `run_script` and `run_shell` unit test (captures stdout/stderr)

Command:

```powershell
python -m unittest -v tests.unit.test_run_script_shell.TestRunScriptShell.test_run_script_and_shell_capture_output
```

Expected console output: test passes (OK). The test verifies `stdout` contains `OUT` and `stderr` contains `ERR` for the script it creates.

7) Run the CLI help-all check

Command:

```powershell
python -m dagrunner --help-all
```

Expected output: main help text followed by each subcommand's help. You should see usage descriptions for `run`, `validate`, `list`, and `init`.

Finding logs quickly
-------------------

PowerShell snippets to find the most recent logs for a job (replace `test_job`):

```powershell
#$ latest log file path
$p=(gci -File -Filter 'dagrunner_*_test_job.log' | Sort-Object LastWriteTime | Select-Object -Last 1)
if ($p) { Write-Host $p.FullName }

# print last 200 lines of that log
Get-Content $p.FullName -Tail 200
```

If a command creates no log, check that:

- You ran the command from the intended project directory (the runner searches upward for `dagrunner.json`).
- The command used the expected Python environment (the `Interpreter:` line in the log shows which interpreter was used to spawn child processes).

If you want, I can add a new section with a small script that runs these smoke commands and automatically archives their logs into a `tests/logs/` folder for review.
