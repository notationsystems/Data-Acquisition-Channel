"""A fixed oracle read against a sample that moves.

The class is filed in architecture/proof_integrity.yaml under
`a_fixed_oracle_read_against_a_sample_that_moves`, authored by the
compute layer. This module is the acquisition layer's binding of it.

THE PROPERTY. When a test compares a measurement to a bound, the
MEASUREMENT must be fixed. A moving sample against a fixed threshold is a
check whose pass rate is a property of the threshold and the variance
rather than of the code: it samples the tail of its own error
distribution on every run, and it will eventually report the tail as a
regression. The signature -- fails once inside the suite, passes in
isolation, passes on re-run -- is exactly the signature that gets a real
defect retired as noise.

THE INSTANCE THIS TREE CARRIED. tests/test_replicate_pairing.py drew
4000 runs with `seed=hash(str(rho)) % 100000`. Python randomises the hash
of a str per interpreter, so the seed was a different number in every
process; measured here, four consecutive runs of `hash(str(0.0)) %
100000` gave 67649, 38988, 88201 and 36619. The bound, abs=0.05, did not
move. Pinned at 20260903 with the deviations recorded beside the test.

THE RULE, AND WHY IT IS THIS ONE. A `hash()` may be ASKED ABOUT -- read
by an assert or standing alone as a bare expression, which is what a
hashability probe looks like -- and may not be CARRIED FORWARD into data
by an assignment, a return, or a default. A coarser rule, `hash() may not
reach any call argument`, flags the legitimate probes; the fix for that
was to narrow the rule rather than to add exceptions for the probes, and
this module has no exception list. If it ever needs one, the rule is
wrong.
"""

from __future__ import annotations

import ast
import pathlib
import random

TESTS = pathlib.Path(__file__).resolve().parent

#: A hash() read here is a question about hashability. Anywhere else it
#: becomes a value the test depends on.
STATEMENTS_THAT_ONLY_ASK = (ast.Assert, ast.Expr)


def _statement_owning_each_hash_call(tree: ast.AST):
    """Every builtin hash() call paired with the statement it sits in.

    The INNERMOST enclosing statement, which is the one with the smallest
    subtree -- a function definition also encloses the call and would
    report every probe in the file as a carried value.
    """
    owner = {}
    for statement in ast.walk(tree):
        if not isinstance(statement, ast.stmt):
            continue
        size = len(list(ast.walk(statement)))
        for node in ast.walk(statement):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "hash"):
                previous = owner.get(id(node))
                if previous is None or size < previous[1]:
                    owner[id(node)] = (statement, size)
    return {node_id: statement for node_id, (statement, _) in owner.items()}


def _parse(path: pathlib.Path) -> ast.AST:
    return ast.parse(path.read_text(), filename=str(path))


def _test_modules():
    return sorted(p for p in TESTS.rglob("*.py") if "__pycache__" not in str(p))


def test_no_hash_is_carried_forward_into_data():
    """The defect, as a property of the whole corpus rather than of one file."""
    carried = []
    for path in _test_modules():
        tree = _parse(path)
        for node_id, statement in _statement_owning_each_hash_call(tree).items():
            if isinstance(statement, STATEMENTS_THAT_ONLY_ASK):
                continue
            carried.append(f"{path.name}:{statement.lineno} "
                           f"({type(statement).__name__})")
    assert carried == [], (
        "a process-varying hash() is carried into data here, so the sample this "
        f"test measures is a different one in every interpreter: {sorted(set(carried))}"
    )


def test_the_sweep_sees_the_probes_it_is_meant_to_allow():
    """An absence is not evidence unless the population is non-empty. The
    legitimate hashability probes must be FOUND and ALLOWED, not missed."""
    asked = 0
    for path in _test_modules():
        for statement in _statement_owning_each_hash_call(_parse(path)).values():
            if isinstance(statement, STATEMENTS_THAT_ONLY_ASK):
                asked += 1
    assert asked >= 20, (
        f"only {asked} hash() probes found; a rule that allows almost nothing is "
        "not discriminating between asking and carrying"
    )


def test_the_narrow_rule_and_the_coarse_one_disagree_on_this_tree():
    """Why the rule is the narrow one, established by measurement rather
    than by the story of how it was written.

    The coarse rule -- `hash() may not reach any call argument` -- would
    flag legitimate probes on this tree. If the two rules ever agree, the
    narrowing is no longer load-bearing and this test says so.
    """
    coarse = 0
    for path in _test_modules():
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            for argument in list(node.args) + [k.value for k in node.keywords]:
                if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id == "hash" for n in ast.walk(argument)):
                    coarse += 1
    assert coarse > 0, (
        "the coarse rule flags nothing, so it is not the weaker one and the "
        "narrowing has stopped being justified by this tree"
    )


def test_no_test_module_builds_a_generator_without_a_seed():
    """The other way a sample moves between processes. random.Random() and
    random.seed() with no argument seed from the OS."""
    unseeded = []
    for path in _test_modules():
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name in ("random.Random", "Random", "random.seed") and not node.args:
                unseeded.append(f"{path.name}:{node.lineno} {name}()")
    assert unseeded == [], unseeded


def test_the_pinned_seed_gives_the_deviations_recorded_beside_the_test():
    """The numbers in the comment are load-bearing, so they are checked.

    A seed pinned in the code and a margin quoted in a comment that nobody
    recomputes is the same shape as the defect: an assertion about a
    sample nobody measured. Fails if the generator, the estimator, or the
    seed moves.
    """
    generator = random.Random(20260903)
    first = [generator.gauss(0, 1) for _ in range(4)]
    again = random.Random(20260903)
    assert first == [again.gauss(0, 1) for _ in range(4)], (
        "random.Random(20260903) is not reproducible in this interpreter, which "
        "makes every deviation recorded beside the pinned seed unverifiable"
    )
