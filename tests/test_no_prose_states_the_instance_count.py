"""No file in this repository may state how many instances the class record
holds.

WHY THIS IS A CHECK AND NOT A CORRECTION. Two files carried the count in
prose. architecture/proof_integrity.yaml said `the 26 instances below`;
tests/test_condition_provenance_reachability.py said `records TWENTY-FOUR
instances`. Both were right when written, both were stale, and they were
stale by different amounts -- so the repository was simultaneously
asserting two different sizes for one list it could have counted.

Bumping them to today's number is the repair that guarantees a third
instance. The number moves every time a class member is filed, which is
exactly the event that makes nobody think about prose written months ago.
So the property asserted is that THE COUNT IS NOT WRITTEN DOWN AT ALL,
anywhere except where it is derived.

THE CLASS THIS BELONGS TO. `coverage_specified_by_enumeration`, and more
precisely the encoding rule beside it: one meaning, one encoding. A count
in prose is a second encoding of something a parse already knows, and
architecture/core.yaml made this exact repair for the `extends` census --
`THE COUNT IS NOT WRITTEN HERE ANY MORE. It is derived.` This is the same
repair applied to the other census the repository keeps.

THE FALSE POSITIVE IT FOUND, AND WHY NO EXCEPTION WAS ADDED. On its
first run this check flagged a THIRD stale count nobody had noticed --
architecture/vacuous_evidence.yaml saying `24 instances` -- and one
genuine false positive in the same file: `Two instances of one class,
stacked`, counting occurrences of a DIFFERENT class in a file that
happens to mention proof_integrity elsewhere. The prose was reworded and
the check was left alone, following the disposition
tests/test_cross_repository_claims.py already argues for at length: an
exception is a permanent hole in a check whose entire value is that it
has none, and it gets added by whoever is annoyed rather than by whoever
measured. A false positive costs one wording change and stays visible.

WHAT IT DOES NOT FORBID, deliberately. Counts of anything else. Phase
reports say how many defects a run found, how many mutants survived, how
many rows were admitted; those are readings with dates on them and
belong in prose. What is forbidden is a count OF THIS LIST, which is
sitting in the tree and can be counted on demand by anyone who wants it.
"""

from __future__ import annotations

import re
from pathlib import Path

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
RECORD = REPO_ROOT / "architecture" / "proof_integrity.yaml"

#: Spelled-out numbers appear in this repository's prose as often as
#: digits -- TWENTY-FOUR was the stale one, not 24. Both forms count.
_WORDS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    "thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    "twenty|thirty|forty|fifty"
)
#: A number, in either form, standing immediately before `instances`.
#: Hyphenated compounds (twenty-four, twenty-seven) are one token here.
_COUNT_OF_INSTANCES = re.compile(
    rf"\b(?:\d+|(?:{_WORDS})(?:[- ](?:{_WORDS}))?)\s+instances\b",
    re.IGNORECASE,
)

#: A file only counts as talking about THIS list if it names it.
_NAMES_THE_RECORD = re.compile(r"proof_integrity", re.IGNORECASE)


def _text_files():
    """Every hand-authored text file, derived by walking rather than
    listed -- the two stale counts lived in a YAML artifact and a test
    docstring, which is already two of the places nobody would have
    thought to enumerate."""
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        if path.suffix not in (".yaml", ".yml", ".py", ".md", ".txt"):
            continue
        if path == Path(__file__):
            continue
        try:
            yield relative, path.read_text()
        except (UnicodeDecodeError, OSError):       # pragma: no cover
            continue


def test_the_class_record_holds_instances_and_they_can_be_counted():
    """The premise. If the list were not parseable, forbidding prose
    counts would remove the only statement of the size -- which is the
    zero-over-an-unreachable-subject shape, not a repair."""
    record = loads(RECORD.read_text())
    instances = record["instances"]
    assert isinstance(instances, list) and instances
    assert all("name" in instance for instance in instances)


def test_no_prose_anywhere_states_the_size_of_the_class_record():
    offenders = []
    for relative, text in _text_files():
        if not _NAMES_THE_RECORD.search(text):
            continue
        for match in _COUNT_OF_INSTANCES.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{relative}:{line}: {match.group(0)!r}")
    assert not offenders, (
        "the size of architecture/proof_integrity.yaml's instance list is "
        "written into prose, where nothing updates it when the list grows:\n  "
        + "\n  ".join(offenders)
        + "\nCount it instead: loads(...)['instances'] is in the tree."
    )


def test_this_check_can_see_the_two_forms_that_were_actually_stale():
    """PLANT AND WATCH IT FAIL, on the real historical strings rather than
    on a convenient one. The digit form and the spelled-hyphenated form
    were the two that occurred, and a regex that caught only digits would
    have reported green over TWENTY-FOUR."""
    for prose in (
        "what makes it a class is the 26 instances below, each measured",
        "architecture/proof_integrity.yaml records TWENTY-FOUR instances of a check",
        "proof_integrity holds twenty-seven instances",
    ):
        assert _COUNT_OF_INSTANCES.search(prose), f"not caught: {prose!r}"
    for prose in (
        "three defects in one run that the full suite had reported green",
        "proof_integrity.yaml names the class; the instances are listed below",
        "the mutation set found 12 survivors",
    ):
        assert not _COUNT_OF_INSTANCES.search(prose), f"false positive: {prose!r}"
