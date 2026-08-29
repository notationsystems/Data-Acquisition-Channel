"""`generation_depth_bounded`, closed: bounded, recorded, and guarded.

WHAT WAS TRUE BEFORE. The invariant read "derivation from derivation is
bounded and the depth is recorded" and was implemented in NEITHER clause
-- measured: no depth symbol existed anywhere, `DerivedValue` carried no
depth field, the invariant declared no bound value, and `ancestry_of`
returned a flat set that discards the level at which each node was
reached. Its status has been `represented_unenforced` since the
correction that found the earlier evidence proved acyclicity rather than
boundedness.

THE COMPOSITION GUARD IS WHAT THIS FILE EXISTS TO PIN. The recorded
semantic domain's last clause covers INITIALIZATION only -- "where
initialization derives from a computed prior, lineage depth inherits from
that prior" -- and initialization alone does not close chaining. A filter
initialized from a fresh measured state but consuming another filter's
OUTPUT reports depth 0 under an initialization-only rule, while standing
one lineage step further from measurement than the filter it consumes.

That is the hole, and `test_an_initialization_only_rule_admits_the_hole`
plants it and watches it open, which is this repository's required step
for trusting a new check.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from science import lineage_depth as ld
from science.lineage_depth import (
    MAX_LINEAGE_DEPTH,
    DepthAccount,
    declares_recursion,
    lineage_depth,
    recursive_computation_is_depth_bounded,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A small lineage: A is grounded, B is one step out, C two, D three.
DEPTHS = {"filter-A": 0, "filter-B": 1, "filter-C": 2, "filter-D": 3}


def depth_of(prior_id):
    return DEPTHS[prior_id]


MEASURED_INIT = {"kind": "measured"}


def computed_init(prior):
    return {"kind": "computed", "prior_id": prior}


def measured_stream(stream_id="noaa-8454000"):
    return {"stream_id": stream_id, "kind": "measured"}


def computed_stream(stream_id, producer):
    return {"stream_id": stream_id, "kind": "computed", "prior_id": producer}


def record(streams=None, initialization=None, depth=0, window="10 samples"):
    return {
        "stream_identity": [measured_stream()] if streams is None else streams,
        "window_or_horizon": window,
        "initialization_provenance": MEASURED_INIT if initialization is None else initialization,
        "lineage_depth": depth,
    }


# ------------------------------------------------- 1. depth 0 means depth 0


def test_a_grounded_computation_is_depth_zero():
    content = record()
    assert recursive_computation_is_depth_bounded(content, depth_of).admissible
    assert lineage_depth(content, depth_of).depth == 0


def test_depth_zero_requires_BOTH_measured_initialization_and_measured_streams():
    """The property, stated as the definition rather than as two separate
    checks: nothing reaches 0 except a record whose every source is
    measured."""
    assert lineage_depth(record(), depth_of).depth == 0

    from_computed_init = record(initialization=computed_init("filter-A"), depth=1)
    assert lineage_depth(from_computed_init, depth_of).depth == 1

    from_computed_stream = record(
        streams=[computed_stream("a-out", "filter-A")], depth=1)
    assert lineage_depth(from_computed_stream, depth_of).depth == 1


# ------------------------------------ 2. the initialization clause, as recorded


@pytest.mark.parametrize("prior,expected", [("filter-A", 1), ("filter-B", 2), ("filter-C", 3)])
def test_initialization_from_a_computed_prior_is_prior_depth_plus_one(prior, expected):
    """Quoted from the semantic domain: "where initialization derives from
    a computed prior, lineage depth inherits from that prior"."""
    content = record(initialization=computed_init(prior), depth=expected)
    assert lineage_depth(content, depth_of).depth == expected
    assert recursive_computation_is_depth_bounded(content, depth_of).admissible


# ------------------------------------------------- 3. THE COMPOSITION GUARD


