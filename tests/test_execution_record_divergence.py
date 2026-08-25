"""The ExecutionRecord divergence resolution, locked before the second
kind exists.

`architecture/execution_record.yaml`'s `divergence_resolution` fixes the
SHAPE of a unified record (shape A: an explicit `kind` discriminant over a
shared core) without performing the schema migration, because no
computation kind exists here yet to discriminate toward. That leaves a
decision recorded in prose and nothing holding it, which is the exact
failure mode this repository has refused before -- a status naming a check
nobody wrote is worse than a status of `absent`.

So the parts that CAN be checked now are checked now:

  * the shared core is the INTERSECTION of the two field sets, not the
    union and not a generalization -- a field may not appear in the core
    unless it genuinely means the same thing for both kinds;
  * the core is exactly what today's real `ExecutionRecord` dataclass
    already provides, so adopting the shape costs the acquisition kind
    no field;
  * the refused merges stay refused -- each names two fields that a later
    phase might quietly unify, and unifying any of them would change what
    `content_digest` covers;
  * today's record is unchanged, so this file locks a decision without
    enacting it.

This is Phase 25's posture applied to a schema: author the rule before
there is a binding to accommodate, so the first binding anyone adds is
checked by a rule that did not bend around it.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.execution.record import ExecutionRecord
from epistemics._yaml import loads

ARCHITECTURE = Path(__file__).resolve().parent.parent / "architecture"


@pytest.fixture(scope="module")
def resolution():
    document = loads((ARCHITECTURE / "execution_record.yaml").read_text())
    return document["divergence_resolution"]


def _core_names(resolution):
    """The shared core is written as a YAML sequence whose entries are
    either a bare name or a one-key mapping of name to rationale."""
    names = []
    for entry in resolution["shared_core"]:
        names.append(next(iter(entry)) if isinstance(entry, dict) else entry)
    return names


# ------------------------------------------------ the shape is decided

def test_exactly_one_shape_is_adopted(resolution):
    verdicts = [shape["verdict"] for shape in resolution["shapes_considered"]]
    assert verdicts.count("adopted") == 1, "the divergence needs ONE chosen shape"
    adopted = next(s for s in resolution["shapes_considered"] if s["verdict"] == "adopted")
    assert adopted["id"] == "A_discriminated_kind_with_shared_core"
    assert resolution["status"] == "decided"


def test_every_rejected_shape_states_why(resolution):
    """A rejection without a reason is a preference."""
    for shape in resolution["shapes_considered"]:
        if shape["verdict"] == "rejected":
            assert shape["reason"], f"{shape['id']} was rejected without a reason"


# ------------------------------------- the core is the INTERSECTION

def test_the_shared_core_is_disjoint_from_both_kind_specific_blocks(resolution):
    """A field in the core must not also be claimed by one kind: that
    would make it kind-specific and shared at once."""
    core = set(_core_names(resolution))
    acquisition = set(resolution["acquisition_only"])
    computation = set(resolution["computation_only"])
    assert core & acquisition == set(), core & acquisition
    assert core & computation == set(), core & computation
    assert acquisition & computation == set(), "the two kind blocks must not overlap"


def test_the_shared_core_is_not_the_union(resolution):
    """The intersection discipline, stated as a check. If the core ever
    grows to swallow a kind-specific block, this fails."""
    core = set(_core_names(resolution))
    assert core, "an empty core would mean shape C (rename) was the right answer"
    for kind in ("acquisition_only", "computation_only"):
        assert resolution[kind], f"{kind} is empty -- then there is nothing to discriminate"
        assert not set(resolution[kind]) <= core


def test_the_core_costs_the_acquisition_kind_no_field(resolution):
    """Every core field is one today's real record already has, so
    adopting the shape is additive for acquisition rather than a
    redefinition. Measured against the dataclass, not against the doc."""
    actual = {f.name for f in dataclasses.fields(ExecutionRecord)}
    missing = set(_core_names(resolution)) - actual
    assert not missing, f"the core claims fields the real record lacks: {missing}"


def test_every_acquisition_only_field_is_real(resolution):
    actual = {f.name for f in dataclasses.fields(ExecutionRecord)}
    missing = set(resolution["acquisition_only"]) - actual
    assert not missing, f"acquisition_only names fields the record lacks: {missing}"


def test_the_core_and_acquisition_block_together_account_for_the_whole_record(resolution):
    """Nothing in today's record may be silently unclassified: every
    existing field is either shared or acquisition-specific."""
    actual = {f.name for f in dataclasses.fields(ExecutionRecord)}
    classified = set(_core_names(resolution)) | set(resolution["acquisition_only"])
    assert actual - classified == set(), f"unclassified fields: {actual - classified}"


# ------------------------------------------------ the refused merges

def test_the_refused_merges_are_recorded_with_reasons(resolution):
    """Each names two fields a later phase might quietly unify. The
    reasons are the whole value -- without them the next reader sees an
    arbitrary restriction and removes it."""
    refused = resolution["refused_merges"]
    assert set(refused) == {
        "adapter_version_and_backend_version",
        "outcome_and_verification_status",
        "output_fingerprint_and_computation_identity",
    }
    for name, reason in refused.items():
        assert len(reason) > 80, f"{name} is refused without a real reason"


def test_no_refused_merge_smuggled_a_field_into_the_core(resolution):
    """The three refusals concern six field names. Any of them appearing
    in the shared core would mean the merge happened after all."""
    core = set(_core_names(resolution))
    for merged in ("adapter_version", "backend_version", "outcome",
                   "verification_status", "computation_identity"):
        assert merged not in core, f"{merged} reached the core despite a refused merge"
    # output_fingerprint IS in the core -- on its own terms, as a hash of
    # the output. What is refused is redefining it as computation_identity.
    assert "output_fingerprint" in core


# --------------------------------- the decision is recorded, not enacted

def test_todays_record_is_unchanged(resolution):
    """The shape is fixed; the migration is not performed. If someone
    adds `kind` without also revisiting the migration cost recorded in
    the architecture file, this fails."""
    actual = {f.name for f in dataclasses.fields(ExecutionRecord)}
    assert "kind" not in actual
    timing = resolution["implementation_timing"]
    assert timing["decision"].startswith("the SHAPE is fixed now")
    # Not a bend, and the answer must say WHICH invariants keep their
    # meaning -- "no" without naming them is an assurance, not a check.
    verdict = timing["is_this_a_bend"]
    assert verdict.lower().startswith("no")
    for invariant in ("execution_recorded", "execution_is_not_evidence",
                      "execution_identity_is_separate"):
        assert invariant in verdict


def test_the_migration_cost_is_stated_rather_than_discovered(resolution):
    """Introducing `kind` re-digests every stored record. That is the
    cost, and it is written down before anyone pays it."""
    cost = resolution["migration_cost"]
    assert "id_unchanged" in cost and "content_digest_changes" in cost
    assert "ExecutionIntegrityMismatch" in cost["content_digest_changes"]
