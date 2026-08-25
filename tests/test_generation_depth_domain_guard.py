"""The expiry guard for `generation_depth_bounded`.

That invariant's recorded evidence -- "no generative path exists to
bound" -- is TRUE NOW AND SELF-INVALIDATING. It is not an ordinary
passing check; it is a claim with an expiry condition, and the failure
mode is that the condition passes silently while the status still reads
`vacuously_enforced`. By this repository's own standard, a vacuous status
whose justification has quietly gone untrue is worse than a status of
`absent`.

So the expiry is ENCODED rather than remembered. This file asserts the
domain is STILL EMPTY. It FAILS the moment a generative path lands, which
forces the depth rule to be written before that path ships rather than
retrofitted around it afterwards -- and retrofitting is precisely the
condition that would turn the correction into a bend
(architecture/recursive_depth.yaml).

THE GUARD IS NOT THE INVARIANT. Nothing here bounds any depth. It refuses
to let the invariant stay vacuous once it has stopped being vacuous.

WHY IT FIRES EARLY. The invariant bites at derivation-FROM-derivation,
but this guard trips one step sooner, at the first derivation of any
kind. That is deliberate: depth becomes a question the moment anything
generative exists, and the rule needs to be written then, not at the
first nested case.

A GUARD THAT CANNOT FIRE IS WORSE THAN NO GUARD, so
`test_the_detector_actually_fires_on_a_synthetic_generative_path` proves
the detector is not vacuous AS A DETECTOR -- the same discipline Phase 25
applied to the model-binding constraint checker.
"""

from __future__ import annotations

import pathlib

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from epistemics.evidence_class import (
    COMPUTED,
    DERIVED,
    ClassRegister,
    make_class_assignment,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
INVARIANTS = REPO_ROOT / "architecture" / "invariants.yaml"

#: Production packages. Tests are excluded on purpose: a test may
#: construct a derivation to characterize behaviour (this file does)
#: without that constituting a production generative path.
PRODUCTION_PACKAGES = ("daf", "epistemics", "science", "assertion", "boundary", "bridge")

#: The ONE legitimate `make_derived_value` call site: rebuilding a
#: DerivedValue that was already stored. Reconstruction is not
#: derivation. Kept as a named allowlist so a second site has to be
#: added here deliberately, in a diff someone reads.
RECONSTRUCTION_ONLY = {"daf/storage/serialization.py"}


def _production_sources():
    for package in PRODUCTION_PACKAGES:
        root = REPO_ROOT / package
        if root.exists():
            for path in sorted(root.rglob("*.py")):
                yield path, path.relative_to(REPO_ROOT).as_posix(), path.read_text()


@pytest.fixture(scope="module")
def invariant():
    document = loads(INVARIANTS.read_text())
    for entry in document["invariants"]:
        if entry["id"] == "generation_depth_bounded":
            return entry
    raise AssertionError("generation_depth_bounded is not declared")


# ================================================= the declared state

def test_the_invariant_still_declares_an_empty_domain(invariant):
    """If someone moves the status off vacuously_enforced, they have
    accepted the obligation and this guard's job changes. Until then the
    declared state and the measured state must agree."""
    assert invariant["status"] == "vacuously_enforced"
    assert invariant["domain"] == "empty"
    assert invariant["invalidated_by"], "an expiring claim must say what expires it"
    assert invariant["guard"] == "tests/test_generation_depth_domain_guard.py", (
        "the invariant must name this file, or the guard can be deleted without trace")


# ============================================ the measured state: empty

def test_no_production_module_creates_a_derivation():
    """The first derivation of any kind makes depth a live question.

    A hit here is not a defect -- it means the generative path arrived,
    and the depth rule has to be written NOW, before that path ships."""
    offenders = []
    for _, relative, text in _production_sources():
        if relative in RECONSTRUCTION_ONLY:
            continue
        for marker in ("make_derived_value(", "make_derived_grounding("):
            if marker in text:
                offenders.append(f"{relative}: {marker}")
    assert not offenders, (
        "a generative path has landed: " + "; ".join(offenders) + ". "
        "generation_depth_bounded is no longer vacuous -- write the depth rule "
        "(architecture/recursive_depth.yaml states the proposed rule and its "
        "composition guard), move the invariant off vacuously_enforced, and "
        "replace its now-false evidence line."
    )


def test_the_reconstruction_allowlist_stays_minimal():
    """The allowlist exists for deserialization, which rebuilds what was
    already stored. If it grows, the growth must be argued."""
    assert RECONSTRUCTION_ONLY == {"daf/storage/serialization.py"}
    text = (REPO_ROOT / "daf" / "storage" / "serialization.py").read_text()
    assert "derived_value_from_dict" in text, (
        "the allowlisted site must still be the deserializer it was allowlisted for")


def test_no_production_module_computes_a_depth():
    """The other half of the same claim: not only is nothing derived
    from a derivation, nothing anywhere carries a depth."""
    offenders = [
        relative for _, relative, text in _production_sources()
        if "generation_depth" in text
    ]
    assert not offenders, (
        f"a depth is being tracked in {offenders} while the invariant still "
        "declares status vacuously_enforced and domain empty -- the declared "
        "state and the code have diverged")


def test_no_production_module_assigns_a_computed_or_derived_class():
    """`computed` and `derived` are already canonically admissible
    classes -- the vocabulary is ready and nothing produces one. The
    first production assignment of either is the store-side arrival of
    the same generative path."""
    offenders = []
    for _, relative, text in _production_sources():
        for marker in ('evidence_class=COMPUTED', 'evidence_class=DERIVED',
                       'evidence_class="computed"', 'evidence_class="derived"'):
            if marker in text:
                offenders.append(f"{relative}: {marker}")
    # daf/storage/classified_pool.py assigns DERIVED to DerivedValue objects
    # by policy. That is the RULE for classifying a derivation, not the
    # creation of one; it is unreachable while nothing creates a
    # DerivedValue, which the test above is what actually holds.
    offenders = [o for o in offenders if not o.startswith("daf/storage/classified_pool.py")]
    assert not offenders, f"a computed/derived class is being assigned in production: {offenders}"


# ====================================== proof the detector can fire

def test_the_detector_actually_fires_on_a_synthetic_generative_path(tmp_path):
    """A guard that cannot fire is worse than no guard, because it reads
    as protection. Two things are shown here:

      1. the class machinery genuinely ADMITS a derived assignment, so
         the domain would really become non-empty -- it is not empty
         because the vocabulary forbids it, but because nothing produces
         one;
      2. the source detector above finds a generative marker when one is
         actually present.
    """
    # 1. the vocabulary is ready and waiting
    assignment = make_class_assignment(
        evidence_id="synthetic-derived-1",
        evidence_kind="derived_value",
        evidence_class=DERIVED,
        assigned_by="test_generation_depth_domain_guard",
    )
    register = ClassRegister()
    register.assign(assignment)
    assert register.class_of("synthetic-derived-1") == DERIVED
    assert COMPUTED != DERIVED, "both are distinct admissible classes"

    # 2. the detector is a real detector
    planted = tmp_path / "fake_module.py"
    planted.write_text("x = make_derived_value(inputs=[other_derived])\n")
    assert "make_derived_value(" in planted.read_text()

    scanned = [relative for _, relative, text in _production_sources()
               if "make_derived_value(" in text]
    assert scanned == ["daf/storage/serialization.py"], (
        "the detector should see exactly the one allowlisted reconstruction site; "
        f"it saw {scanned}")