def test_a_filter_fed_by_another_filter_is_not_depth_zero():
    """THE HOLE, closed. Fresh measured initialization, but the stream it
    consumes is another filter's output. One lineage step beyond that
    filter, and an initialization-only reading calls it grounded."""
    chained = record(streams=[computed_stream("a-out", "filter-A")], depth=0)

    account = lineage_depth(chained, depth_of)
    assert account.depth == 1
    assert account.from_initialization == 0, "the initialization really is measured"
    assert account.from_streams == (("a-out", 1),)
    assert account.inherited_from_a_stream

    verdict = recursive_computation_is_depth_bounded(chained, depth_of)
    assert not verdict.admissible
    assert ld.DECLARED_DEPTH_DISAGREES_WITH_LINEAGE in verdict.reasons

    honest = record(streams=[computed_stream("a-out", "filter-A")], depth=1)
    assert recursive_computation_is_depth_bounded(honest, depth_of).admissible


def test_an_initialization_only_rule_admits_the_hole():
    """PLANT THE DEFECT AND WATCH IT OPEN -- the required step before
    trusting any check here. The rule as the semantic domain literally
    states it, implemented alone, calls the chained filter grounded."""

    def initialization_only(content):
        initialization = content["initialization_provenance"]
        if initialization["kind"] == "measured":
            return 0
        return depth_of(initialization["prior_id"]) + 1

    chained = record(streams=[computed_stream("a-out", "filter-A")], depth=0)
    assert initialization_only(chained) == 0, "the rule being guarded against"
    assert lineage_depth(chained, depth_of).depth == 1, "what the guard says instead"


def test_the_deepest_source_wins_whichever_kind_it_is():
    """Depth is a maximum over both kinds of source, so neither can be
    hidden behind the other. A shallow initialization does not mask a deep
    stream, and a shallow stream does not mask a deep initialization."""
    deep_stream = record(
        streams=[measured_stream(), computed_stream("c-out", "filter-C")],
        initialization=MEASURED_INIT, depth=3)
    assert lineage_depth(deep_stream, depth_of).depth == 3

    deep_init = record(
        streams=[measured_stream()], initialization=computed_init("filter-C"), depth=3)
    assert lineage_depth(deep_init, depth_of).depth == 3

    both = record(
        streams=[computed_stream("a-out", "filter-A")],
        initialization=computed_init("filter-C"), depth=3)
    assert lineage_depth(both, depth_of).depth == 3


def test_iteration_count_is_still_not_lineage_depth():
    """The domain's other clause, which the composition guard must not
    quietly undo: "a recursive estimator running N iterations over one
    measurement stream is one lineage step, not N"."""
    for window in ("10 samples", "10000 samples", "the whole record"):
        content = record(window=window)
        assert lineage_depth(content, depth_of).depth == 0, window


# --------------------------------------------------------- 4. the bound


def test_the_bound_exists_is_declared_and_bites():
    assert isinstance(MAX_LINEAGE_DEPTH, int) and MAX_LINEAGE_DEPTH > 0
    over = record(streams=[computed_stream("d-out", "filter-D")], depth=4)
    verdict = recursive_computation_is_depth_bounded(over, depth_of)
    assert not verdict.admissible
    assert ld.LINEAGE_DEPTH_EXCEEDS_BOUND in verdict.reasons

    at_the_bound = record(streams=[computed_stream("c-out", "filter-C")], depth=3)
    assert recursive_computation_is_depth_bounded(at_the_bound, depth_of).admissible


def test_the_bound_is_recorded_as_a_policy_not_a_derivation():
    source = (REPO_ROOT / "science" / "lineage_depth.py").read_text()
    assert "POLICY" in source
    assert "recorded rather than derived" in source


# ------------------------------------------- 5. the declaration is complete


def test_a_partial_declaration_is_refused_rather_than_read_as_non_recursive():
    """The way a recursive result would otherwise pass as an ordinary one.
    Any ONE of the four fields is a claim to be recursive; the rest then
    have to be there."""
    for field in ld.RECURSIVE_FIELDS:
        partial = {field: record()[field]}
        assert declares_recursion(partial)
        verdict = recursive_computation_is_depth_bounded(partial, depth_of)
        assert not verdict.admissible
        assert ld.PARTIALLY_DECLARED_RECURSION in verdict.reasons, field


def test_a_record_declaring_no_recursion_passes_untouched():
    """This gate answers one question and does not restate any other
    gate's. An ordinary observation is not a recursive computation."""
    ordinary = {"property": "water_level", "value": 1.2, "unit": "m"}
    assert not declares_recursion(ordinary)
    assert recursive_computation_is_depth_bounded(ordinary, depth_of).admissible


