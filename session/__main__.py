"""`python3 -m session plan <queue.json>` / `close <queue> <capture>`."""

from __future__ import annotations

import sys

from session.intake import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
