import importlib.machinery
import importlib.util
import sys
from pathlib import Path

# Load src/systemd_search/__init__.py directly so tests run without
# requiring the package to be pip-installed.
_path = str(Path(__file__).parent.parent / "src" / "systemd_search" / "__init__.py")
_loader = importlib.machinery.SourceFileLoader("systemd_search", _path)
_spec = importlib.util.spec_from_loader("systemd_search", _loader)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["systemd_search"] = _mod
