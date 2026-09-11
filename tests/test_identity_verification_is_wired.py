"""The tamper detector, at every call site rather than one.

FOUND BY tools/wiring_probe.py, and the probe exists because of a defect
found retrofitting a guard into a different project: six planted defects
were caught and a seventh was not -- removing a validator's CALL left the
suite green, because every test called the validator directly. The guard
was covered. Its wiring was not.

Run against this repository, the probe plants that defect at all fifteen
guard call sites in the product and reports the ones nothing notices.
`daf/storage/serialization.py` has EIGHT `_verify(...)` sites, one per
persisted artifact type, and only ONE of them was noticed --
`document_from_dict`. The other seven could be deleted with 2535 tests
green.

AND THIS MODULE'S OWN COVERAGE CHECK READ A MOVING TREE. The first draft
listed seven types and omitted Referent, and the derived check below --
which exists precisely to catch that -- reported green, because it was run
while the probe had `referent_from_dict`'s `_verify` line replaced by
`pass`. It counted seven sites and agreed with seven cases. The check was
correct; the tree was mid-mutation. A derived check is only as good as the
snapshot it derives from, which is the same class one level up again, and
it was caught by the probe's own final report disagreeing with it.

WHAT THAT MEANT. `_verify` raises ArtifactIdentityMismatch, described in
its own docstring as "the corruption/tamper detector". So the detector
that establishes a stored artifact still matches its content-addressed
identity was exercised for Document and for nothing else -- including
Observation, which is the object the whole substrate exists to hold. A
tampered Source, Record, Observation, ClaimedRelationship, DerivedValue or
DerivedGrounding would have been re-hydrated without complaint, and no
test would have said so.

The existing module had exactly one tamper test, and the reason is worth
stating plainly: writing one per type reads as repetition, so one gets
written and the rest feel covered. The probe is what makes the difference
between covered and feeling covered measurable.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

from evidence.types import (make_claimed_relationship,  # noqa: E402
                            make_derived_grounding, make_derived_value,
                            make_document, make_observation, make_record,
                            make_referent, make_source)

from daf.storage import serialization  # noqa: E402


def _source():
    return make_source(kind="paper", name="arXiv")


def _document():
    return make_document(source_id="src-1", raw_content="<entry>hello</entry>",
                         retrieval_method="http:arxiv_api_v1",
                         retrieved_at="2026-08-24T00:00:00Z")


def _record():
    return make_record(document_id="doc-1", locator="loc-1",
                       raw_content="<entry>hi</entry>")


def _observation():
    return make_observation(record_ids=("rec-1", "rec-2"),
                            extraction_method="xml:arxiv_atom_v1",
                            content={"title": "T", "arxiv_id": "a1"},
                            confidence=1.0, extracted_at="2026-08-24T00:00:00Z")


def _referent():
    return make_referent(natural_key="Ada Example", kind="author")


def _claimed_relationship():
    return make_claimed_relationship(from_referent_id="r1", to_referent_id="r2",
                                     type="authored_by", observation_id="obs-1",
                                     confidence=1.0)


def _derived_value():
    return make_derived_value(derived_from=("obs-1", "obs-2"), method="average",
                              content={"value": 1.5}, confidence=0.9,
                              derived_at="2026-08-24T00:00:00Z")


def _derived_grounding():
    return make_derived_grounding(derived_value_id="dv-1", referent_ids=("r1", "r2"))


#: One entry per `_verify(...)` site in serialization.py. The type NAME is
#: the literal that site passes, so the coverage assertion below can be
#: derived from the source rather than restated here.
ARTIFACTS = (
    ("Source", _source, "source"),
    ("Document", _document, "document"),
    ("Record", _record, "record"),
    ("Observation", _observation, "observation"),
    ("Referent", _referent, "referent"),
    ("ClaimedRelationship", _claimed_relationship, "claimed_relationship"),
    ("DerivedValue", _derived_value, "derived_value"),
    ("DerivedGrounding", _derived_grounding, "derived_grounding"),
)


def _verified_type_names():
    """The type names `_verify` is actually called with, read from the code.

    Derived rather than listed: a new persisted artifact type arrives here
    unexamined otherwise, which is how a sweep of seven quietly becomes a
    sweep of seven out of nine.
    """
    source = (REPO_ROOT / "daf" / "storage" / "serialization.py").read_text()
    names = set()
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_verify" and node.args):
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                names.add(first.value)
    return names


@pytest.mark.parametrize("type_name,build,prefix",
                         ARTIFACTS, ids=[a[0] for a in ARTIFACTS])
def test_a_tampered_stored_id_is_refused_for_every_artifact_type(type_name, build, prefix):
    """The stored id is altered and the content left alone.

    This is the direction the existing Document test does NOT cover -- it
    changes the content and leaves the id stale. Both must fail, because
    `_verify` compares the two and does not care which side moved.
    """
    to_dict = getattr(serialization, f"{prefix}_to_dict")
    from_dict = getattr(serialization, f"{prefix}_from_dict")

    payload = to_dict(build())
    assert from_dict(dict(payload)) == build(), "the untampered payload must round-trip"

    tampered = dict(payload)
    tampered["id"] = "sha256:" + "0" * 64
    with pytest.raises(serialization.ArtifactIdentityMismatch) as raised:
        from_dict(tampered)
    assert type_name in str(raised.value), (
        "the refusal must name the type, or a reader cannot tell which artifact "
        "on disk is the corrupt one"
    )


def test_every_verify_call_site_is_covered_by_a_case_above():
    """The coverage claim, derived from the source at test time.

    An enumeration standing for a set nobody re-derives is how six
    unwirable call sites came to sit behind one passing tamper test.
    """
    covered = {name for name, _, _ in ARTIFACTS}
    in_code = _verified_type_names()
    assert in_code, "no _verify call sites found -- the sweep is looking at nothing"
    assert in_code == covered, (
        f"serialization.py verifies {sorted(in_code)} and this module covers "
        f"{sorted(covered)}; the difference is unguarded"
    )


# =====================================================================
# The record, bound to what the probe and the code actually do
# =====================================================================

def test_the_record_states_the_measurement_this_tree_still_supports():
    """architecture/guard_wiring.yaml is bound here rather than left
    unbound and allowed for by the doctrine-coverage baseline."""
    from epistemics._yaml import loads

    record = loads((REPO_ROOT / "architecture" / "guard_wiring.yaml").read_text())
    measurement = record["the_measurement"]

    # The site count is re-derived, not restated: the record claims EIGHT
    # _verify sites and the tree must still have eight.
    assert "EIGHT" in measurement["what_the_survivors_were"]
    assert len(_verified_type_names()) == 8

    assert "11 detected, 4 SURVIVED" in measurement["first_run"]
    assert "15 detected, 0 SURVIVED" in measurement["after_the_repair"]
    assert record["status"] == "measured_and_closed"


def test_the_record_keeps_this_sessions_own_miss():
    """The coverage check reported green while omitting Referent, because
    it read a file the probe had mid-mutation. Deleting that paragraph
    would leave a record of a clean repair, which is not what happened."""
    from epistemics._yaml import loads

    record = loads((REPO_ROOT / "architecture" / "guard_wiring.yaml").read_text())
    miss = record["a_derived_check_is_only_as_good_as_the_snapshot_it_derives_from"]
    assert "Referent" in miss["what_happened"]
    assert "may not run concurrently" in miss["the_general_rule_it_yields"]
