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

---

## 📦 Installation

To build the standalone executable:

```bash
pip install pyinstaller
pyinstaller --onefile dagrunner.py
```

Run it with:

```bash
./dist/dagrunner run
```

Or add it globally to your PATH for convenience.

---

## 🚀 CLI Usage

🆕 Initialize a Project

```bash
dagrunner init
```

Creates a sample dagrunner.json in the current directory.

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

## ⚠️ Limitations

- 🚫 No distributed/cloud execution

- ❌ No retries, retries-on-failures, or scheduling

- 🖼 No DAG visualization

---

## 🪪 License
MIT