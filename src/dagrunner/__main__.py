"""Entrypoint for dagrunner when run as a module or when frozen by PyInstaller.

Use a relative import when running as a package in normal Python, but fall
back to an absolute import when the module is executed as a script (PyInstaller
may execute __main__.py without package context, causing relative imports to fail).
"""
try:
    # Preferred when running via `python -m dagrunner` or installed package
    from . import main
except Exception:
    # Fallback for frozen/executable contexts where package context isn't set
    from dagrunner import main


if __name__ == "__main__":
    # On Windows, frozen executables need to call freeze_support() to allow
    # multiprocessing spawn to initialize correctly. This also makes the
    # frozen child processes handle the special bootstrap args (like
    # 'parent_pid=...') that PyInstaller uses.
    try:
        import multiprocessing
        multiprocessing.freeze_support()
    except Exception:
        pass
    main()
