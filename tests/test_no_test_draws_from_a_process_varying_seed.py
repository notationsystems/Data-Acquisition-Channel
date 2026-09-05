"""No test in this repository may let a process-varying value reach its data.

WHAT WENT WRONG, EXACTLY. tests/test_replicate_pairing.py drew its sample
with `seed=hash(str(rho)) % 100000`. Python randomises the hash of `str` and
`bytes` per interpreter unless PYTHONHASHSEED is pinned, so that seed was a
different number in every process. Measured, three consecutive interpreters:

    hash(str(0.0)) % 100000 -> 22807, 37619, 53489

The assertion it fed was `recovered == approx(rho, abs=0.05)` -- a FIXED
oracle. So the test compared a sample that moved against a bound that did
not. It failed once for rho=0.0 inside a full-suite run, passed on its own,
and passed again on re-run, which is the exact signature that gets a test
called flaky and re-run until it is green.

WHY IT IS FILED AS A DEFECT AND NOT A FLAKE. A flake is a defect whose
location has not been found. This one has a location and a mechanism. The
repair was to pin the seed, and specifically to pin it WITHOUT SHOPPING IT:
the first and only value tried was the date, 20260903. Best-of-forty seed
selection was measured (it gives |r-rho| ~ 0.0001) and rejected, because
choosing the sample that best flatters the estimator is tuning the
experiment to its own answer -- the same failure as using the production
implementation as its own oracle. The tolerance was NOT touched.

THE REPOSITORY ALREADY KNEW. tests/test_persistent_condition_lifecycle.py
has said, since it was written, that the native hash "is a dict key WITHIN
one process and never persists or compares it. A test asserting a stable
native hash across processes would be asserting something Python does not
promise and this architecture does not need." It even runs three
subprocesses to demonstrate the value moving. So this was not an unknown
hazard that bit an unlucky file -- it was a documented one, written down in
one test file, violated in another, with nothing mechanical between them.
That gap is the whole reason this check exists: prose in a docstring binds
only the file it is in.

THE PROPERTY ASSERTED HERE, and where the line falls. The builtin `hash()`
may be ASKED ABOUT but not CARRIED FORWARD. Concretely: a hash() call may
appear in an `assert` or as a bare expression -- `hash(conditions)`,
`assert isinstance(hash(fm), int)`, `assert hash(a) == hash(b)`,
`assert len({hash(c) for c in group}) == 1` -- because there its value is
consumed, in the same statement, by a question about hashing. It may not
appear in an assignment or any other statement that carries its value on to
be used as data, which is precisely what `seed=hash(str(rho)) % 100000`
inside `runs = correlated_runs(...)` did.

The first draft of this check used a coarser rule -- hash() may not reach
any call's arguments -- and it flagged two of the legitimate probes above.
No exception was added for them. The rule was narrowed to the property that
is actually true, which is the disposition
tests/test_no_prose_states_the_instance_count.py argues for: an exception is
a permanent hole placed by whoever was annoyed, and a check with holes in it
stops being evidence.

WHAT IT DELIBERATELY DOES NOT CHECK. Determinism in general. A test may
still draw from `random` without a seed, read the clock, or depend on
directory order; those are different defects with different repairs. This
check names one mechanism that actually bit, and it stays narrow so that
the thing it reports is unambiguous when it fires.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS = REPO_ROOT / "tests"


def _python_sources():
    """Derived by sweep. Nothing here is enumerated -- a test file added
    tomorrow is covered the day it lands, without editing this list."""
    for path in sorted(TESTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _builtin_hash_calls(node):
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "hash"
        ):
            yield child


#: Statements that consume a value where they stand. Anything else carries
#: it forward, which is the thing being forbidden.
_CONSUMING = (ast.Assert, ast.Expr)


def _statements_that_carry_a_hash_forward(tree):
    """Yield (lineno, statement class name) for every hash() call sitting in
    a statement that does not consume it on the spot."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt) or isinstance(node, _CONSUMING):
            continue
        # only this statement's own expressions, not those of nested
        # statements -- ast.walk would otherwise attribute a nested assert's
        # hash() to the enclosing function definition.
        for field, value in ast.iter_fields(node):
            items = value if isinstance(value, list) else [value]
            for item in items:
                if not isinstance(item, ast.AST) or isinstance(item, ast.stmt):
                    continue
                for found in _builtin_hash_calls(item):
                    yield found.lineno, type(node).__name__


