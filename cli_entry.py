"""Tiny launcher script used for PyInstaller builds.

This imports the package `dagrunner` and invokes its `main()` function.
Putting the small entrypoint in a plain script makes PyInstaller's
module-import behavior predictable and allows `multiprocessing.freeze_support()`
to be called from `__main__` as recommended for frozen executables on Windows.
"""
import multiprocessing

from dagrunner import main


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