@pytest.mark.parametrize("streams,expected", [
    ([], ld.EMPTY_STREAM_IDENTITY),
    ("noaa-8454000", ld.UNTYPED_STREAM_IDENTITY),
    ([{"stream_id": "", "kind": "measured"}], ld.UNTYPED_STREAM_IDENTITY),
    ([{"stream_id": 7, "kind": "measured"}], ld.UNTYPED_STREAM_IDENTITY),
    ([{"stream_id": "s", "kind": "guessed"}], ld.UNKNOWN_PROVENANCE_KIND),
    ([{"stream_id": "s", "kind": "computed"}], ld.COMPUTED_PROVENANCE_NAMES_NO_PRIOR),
])
def test_stream_identity_must_be_a_real_identity(streams, expected):
    verdict = recursive_computation_is_depth_bounded(record(streams=streams), depth_of)
    assert not verdict.admissible
    assert expected in verdict.reasons


def test_a_measured_provenance_naming_a_prior_is_two_claims_not_one():
    """Not a harmless extra field: it says the record both was and was not
    derived from something, and picking either would invent an answer."""
    contradictory = {"kind": "measured", "prior_id": "filter-A"}
    verdict = recursive_computation_is_depth_bounded(
        record(initialization=contradictory), depth_of)
    assert ld.MEASURED_PROVENANCE_NAMES_A_PRIOR in verdict.reasons


@pytest.mark.parametrize("window", [None, "", "   "])
def test_the_horizon_must_be_stated_rather_than_absent(window):
    """An absent horizon is not "unbounded", it is unstated -- the same
    distinction as uncertainty_kind's explicit `absent`."""
    verdict = recursive_computation_is_depth_bounded(record(window=window), depth_of)
    assert ld.UNTYPED_WINDOW_OR_HORIZON in verdict.reasons


@pytest.mark.parametrize("declared", [-1, 1.5, True, "1", None])
def test_a_declared_depth_that_is_not_a_count_is_refused(declared):
    verdict = recursive_computation_is_depth_bounded(record(depth=declared), depth_of)
    assert not verdict.admissible
    assert ld.DECLARED_DEPTH_DISAGREES_WITH_LINEAGE in verdict.reasons


def test_an_unresolvable_prior_is_a_refusal_not_an_exception():
    unknown = record(initialization=computed_init("filter-Z"), depth=1)
    verdict = recursive_computation_is_depth_bounded(unknown, depth_of)
    assert not verdict.admissible
    assert ld.UNRESOLVABLE_PRIOR in verdict.reasons


# --------------------------------- 6. the account, because a number cannot argue


def test_the_depth_carries_its_contributions_not_only_its_value():
    """The failure being bounded is silent -- a trajectory that has
    drifted far from measured input looks exactly like one that has not.
    A number alone cannot be argued with."""
    account = lineage_depth(
        record(streams=[measured_stream(), computed_stream("b-out", "filter-B")],
               initialization=computed_init("filter-A"), depth=2), depth_of)
    assert isinstance(account, DepthAccount)
    assert account.depth == 2
    assert account.from_initialization == 1
    assert dict(account.from_streams) == {"noaa-8454000": 0, "b-out": 2}
    assert account.inherited_from_a_stream


# --------------------------------------------------- 7. the invariant record


def test_the_invariant_is_now_enforced_and_says_what_changed():
    entry = next(
        e for e in loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())["invariants"]
        if e["id"] == "generation_depth_bounded")
    assert entry["status"] == "enforced"
    assert Path(__file__).name in entry["enforcement"]
    assert entry["rule"] == "derivation from derivation is bounded and the depth is recorded"
    assert str(MAX_LINEAGE_DEPTH) in str(entry["declared_bound"])
    assert "composition guard" in entry["composition_guard"].lower()


def test_the_module_stays_pure_and_resolves_no_ids_itself():
    import ast

    source = (REPO_ROOT / "science" / "lineage_depth.py").read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "dataclasses", "typing", "science"}, sorted(imported)
    assert "daf" not in imported, "science/ may not reach into the acquisition layer"


