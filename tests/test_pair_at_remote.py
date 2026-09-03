"""The joint-reissue verdict, taken where the counterparty actually is.

A local sibling directory is versioned with nothing. Comparing a
committed artifact against it answers "do these two directories agree
right now", and on 2026-09-03 that produced three reports of
`proof_integrity.yaml has DIVERGED across the pair` for a pair that was
byte-identical at both parties' heads.

This module asks the question the joint-reissue rule is actually about.
It requires the network and says so when it cannot run, rather than
passing.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tests"))
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

from _pair import (COUNTERPARTY_BRANCH, COUNTERPARTY_URL, SHARED,  # noqa: E402
                   counterparty_head, local_sibling_is_current,
                   pair_at_counterparty_head)


def _ours(name: str) -> bytes:
    return (REPO_ROOT / "architecture" / name).read_bytes()


def test_the_shared_pair_is_byte_identical_at_both_parties_heads():
    """The real verdict.

    Fails in the state the joint-reissue rule exists for: one party
    editing a shared artifact and the other not carrying the edit. It
    SKIPS, loudly, when the network does not answer -- a pair check that
    passed offline would be asserting nothing about the counterparty.
    """
    head = counterparty_head()
    if head is None:
        pytest.skip("the network did not answer; the counterparty's head is unknown and "
                    "this verdict cannot be taken. Not a pass.")

    theirs = pair_at_counterparty_head(head)
    if theirs is None:
        pytest.skip(f"the counterparty's head {head[:8]} could not be fetched; not a pass")

    assert set(theirs) == set(SHARED)
    for name in SHARED:
        assert hashlib.sha256(theirs[name]).hexdigest() == hashlib.sha256(_ours(name)).hexdigest(), (
            f"architecture/{name} has genuinely DIVERGED across the pair, measured at "
            f"the counterparty's head {head}. This is the joint-reissue rule being broken, "
            "not a stale checkout."
        )


def test_a_stale_local_sibling_is_reported_as_staleness_and_not_as_divergence():
    """The finding this module was built for, held as a property.

    On the day it was written the sibling was four commits behind and the
    pair agreed. If the sibling is current, there is nothing to
    distinguish and the test says so rather than passing silently.
    """
    current, reason = local_sibling_is_current()
    if current is None:
        pytest.skip(f"currency could not be established: {reason}")

    if current:
        # Nothing to distinguish today. Stated rather than passed over:
        # a green here means the two questions happen to coincide.
        assert "vs remote" in reason
        return

    # The sibling is behind. A byte comparison against it may disagree
    # with the pair's actual state, and that is precisely the false
    # DIVERGED this module exists to stop being reported.
    head = counterparty_head()
    theirs = pair_at_counterparty_head(head) if head else None
    if theirs is None:
        pytest.skip("the counterparty could not be read; the distinction cannot be shown")

    sibling = pathlib.Path("/home/user/scientific-compute-layer-scl-/architecture")
    disagreed_locally = []
    for name in SHARED:
        local_copy = sibling / name
        if local_copy.exists() and local_copy.read_bytes() != _ours(name):
            disagreed_locally.append(name)

    for name in disagreed_locally:
        assert theirs[name] == _ours(name), (
            f"architecture/{name} disagrees with the stale sibling AND with the "
            "counterparty's head; that is a real divergence"
        )


def test_the_helper_cannot_quietly_stop_disabling_the_lazy_fetch():
    """A presence query in a partial clone FETCHES the object and answers
    yes -- the question creates its own answer. The guard is not the
    environment variable; it is that no git call is written around it.
    """
    source = (REPO_ROOT / "tests" / "_pair.py").read_text()
    body = source.split("def _git(", 1)[1].split("\ndef ", 1)[0]
    assert 'environment["GIT_NO_LAZY_FETCH"] = "1"' in body
    assert 'environment["GIT_TERMINAL_PROMPT"] = "0"' in body

    # Everything that is NOT the _git body. Reconstructed by removing the
    # body rather than by splitting on the first `def`, which put _git's
    # own subprocess call back into the remainder and failed on itself.
    outside = source.replace(body, "")
    assert "subprocess.run" not in outside, (
        "a git call is written around the helper; the protections are per-call, so a "
        "call that bypasses them has none of them"
    )


def test_every_sha_the_helper_sends_to_a_remote_is_unabbreviated():
    """An abbreviation must resolve against a LOCAL object database, so it
    misses locally and never reaches the remote. Six false `no longer
    served` alarms in this repository came from exactly that."""
    from _pair import pair_at_counterparty_head as fetcher
    with pytest.raises(ValueError, match="forty-character"):
        fetcher("c9be0996")


def test_the_counterparty_is_named_by_url_and_branch_rather_than_by_a_directory():
    """A directory on this machine is not an identity. The rule the whole
    module rests on."""
    assert COUNTERPARTY_URL.startswith("https://github.com/notationsystems/")
    assert COUNTERPARTY_BRANCH.startswith("refs/heads/")
    assert set(SHARED) == {"proof_integrity.yaml", "kalman_validation_preregistration.yaml"}


# =====================================================================
# The record this module enforces, bound to what it measures
# =====================================================================

RECORD = loads((REPO_ROOT / "architecture"
                / "pair_verification_subject.yaml").read_text())


def test_the_record_states_the_digests_the_pair_actually_carries():
    """The record names two sha256 values it measured. If they were prose
    they would be bound to nothing.

    Fails in the state where the pair moves and the record does not --
    which is the whole point of a reissue being a joint act.
    """
    happened = RECORD["what_happened"]["what_was_actually_true"]
    for name in SHARED:
        digest = hashlib.sha256(_ours(name)).hexdigest()
        assert digest in happened, (
            f"architecture/{name} now hashes to {digest} and the record states an older "
            "value. A reissue moves the pair; the record of it is re-measured, not edited "
            "to agree."
        )


def test_the_record_names_the_substitution_rather_than_the_incident():
    """A record of one bad afternoon is worth less than a record of the
    shape. This one has to carry the general form."""
    assert RECORD["status"] == "measured_and_repaired_for_this_layer"
    assert "location and not an identity" in RECORD["the_general_form_worth_carrying"]
    # And the record must carry its own retraction rather than a tidied
    # version of what it first claimed.
    retraction = RECORD["the_two_tests_this_record_first_said_it_would_leave_alone"]
    assert "are not edited here" in retraction["what_it_said"]
    assert "handing over a broken instrument" in retraction["why_that_was_wrong"]
    assert "watched both fire before restoring" in retraction["what_was_actually_done"]
