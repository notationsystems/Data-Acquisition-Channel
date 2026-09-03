"""architecture/api_plane_assignment.yaml, and the invariant it encodes.

THE INVARIANT, as handed down: every API response either carries a
canonical reference and a proof root, or says explicitly that it is an
operational observation with its limitations.

THE AMENDMENT THIS FILE ENFORCES. These modules return three kinds of
thing, not two. A REFUSAL is neither a proof-rooted claim nor an
operational observation: it is derived, it reproduces from the same input,
and its reason comes from a closed vocabulary. Filing it as an observation
discards the property that makes it worth returning. The record states the
argument; this file makes the classification checkable.

WHY THE BRANCH IS DECLARED IN THE RECORD AND NOT STAMPED ON THE CLASSES.
Whether a type is a claim, a refusal or an observation cannot be derived
from its shape -- it is a statement about what the type MEANS. So it is
declared once, in the record, and joined here against types derived from
the code. Stamping an attribute on seventeen classes would put one
epistemic claim in two places, and this repository has a name for what
happens next.

WHAT IS DERIVED RATHER THAN LISTED. The response set: every project-owned
type returned by a public module-level entry point, found by walking the
return annotations. A new public function returning a new type fails here
until the record classifies it -- which is the point, because the
alternative is an endpoint returning something nobody decided the branch
of.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = loads((REPO_ROOT / "architecture" / "api_plane_assignment.yaml").read_text())

#: The packages a read surface would be built over.
_SURFACE = ("daf", "science", "evidence", "epistemics")

#: Annotations that are not project-owned response types. Derived from the
#: language and the standard library rather than from what happens to be
#: returned today, so the exclusion cannot quietly grow.
_NOT_A_RESPONSE_TYPE = {
    "None", "str", "int", "float", "bool", "bytes", "dict", "list", "tuple",
    "set", "Any", "Path", "object",
}


def _public_return_types():
    """Project-owned types returned by public module-level functions.

    A bare name only: a container annotation names the type it carries and
    that inner type is what a consumer receives, so `Tuple[Invariant, ...]`
    contributes `Invariant`."""
    found = {}
    for package in _SURFACE:
        base = REPO_ROOT / package
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:                          # pragma: no cover
                continue
            # Module-level functions AND public methods on public classes.
            # Narrowing to module level missed AcquiredArtifact and
            # AcquisitionCheckpoint, which reach a caller through a store's
            # method -- a surface is what a consumer can call, not what
            # happens to be spelled at module level.
            candidates = []
            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    candidates.append(node)
                elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    candidates.extend(
                        child for child in node.body
                        if isinstance(child, ast.FunctionDef)
                    )
            for node in candidates:
                if node.name.startswith("_") or node.returns is None:
                    continue
                for inner in ast.walk(node.returns):
                    if not isinstance(inner, ast.Name):
                        continue
                    name = inner.id
                    if name in _NOT_A_RESPONSE_TYPE or name[0].islower():
                        continue
                    if name in ("Optional", "Tuple", "Dict", "List", "Sequence",
                                "Mapping", "Iterable", "Set", "FrozenSet"):
                        continue
                    found.setdefault(name, str(path.relative_to(REPO_ROOT)))
    return found


def _declared_fields(type_name):
    """The annotated fields of a class, wherever it is defined."""
    for package in _SURFACE:
        base = REPO_ROOT / package
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:                          # pragma: no cover
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == type_name:
                    return [
                        statement.target.id for statement in node.body
                        if isinstance(statement, ast.AnnAssign)
                        and isinstance(statement.target, ast.Name)
                    ]
    return None


BRANCH_REQUIREMENT = {
    "claim": "reference_field",
    "refusal": "reason_field",
    "observation": "limitation_field",
}


def test_the_record_declares_three_branches_and_what_each_one_owes():
    """The amendment itself. Two branches would put refusals somewhere
    they do not belong; a branch with no requirement would be a label."""
    branches = RECORD["response_branches"]
    assert set(branches) == set(BRANCH_REQUIREMENT), (
        f"the record declares branches {sorted(branches)}"
    )
    for name, branch in branches.items():
        assert branch.get("requires"), f"{name} declares no requirement"
        assert branch.get("what_it_is"), f"{name} says nothing about what it is"


def test_every_response_type_the_code_returns_is_classified():
    """DERIVED, not listed. This is the check that makes the record a
    constraint rather than a snapshot: a public function returning a type
    nobody has assigned a branch to fails here."""
    returned = _public_return_types()
    assert len(returned) >= 10, f"only found {sorted(returned)}; the walk is broken"
    declared = (set(RECORD["response_types"])
                | set(RECORD["vendored_response_types"]["observed"])
                | set(RECORD["not_a_response"]["members"]))
    unclassified = sorted(set(returned) - declared)
    assert not unclassified, (
        "these types are returned by a public entry point and the record "
        f"assigns them no branch: {[(n, returned[n]) for n in unclassified]}"
    )


def test_no_type_is_classified_that_the_code_does_not_return():
    """The mirror, and the one that catches a record going stale. A branch
    assigned to a type nothing returns is a decision about nothing."""
    returned = set(_public_return_types())
    classified = (set(RECORD["response_types"])
                  | set(RECORD["vendored_response_types"]["observed"])
                  | set(RECORD["not_a_response"]["members"]))
    orphans = sorted(classified - returned)
    assert not orphans, (
        f"the record classifies types no public entry point returns: {orphans}"
    )


def test_the_vendored_types_are_recorded_as_observed_and_not_declared():
    """A third of the response surface belongs to the core. Recording a
    branch for another party's type as though this layer had decided it is
    the error architecture/exchange/ste_invariants.yaml warns about -- a
    reconstruction cited as a declaration. So the vendored block uses a
    different key and says what would make it a declaration."""
    block = RECORD["vendored_response_types"]
    assert block["status"] == "OBSERVED_NOT_DECLARED"
    assert block.get("owner") and block.get("what_would_make_them_declared")
    for name, entry in block["observed"].items():
        assert "observed_branch" in entry, f"{name} declares rather than observes"
        assert "branch" not in entry, f"{name} uses the declaring key"
        assert entry["observed_branch"] in BRANCH_REQUIREMENT


def test_each_branch_carries_the_field_its_requirement_names():
    """THE HALF THAT BITES. A declaration alone is a label. What is checked
    is that the type actually HAS the field its branch obliges it to have:
    a claim with no reference field, or a refusal with no reason field, is
    the state the invariant exists to forbid."""
    missing = []
    for name, entry in RECORD["response_types"].items():
        branch = entry["branch"]
        assert branch in BRANCH_REQUIREMENT, f"{name} declares branch {branch!r}"
        key = BRANCH_REQUIREMENT[branch]
        field = entry.get(key)
        assert field, f"{name} is a {branch} and names no {key}"
        fields = _declared_fields(name)
        if fields is None:
            continue
        if field not in fields:
            missing.append(f"{name} ({branch}) names {key}={field!r}, and has {fields}")
    assert not missing, (
        "a response type does not carry the field its branch requires:\n  "
        + "\n  ".join(missing)
    )


def test_the_covariance_can_be_navigated_back_to_the_runs_it_came_from():
    """THE GAP THE INVARIANT FOUND, replayed as its own case rather than
    left to the general check.

    SampleCovariance carried no reference of any kind: not an id, not the
    run ids, not the observation ids of the cells it was summed from. It
    is the object this pair spent a phase making trustworthy and the one
    whose output crosses to the compute layer. Every test over it passed
    the whole time, because they check the numbers and the numbers were
    right.

    Asserted on a live pairing rather than on the dataclass, so a field
    that exists and is never populated fails."""
    import datetime
    import math
    import random

    from evidence.types import make_observation
    from daf.storage.frozen_mapping import FrozenMapping
    from science.replicate_pairing import pair_replicates, sample_covariance

    # Built here rather than imported from another test module: a check
    # that depends on a test file is a check that moves when that file is
    # reorganised, and this one is about a property of the module.
    when = datetime.datetime(2026, 9, 3, tzinfo=datetime.timezone.utc)
    conditions = FrozenMapping({"solvent": "THF"})
    rng = random.Random(20260903)
    observations = []
    for run in range(4):
        mn = math.exp(rng.gauss(math.log(104000.0), 0.03))
        for name, value in (("number_average_molar_mass", mn),
                            ("weight_average_molar_mass", mn * 2.4)):
            observations.append(make_observation(
                record_ids=(f"gpc-run-{run}",),
                extraction_method="gpc_report_v1",
                content={"sample_id": "PS-lot-4471", "property": name,
                         "value": value, "unit": "g/mol", "uncertainty": 1200.0,
                         "uncertainty_kind": "stated", "conditions": conditions},
                confidence=1.0, extracted_at=when))

    pairing = pair_replicates(observations)
    result = sample_covariance(pairing.sets[0])
    assert result.source_run_ids, "no run reference"
    assert len(result.source_run_ids) == result.n_runs
    assert result.source_observation_ids, "no observation reference"
    # every cell that entered the sums is referenced, and nothing else is
    assert len(result.source_observation_ids) == result.n_runs * len(result.variables)
    keys = {key for key, _ in result.source_observation_ids}
    assert keys == {(run, variable)
                    for run in result.source_run_ids
                    for variable in result.variables}
    assert all(identity for _, identity in result.source_observation_ids)


def test_a_store_handle_is_not_classified_as_a_response():
    """The fourth category, and why it is not a branch.

    A handle asserts nothing, refuses nothing and reports nothing. The
    first draft of the record filed one as an observation with an empty
    limitation field and the requirement check refused it -- an empty
    required field is a classification that was not made. Each member must
    say what it is and what KIND of response it hands back, so the
    obligation lands on the returns rather than being lost."""
    block = RECORD["not_a_response"]
    assert block.get("why_the_category_exists")
    assert block["members"], "the category exists with no members"
    branches = set(RECORD["response_branches"])
    for name, member in block["members"].items():
        assert member.get("what_it_is"), f"{name} does not say what it is"
        returns = member.get("returns_responses_of_type")
        assert returns, f"{name} does not say what kind of response it hands back"
        assert "branch" not in member and "observed_branch" not in member, (
            f"{name} is classified as a response and is a store handle"
        )
        classified = set(RECORD["response_types"]) | set(
            RECORD["vendored_response_types"]["observed"])
        named = [part.strip() for part in returns.split(",")]
        unknown = [n for n in named if n not in classified]
        assert not unknown, (
            f"{name} hands back {unknown}, which nothing classifies"
        )
    assert branches.isdisjoint(block["members"])


def test_a_plane_this_repository_cannot_serve_says_so_rather_than_being_omitted():
    """Three of the four planes assume a tenant and nothing here has one.
    A map that listed only what it could do would read as a system that
    does all four -- the zero-over-an-unreachable-subject shape, applied
    to a capability statement."""
    planes = RECORD["planes"]
    assert set(planes) == {
        "tenant_read", "verification", "governance", "internal_ingestion_operator",
    }
    for name, plane in planes.items():
        assert plane.get("can_serve_today"), f"{name} does not say what it can serve"
    operator = planes["internal_ingestion_operator"]
    assert "NONE" in operator["can_serve_today"].upper()
    assert operator.get("what_is_absent")


def test_no_proof_root_is_claimed_anywhere():
    """The half of the invariant nothing here satisfies, asserted so it
    cannot be quietly satisfied by renaming a content commitment.

    A content hash answers `are these the same bytes`. A proof root
    answers `what supports this`. They are different questions and only
    one of them has an implementation here."""
    claim = RECORD["response_branches"]["claim"]
    status = claim["proof_root_status"]
    assert "NOT PRESENT" in status
    for name, entry in RECORD["response_types"].items():
        assert "proof_root" not in entry, (
            f"{name} claims a proof root; none exists in this tree"
        )


def test_every_module_family_recorded_present_names_something_that_exists():
    """A capability claim about this repository is checkable here, so it
    is checked. `absent` and `thin` claims are not verifiable this way and
    are not pretended to be."""
    import re

    unfound = []
    for name, family in RECORD["module_families"].items():
        if str(family.get("status", "")).split("_")[0] not in ("present", "partial"):
            continue
        paths = re.findall(r"(?:daf|science|evidence|epistemics|architecture)/[\w/.]+\w",
                           family.get("here", ""))
        if not paths:
            continue
        for path in paths:
            if not (REPO_ROOT / path).exists():
                unfound.append(f"{name}: {path}")
    assert not unfound, (
        f"a family recorded as present names paths that do not exist: {unfound}"
    )
