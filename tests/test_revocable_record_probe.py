"""The revocable-record probe, RUN -- against expectations recorded first.

architecture/_probes/revocable_record_expectations.yaml was committed in
bbd294a, before this file existed. This file READS it.

THE ABSENCE PROBLEM, which makes this probe harder than the cohort one.
Four of five cases predict that something CANNOT be done, and "it did not
work" is also what a WRONG STIMULUS produces. The cohort probe generated
four real refusals from correctly-behaving gates, none about the property
under test; there the ids distinguished them. Here the expected outcome is
an absence, and an absence has no id.

So each case asserts an OBSERVABLE -- a named exception, a returned value,
a post-condition on the bytes -- and never merely that something raised.
One case is a CONTROL that must SUCCEED, which is what shows the refusals
are about identity rather than about writing at all.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage import serialization
from evidence.types import make_observation

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPECTATIONS = loads(
    (REPO_ROOT / "architecture" / "_probes"
     / "revocable_record_expectations.yaml").read_text())
CASES = {case["name"]: case for case in EXPECTATIONS["cases"]}

REMOVAL_NAMES = ("delete", "remove", "retract", "tombstone", "purge")


def _observation(value):
    return make_observation(
        record_ids=("rec-1",),
        extraction_method="regex:gpc",
        content={"property": "number_average_molar_mass", "value": value, "unit": "g/mol"},
        confidence=1.0,
        extracted_at="2026-08-26T00:00:00Z",
    )


# ------------------------------------------------------- probe integrity --

def test_the_expectations_predate_this_run():
    import subprocess

    def added_in(relative):
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", relative],
                             cwd=str(REPO_ROOT), capture_output=True, text=True)
        return out.stdout.split()[-1] if out.stdout.strip() else None

    expectations = added_in("architecture/_probes/revocable_record_expectations.yaml")
    run = added_in("tests/test_revocable_record_probe.py")
    if not expectations or not run:
        pytest.skip("one of the two files is not yet committed")
    assert expectations != run, "expectations and run added in the SAME commit"
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", expectations, run],
                              cwd=str(REPO_ROOT), capture_output=True)
    assert ancestor.returncode == 0, "the run does not descend from the expectations"


def test_every_recorded_case_is_actually_run():
    run_here = {name for name in CASES if f"test_case_{name}" in globals()}
    assert run_here == set(CASES), f"recorded but not run: {sorted(set(CASES) - run_here)}"


# ------------------------------------------------------------ the cases --

def test_case_no_removal_method_exists_on_the_store():
    """Introspect the CLASS, not the source. A grep sees text; a caller
    holds an object, and the object is what has to lack the method."""
    surface = {name for name in dir(FilesystemEvidenceStore) if not name.startswith("_")}
    removals = {name for name in surface
                if any(word in name.lower() for word in REMOVAL_NAMES)}
    assert not removals, (
        f"a removal path exists on the store: {sorted(removals)}. The invariant records "
        f"retraction as ABSENT, which would be wrong, and the bend smaller than recorded.")
    assert surface, "no public surface found -- the introspection is not reaching the class"


def test_case_rewriting_an_id_with_different_content_is_refused():
    """THE RECORDED OBSERVABLE WAS "the store refuses, OR the original
    bytes survive unchanged". The first version of this test asserted only
    the exception -- stricter than the prediction it was written for --
    and reported that content-addressing was broken.

    It is not. Measured: the write returns early WITHOUT writing, the
    original bytes are byte-identical afterwards, and the forged payload
    never reaches disk. The store re-verifies the EXISTING file's identity
    rather than comparing payloads, and the module documents why: a
    payload-equality check would reject legitimate re-acquisitions, since
    confidence and extracted_at are deliberately outside identity.

    AND THE FORGERY NEEDED THE PRIVATE API. put_observation derives the id
    FROM the observation, so a caller cannot supply a mismatched pair. The
    near-miss is the cohort probe's lesson again -- a stimulus that
    bypasses the public surface produces an outcome that is not evidence
    about the public surface -- and this time it would have been a serious
    false claim rather than an inverted one."""
    with tempfile.TemporaryDirectory() as root:
        store = FilesystemEvidenceStore(Path(root))
        original = _observation(104000.0)
        store.put_observation(original)
        path = Path(root) / "observations" / f"{original.id}.json"
        before = path.read_bytes()

        impostor = _observation(999999.0)
        payload = serialization.observation_to_dict(impostor)
        payload["id"] = original.id

        raised = None
        try:
            store._write("observations", original.id, payload,
                         serialization.observation_from_dict)
        except Exception as error:              # noqa: BLE001 -- the type IS the observable
            raised = error

        # the recorded expectation, in the form it was recorded
        assert raised is not None or path.read_bytes() == before, (
            "neither refused NOR left the bytes intact: the forged payload was written, "
            "which would mean content-addressing is not enforced on write")
        assert store.get_observation(original.id).content["value"] == 104000.0
        if raised is not None:
            assert "identity" in str(raised).lower(), (
                f"refused by {type(raised).__name__}, which does not name the identity "
                f"conflict -- a gate reached and a claim unsupported")


def test_case_the_write_is_a_silent_no_op_and_first_write_wins():
    """The behaviour that IS publicly reachable, and the one that matters
    for revocation.

    confidence and extracted_at are outside identity by design -- a
    re-acquisition of the same fact is the same fact. So two observations
    differing only in those fields share an id, and the second
    put_observation is a NO-OP: the FIRST confidence is kept, silently,
    through the public API with no forgery.

    Named here rather than folded into the case above because it is a
    different claim: that one is about content-addressing holding, this
    one is about a caller not being told their write did nothing. If a
    non-identity field cannot be updated, revocation is not a near miss --
    it is far outside what the store does."""
    with tempfile.TemporaryDirectory() as root:
        store = FilesystemEvidenceStore(Path(root))
        first = make_observation(("rec-1",), "regex:gpc",
                                 {"property": "Mn", "value": 104000.0, "unit": "g/mol"},
                                 0.60, "2026-08-26T00:00:00Z")
        second = make_observation(("rec-1",), "regex:gpc",
                                  {"property": "Mn", "value": 104000.0, "unit": "g/mol"},
                                  0.95, "2026-08-27T00:00:00Z")
        assert first.id == second.id, "the premise: same fact, same identity"

        store.put_observation(first)
        store.put_observation(second)           # public API, returns None, raises nothing
        stored = store.get_observation(first.id)

        assert stored.confidence == 0.60, "the re-acquisition's confidence was kept"
        assert stored.extracted_at == "2026-08-26T00:00:00Z"


def test_case_re_persisting_identical_content_is_idempotent_not_a_conflict():
    """THE CONTROL. If this also refused, the case above would be about
    writing twice rather than about identity, and the probe would have
    measured nothing."""
    with tempfile.TemporaryDirectory() as root:
        store = FilesystemEvidenceStore(Path(root))
        observation = _observation(104000.0)
        store.put_observation(observation)
        store.put_observation(observation)          # must not raise
        assert store.get_observation(observation.id).content["value"] == 104000.0


def test_case_nothing_expresses_supersession_between_two_observations():
    """Supersession is deletion's weaker cousin -- keep the bytes, mark
    them replaced. If it existed the bend would be smaller."""
    import evidence.types as types

    names = {n.lower() for n in dir(types)}
    supersession = {n for n in names
                    if any(w in n for w in ("supersede", "replaces", "retract", "revoke"))}
    assert not supersession, f"a supersession vocabulary exists: {sorted(supersession)}"

    # and the one relation type that exists relates REFERENTS, not observations
    fields = types.ClaimedRelationship.__dataclass_fields__
    assert "from_referent_id" in fields and "to_referent_id" in fields
    assert not any("observation" in f for f in fields if f != "observation_id"), (
        "ClaimedRelationship gained an observation-to-observation field")


def test_case_a_revoked_observation_would_orphan_downstream_state():
    """The consequence the invariant records, checked structurally rather
    than asserted: a downstream type references an observation BY ID with
    no back-reference, so removing the observation leaves it dangling."""
    import evidence.types as types

    referencing = {}
    for name in dir(types):
        attribute = getattr(types, name)
        fields = getattr(attribute, "__dataclass_fields__", None)
        if not fields or name == "Observation":
            continue
        pointing = [f for f in fields if "observation_id" in f]
        if pointing:
            referencing[name] = pointing
    assert referencing, (
        "nothing references an observation by id, so removal would orphan nothing -- "
        "the recorded consequence would be wrong")

    observation_fields = set(types.Observation.__dataclass_fields__)
    assert not any("referenced_by" in f or "referents" in f for f in observation_fields), (
        "Observation carries a back-reference, so removal could be repaired by walking it")