def test_no_hash_value_is_carried_forward_as_data():
    escaping = []
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, statement in _statements_that_carry_a_hash_forward(tree):
            escaping.append(
                f"{path.relative_to(REPO_ROOT)}:{lineno} -- hash() in a {statement}"
            )
    assert not escaping, (
        "the builtin hash() of a str or bytes is randomised per process; its "
        "value may be asserted about but must not become data:\n  "
        + "\n  ".join(escaping)
    )


def test_the_check_would_catch_the_defect_it_was_written_for():
    """Planted. Without this, the check above could be vacuous -- it passes
    today because the tree is clean, which is indistinguishable from it
    passing because it looks at nothing."""
    planted = ast.parse(
        "runs = correlated_runs(4000, rho, seed=hash(str(rho)) % 100000)")
    assert list(_statements_that_carry_a_hash_forward(planted)), (
        "the check does not catch the line it exists because of")


def test_the_hashability_probes_that_are_fine_are_not_flagged():
    """The other half of the same question. A check that flagged every hash()
    would be enforcing nothing about seeds -- it would just be a ban, and the
    first person it inconvenienced would except their file out of it.

    Every line below is quoted from a test in this tree that is CORRECT."""
    for source in (
        "hash(conditions)",
        "assert isinstance(hash(fm), int)",
        "assert a == b and hash(a) == hash(b)",
        "assert hash(conditions) == hash(FrozenMapping(dict(conditions)))",
        "assert len({hash(c) for c in conditions}) == 1",
        "assert hash(obs.content['conditions']) is not None",
        "def f():\n    assert hash(x)\n",
    ):
        flagged = list(_statements_that_carry_a_hash_forward(ast.parse(source)))
        assert not flagged, f"a legitimate hashability probe was flagged: {source}"


# =====================================================================
# Three further properties, merged in from the concurrent measurement of
# the same defect. Both sessions read the same record and built this
# module independently; these are what the other one had that this did
# not.
# =====================================================================

def test_no_test_module_builds_a_generator_without_a_seed():
    """The OTHER way a sample moves between processes, and the one the
    hash() rule cannot see. `random.Random()` and `random.seed()` with no
    argument seed from the OS, which is a different mechanism with an
    identical consequence: a fixed oracle read against a sample nobody
    chose."""
    unseeded = []
    for path in _python_sources():
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if not isinstance(node, ast.Call):
                continue
            if ast.unparse(node.func) in ("random.Random", "Random",
                                          "random.seed") and not node.args:
                unseeded.append(f"{path.name}:{node.lineno}")
    assert unseeded == [], (
        f"a generator here is seeded from the OS, so its sample differs per "
        f"process exactly as the hash() one did: {unseeded}"
    )


def test_the_narrow_rule_and_the_coarse_one_still_disagree_on_this_tree():
    """Why the rule allows a hash() inside an assert instead of banning it.

    The coarse rule -- `hash() may not reach any call argument` -- flags
    legitimate probes on this tree. That is the whole reason the narrowing
    exists, and it is a fact about the corpus rather than about the story
    of how the rule was written, so it is measured. If the two rules ever
    agree, the narrowing has stopped being load-bearing and this says so
    rather than leaving a justification nobody rechecks.
    """
    coarse = 0
    for path in _python_sources():
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if not isinstance(node, ast.Call):
                continue
            for argument in list(node.args) + [k.value for k in node.keywords]:
                if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id == "hash" for n in ast.walk(argument)):
                    coarse += 1
    assert coarse > 0, (
        "the coarse rule now flags nothing, so it is no longer the weaker one "
        "and the narrowing is no longer justified by this tree"
    )


def test_the_pinned_seed_is_reproducible_in_this_interpreter():
    """The deviations recorded beside the pinned seed are only meaningful if
    the generator gives the same draw twice. Asserting the numbers without
    asserting that is the same shape as the defect."""
    import random

    first = [random.Random(20260903).gauss(0, 1) for _ in range(1)]
    again = [random.Random(20260903).gauss(0, 1) for _ in range(1)]
    assert first == again, (
        "random.Random(20260903) is not reproducible here, which makes every "
        "deviation recorded beside the pinned seed unverifiable"
    )
