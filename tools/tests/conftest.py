"""pytest configuration — adds repo root to sys.path for habanero imports."""

from __future__ import annotations

import os
import sys

# Allow test files to import habanero package without install
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
