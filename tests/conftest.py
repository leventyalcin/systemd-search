import importlib.util
import importlib.machinery
import sys
from pathlib import Path

# Import the hyphen-named, extension-less script as a Python module
_path = str(Path(__file__).parent.parent / "systemd-search")
_loader = importlib.machinery.SourceFileLoader("systemd_search", _path)
_spec = importlib.util.spec_from_loader("systemd_search", _loader)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
sys.modules["systemd_search"] = _mod
