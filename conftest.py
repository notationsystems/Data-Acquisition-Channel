"""Ensures the vendored State-Space repository is importable before any
test does `from scout.interface import ...` / `from evidence... import ...`.
See daf/_vendor.py."""

from __future__ import annotations

import daf  # noqa: F401
