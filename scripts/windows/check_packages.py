"""List the Python packages used by the project; a package that is installed but cannot load (e.g. libsumo with a
missing DLL) is reported instead of stopping the listing (added 2026-10-15)."""
import importlib
import importlib.util

for m in ["traci", "sumolib", "libsumo", "pandas", "numpy", "pytest", "fastapi", "uvicorn", "httpx", "openpyxl", "requests", "matplotlib"]:
    if importlib.util.find_spec(m) is None:
        print(m, "MISSING")
        continue
    try:
        print(m, getattr(importlib.import_module(m), "__version__", "ok"))
    except Exception as exc:  # noqa: BLE001
        print(m, "INSTALLED BUT FAILS TO LOAD:", type(exc).__name__, exc)
