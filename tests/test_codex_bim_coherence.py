"""The Codex/BIM coherence record, bound to what it asserts.

Like tests/test_twin_codex_coherence.py, this does not re-run the network
measurements -- that would make the suite depend on another repository's
current state and on the network. What is checked is the SHAPE of the
claims: that every alignment is a quotation and not a paraphrase, that
every divergence names what it does not claim, that the scope is stated in
the record rather than left to be inferred, and that the sp1 half does not
report a version agreement as a protocol agreement.

The one thing here that IS re-derived rather than asserted is the sha
format. A record whose evidence is a fetch of a forty-character sha is
worth nothing if it writes down twelve of them, and this pair has had that
exact trap spring twice.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

PATH = REPO_ROOT / "architecture" / "codex_bim_coherence.yaml"
RECORD = loads(PATH.read_text())


def _values(node):
    """Every leaf string in the record. Derived, so a section added later
    is covered without editing anything here."""
    if isinstance(node, dict):
        for value in node.values():
            yield from _values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _values(value)
    elif isinstance(node, str):
        yield node


def test_every_commit_this_record_rests_on_is_written_unabbreviated():
    """The trap that sprang twice in this pair. An abbreviated sha must
    resolve against a LOCAL object database before any remote is asked, so
    a record that carries twelve characters cannot be re-measured by the
    method it claims to have used."""
    text = PATH.read_text()
    # any hex run of 7..39 that is not part of a longer one
    short = re.findall(r"(?<![0-9a-f])[0-9a-f]{7,39}(?![0-9a-f])", text)
    # a bare decimal-looking run is not a sha; require at least one a-f
    short = [s for s in short if re.search(r"[a-f]", s)]
    assert not short, (
        "abbreviated shas in a record whose evidence is a remote fetch: "
        f"{short}. Forty characters or the claim cannot be re-run."
    )
    full = re.findall(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", text)
    assert len(full) >= 3, f"expected the three read branch tips, found {len(full)}"


def test_each_alignment_carries_a_quotation_rather_than_a_paraphrase():
    """Four independent arrivals at one rule is the most flattering
    possible reading of an artifact, and the most tempting to write up from
    memory. Every claim of agreement must quote the other party."""
    section = RECORD["where_codex_arrived_independently_at_this_pairs_doctrine"]
    claims = {k: v for k, v in section.items() if k != "the_caveat_first"}
    assert len(claims) >= 5, "the section has lost its content"
    for name, text in claims.items():
        assert "`" in text, (
            f"{name} claims agreement without quoting it. A paraphrase of "
            "another party's document is this session's own words attributed "
            "to them."
        )


def test_the_convergence_caveat_is_stated_before_the_convergence():
    """proof_integrity.yaml demotes convergence to a PROMPT TO RE-MEASURE.
    A record that lists five agreements has to carry that demotion where a
    reader meets it first, not in a footnote."""
    section = RECORD["where_codex_arrived_independently_at_this_pairs_doctrine"]
    assert list(section)[0] == "the_caveat_first", (
        "the caveat is no longer the first thing in the section"
    )
    caveat = section["the_caveat_first"]
    assert "convergence_is_not_evidence" in caveat
    assert "no claim that the agreement proves either party right" in caveat


def test_the_divergence_says_what_it_does_not_claim():
    divergence = RECORD["the_divergence_that_is_concrete_and_measured"]
    assert "what_is_NOT_claimed" in divergence
    not_claimed = divergence["what_is_NOT_claimed"]
    assert "not claimed" in not_claimed or "NOT_claimed" in not_claimed or (
        "wrong to lack it" in not_claimed)
    # and it must not quietly resolve the open proposal it bears on
    assert "not amended here" in divergence["what_it_changes_for_the_open_proposal"]


def test_the_open_proposal_it_cites_is_actually_open():
    """A record citing a proposal as open, over a proposal that was
    resolved, is a stale referent -- the class this session found four
    kinds of in one night."""
    cited = "architecture/proposals/2026-09-03-uncertainty-kind-as-a-contract-axis.yaml"
    path = REPO_ROOT / cited
    assert path.exists(), f"{cited} is cited by the record and is not there"
    proposal = loads(path.read_text())
    status = str(proposal.get("status", ""))
    assert "resolved" not in status.lower(), (
        f"the record calls this proposal open and its status is {status!r}"
    )


def test_the_version_agreement_is_not_reported_as_a_protocol_agreement():
    """The specific substitution available here: three implementations
    pinning one prover version reads like interoperability and is not."""
    sp1 = RECORD["the_sp1_question_this_settles_and_the_one_it_does_not"]
    assert "what_it_does_not_settle" in sp1
    assert "necessary and nowhere near sufficient" in sp1["what_it_does_not_settle"]
    assert sp1["the_honest_status"].startswith("unchanged")


def test_the_scope_is_stated_in_the_record_and_not_left_to_be_inferred():
    measurement = RECORD["the_measurement"]
    assert "what_was_not_read" in measurement, (
        "a record that read three of twelve branches must say so itself"
    )
    assert "nine" in measurement["what_was_not_read"]
    must_not = RECORD["what_this_record_must_not_become"]
    assert "what_would_change_the_verdict" in must_not


def test_the_bounded_instrument_is_reported_as_the_existing_class():
    """It would be flattering to file this as a new discovery. It is the
    class already in the shared record, in a sharper form, and saying so is
    what keeps that record a class rather than a list."""
    bounded = RECORD["the_instrument_was_bounded_by_the_thing_it_was_auditing"]
    reason = bounded["why_this_is_the_same_class_and_not_a_new_one"]
    assert "coverage_specified_by_enumeration" in reason
    assert "Deriving from the tree is not enough" in reason
    assert bounded["what_it_reported"].startswith("six")
    assert "EIGHTEEN" in bounded["what_is_actually_there"]


def test_the_register_hole_is_stated_and_not_quietly_patched():
    """Naming four absent members and adding them in the same commit would
    make the register pass a check that nothing had measured. The hole is
    recorded with its evidence so the repair is made against the
    measurement."""
    bounded = RECORD["the_instrument_was_bounded_by_the_thing_it_was_auditing"]
    hole = bounded["and_the_register_still_does_not_hold_it"]
    register = (REPO_ROOT / "architecture" / "ecosystem_register.yaml").read_text()
    for absent in ("BIM-State-Transformer-Engine", "Payload-Render-Engine",
                   "Notations-Corpus-Graph", "PayLoad-OCR-Agent"):
        assert absent in hole, f"{absent} is not named in the hole this record states"
        assert absent not in register, (
            f"{absent} is now a register member and this record still calls it "
            "absent. The record is the thing that goes stale here, and it is "
            "the thing to correct."
        )


def test_the_two_codex_records_are_bound_to_each_other():
    """The group mechanism, used rather than restated. Both records declare
    codex_coherence and each names the other; the register's group check
    then holds them together, including if one is renamed away."""
    twin = loads(
        (REPO_ROOT / "architecture" / "twin_codex_coherence.yaml").read_text())
    assert twin["subject_group"] == RECORD["subject_group"] == "codex_coherence"
    assert "architecture/codex_bim_coherence.yaml" in twin["records_sharing_this_subject"]
    assert "architecture/twin_codex_coherence.yaml" in RECORD["records_sharing_this_subject"]
