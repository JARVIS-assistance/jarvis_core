from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = REPO_ROOT / "jarvis_core" / "src"
CONTRACTS_ROOT = REPO_ROOT / "jarvis_contracts"

for path in (CORE_SRC, CONTRACTS_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