# ------------------------------- 8. the response artifact the compute layer reads


def test_the_response_states_no_status_and_covers_every_daq_owned_row():
    """DAQ supplies evidence; the compute layer moves the row. The
    artifact must therefore state no status -- and must address every row
    the requirements artifact lists, with the count DERIVED rather than
    transcribed."""
    import re

    exchange = REPO_ROOT / "architecture" / "exchange"
    response = loads((exchange / "daq_requirement_response.yaml").read_text())

    # SCOPED TO KALMAN ON PURPOSE -- this is the Kalman file. The
    # partition-wide coverage property lives in
    # tests/test_cross_repository_claims.py, which is where it belongs now
    # that the response answers more than one workload. Keys became
    # `workload::requirement` when a requirement NAME turned out not to be
    # a row identity.
    assert "kalman_filter_linear" in response["responds_to_workloads"]
    assert "states_no_status" in response

    requirements = loads((exchange / "scl_requirements.yaml").read_text())
    daq_rows = {
        f"kalman_filter_linear::{row['requirement']}"
        for row in requirements["workloads"]["kalman_filter_linear"]["blocking_requirements"]
        if row["owner"] == "daq"
    }
    answered_here = {k for k in response["responses"] if k.startswith("kalman_filter_linear::")}
    assert answered_here == daq_rows, (
        f"the response addresses {sorted(answered_here)} of the artifact's {sorted(daq_rows)}")

    # No row may assert a status word.
    for name, row in response["responses"].items():
        blob = " ".join(str(v) for v in row.values())
        assert not re.search(r"\b(SATISFIED|UNSATISFIED)\b", blob), (
            f"{name} states a status; that is the compute layer's to set")


def test_the_response_quotes_the_requirement_rather_than_paraphrasing_it():
    exchange = REPO_ROOT / "architecture" / "exchange"
    response = loads((exchange / "daq_requirement_response.yaml").read_text())
    requirements = loads((exchange / "scl_requirements.yaml").read_text())
    rows = {
        f"kalman_filter_linear::{row['requirement']}": row["statement"]
        for row in requirements["workloads"]["kalman_filter_linear"]["blocking_requirements"]
    }
    for name, row in response["responses"].items():
        if not name.startswith("kalman_filter_linear::"):
            continue
        assert row["what_the_requirement_asked"] == rows[name], (
            f"{name}: the response paraphrases the requirement. A paraphrase of a counterparty's "
            "requirement is DAQ's account of it, which is what the exchange protocol exists to "
            "avoid.")


def test_the_response_regenerates_byte_identically_and_matches_its_sidecar():
    import hashlib
    import subprocess
    import sys

    exchange = REPO_ROOT / "architecture" / "exchange"
    artifact = exchange / "daq_requirement_response.yaml"
    before = artifact.read_bytes()
    subprocess.run([sys.executable, "build_daq_requirement_response.py"],
                   cwd=str(exchange), check=True, capture_output=True)
    assert artifact.read_bytes() == before
    assert (exchange / "daq_requirement_response.sha256").read_text().strip() == (
        "sha256:" + hashlib.sha256(before).hexdigest())


def test_the_response_reports_the_stale_upstream_status_without_editing_it():
    """The requirements artifact describes DAQ's invariant as
    `vacuously_enforced`. DAQ corrected it twice since. Reported in the
    response because the artifact is the compute layer's."""
    exchange = REPO_ROOT / "architecture" / "exchange"
    response = loads((exchange / "daq_requirement_response.yaml").read_text())
    row = response["responses"]["kalman_filter_linear::recursive_generation_depth"]
    assert "stale" in row["the_status_your_artifact_records_is_stale"].lower() or \
        "vacuously_enforced" in row["the_status_your_artifact_records_is_stale"]
    assert "Reported, not edited" in row["the_status_your_artifact_records_is_stale"]

    requirements = loads((exchange / "scl_requirements.yaml").read_text())
    upstream = next(r for r in requirements["workloads"]["kalman_filter_linear"]
                    ["blocking_requirements"] if r["requirement"] == "recursive_generation_depth")
    assert "vacuously_enforced" in upstream["statement"], (
        "the upstream text changed; the staleness report needs re-measuring")
