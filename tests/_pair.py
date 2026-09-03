"""Where the jointly-held pair actually lives, and how to ask.

THE PROBLEM THIS SOLVES, MEASURED ON 2026-09-03. Three tests reported
`proof_integrity.yaml has DIVERGED across the pair`. It had not. Both
parties carried byte-identical copies at their own heads
(c9be09961d3440684c781fee7c2ce72be84a9507907240c887390ccf012c5f36).
What had happened is that the acquisition layer authored two new class
instances, the compute layer mirrored them, and the SIBLING CHECKOUT ON
THIS MACHINE was four commits behind at ee346ba while its remote was at
2b30dd1.

So the verdict was about a checkout and was reported as a verdict about
the pair. A local sibling directory is versioned with nothing: it is
whatever someone last pulled into it, and comparing a committed artifact
against it answers `do these two directories agree right now`, which is
not the question the joint-reissue rule cares about.

`architecture/unverified_window.yaml` already recorded this shape for
canonical_yaml.py. This module is the repair for the pair itself.

WHAT ASKING COSTS. Every git call goes through `_git`, which sets
GIT_NO_LAZY_FETCH=1 -- in a partial clone a presence query FETCHES the
object and answers yes, so the question creates its own answer -- and
GIT_TERMINAL_PROMPT=0, because a credential hang reports nothing at all.
Both are the acquisition layer's own findings, filed in
architecture/proof_integrity.yaml. Full forty-character shas everywhere:
an abbreviation must resolve against a local object database, so it
misses locally and never reaches the remote at all.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The two artifacts both parties hold byte-identically. Editing either is
#: a joint reissue and never one party's act.
SHARED = ("proof_integrity.yaml", "kalman_validation_preregistration.yaml")

COUNTERPARTY_URL = "https://github.com/notationsystems/scientific-compute-layer-scl-"
COUNTERPARTY_BRANCH = "refs/heads/claude/scl-architecture-design-0jzkm9"

#: A remote read is real network. It runs when the network answers and
#: reports that it could not when it does not -- never silently.
NETWORK_TIMEOUT_SECONDS = 60


def _git(*arguments: str, cwd=None, timeout: int = 30):
    environment = dict(os.environ)
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(["git", *arguments], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, timeout=timeout,
                          env=environment)


def counterparty_head() -> Optional[str]:
    """The full sha the counterparty's branch points at, or None if the
    network did not answer. Refs, not object reachability: GitHub serves a
    fork's whole network from one object store, so `does this remote have
    commit C` is true across every fork and identifies nothing."""
    result = _git("ls-remote", COUNTERPARTY_URL, COUNTERPARTY_BRANCH,
                  timeout=NETWORK_TIMEOUT_SECONDS)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if "\t" in line:
            sha = line.split("\t", 1)[0].strip()
            if len(sha) == 40:
                return sha
    return None


def pair_at_counterparty_head(head: str) -> Optional[Dict[str, bytes]]:
    """The shared artifacts as the counterparty actually holds them.

    Fetched into a throwaway repository so nothing on this machine is
    touched -- in particular NOT the sibling checkout, which belongs to
    another party and which this layer reports on rather than edits.
    """
    if len(head) != 40:
        raise ValueError("a full forty-character sha is required; an abbreviation "
                         "resolves locally and never reaches the remote")
    with tempfile.TemporaryDirectory() as scratch:
        if _git("init", "-q", ".", cwd=scratch).returncode != 0:
            return None
        fetched = _git("fetch", "--depth", "1", COUNTERPARTY_URL, head,
                       cwd=scratch, timeout=NETWORK_TIMEOUT_SECONDS)
        if fetched.returncode != 0:
            return None
        contents = {}
        for name in SHARED:
            shown = _git("cat-file", "-p", f"{head}:architecture/{name}", cwd=scratch)
            if shown.returncode != 0:
                return None
            contents[name] = shown.stdout.encode()
        return contents


def local_sibling_is_current() -> Tuple[Optional[bool], str]:
    """Is the sibling checkout on this machine at its remote head?

    (None, reason) when it cannot be established -- no checkout, or no
    network. A comparison against a sibling that is NOT current cannot
    distinguish a divergence from a stale pull, and reporting one as the
    other is what this module exists to stop.
    """
    sibling = pathlib.Path("/home/user/scientific-compute-layer-scl-")
    if not (sibling / ".git").exists():
        return None, "no sibling checkout on this machine"
    head = _git("rev-parse", "HEAD", cwd=sibling)
    if head.returncode != 0:
        return None, "the sibling checkout has no resolvable HEAD"
    remote = counterparty_head()
    if remote is None:
        return None, "the network did not answer; the sibling's currency is unknown"
    return head.stdout.strip() == remote, f"sibling {head.stdout.strip()[:8]} vs remote {remote[:8]}"

