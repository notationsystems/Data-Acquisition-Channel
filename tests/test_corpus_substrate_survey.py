"""architecture/corpus_substrate_survey.yaml, checked on the half that is here.

WHAT THIS FILE CAN AND CANNOT WITNESS. The survey compares two
repositories, and only one of them is in this tree. Claims about the
corpus substrate are a DATED READING of a named commit: they carry the
path they were read from, and re-verifying them means re-reading that
repository, which nothing here does. Claims about THIS repository are
checked directly, against the code rather than against the prose.

THE ONE THAT MATTERS MOST IS THE PREDICTION. The survey says a molar mass
emitted by the corpus -- a value with a unit and a bare scalar
uncertainty, and no statement of where that uncertainty came from -- is
refused at this repository's ingest boundary as MISSING_UNCERTAINTY_KIND.
That is a claim about behaviour, made about a shape no ingest has ever
seen, and it is the whole substance of the divergence the survey reports.
So it is not left as prose. The shape is constructed here from the
corpus's own field set and run through the real gate, and the refusal is
asserted by code, with the ADMISSIBLE counterpart run beside it so a gate
that refused everything could not pass this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from science.admissibility import (
    ABSENT,
    MISSING_UNCERTAINTY_KIND,
    STATED,
    UNCERTAINTY_KINDS,
    quantity_is_typed,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SURVEY = loads((REPO_ROOT / "architecture" / "corpus_substrate_survey.yaml").read_text())


def test_the_survey_records_what_it_read_and_when():
    """A reading with no referent is an opinion. The commit is recorded in
    full for the reason architecture/ecosystem_register.yaml had to learn
    twice: an abbreviated sha cannot be fetched from a remote, so a
    referent recorded short cannot be gone back to."""
    read = SURVEY["read_at"]
    assert re.fullmatch(r"[0-9a-f]{40}", read["commit"]), (
        f"the surveyed commit is recorded as {read['commit']!r}; a referent "
        "recorded abbreviated cannot be fetched back"
    )
    assert read["repository"].startswith("https://github.com/")
    assert read["branch"]


def test_every_claim_about_the_other_repository_names_where_it_was_read():
    """The survey's own stated rule, enforced rather than trusted. A claim
    about a sibling cannot be its own witness, so an uncited one is a
    claim nothing can be gone back to -- the shape
    architecture/proof_integrity.yaml files as a measured fact recorded in
    prose having nothing defending it.

    Derived from the survey's structure: any leaf whose key names the
    corpus must cite a path in it. A new comparison added later is
    covered by being a leaf, not by being added to a list here."""
    citation = re.compile(r"(?:README\.md|manifests/[\w.\-]+|ncg/[\w/]+\.py)")
    uncited = []

    def visit(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                visit(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")
        elif isinstance(node, str):
            leaf = path.rsplit(".", 1)[-1]
            if leaf == "the_corpus" and not citation.search(node):
                uncited.append(path)

    visit(SURVEY)
    assert not uncited, (
        "claims about the corpus substrate with no path they were read "
        f"from: {uncited}"
    )


def test_this_repositorys_uncertainty_vocabulary_is_what_the_survey_says():
    """Read from the code, not restated. The survey says four members and
    names them; a fifth added later, or one renamed, fails here."""
    divergence = SURVEY["where_the_two_diverge"]["uncertainty_carries_no_kind_in_the_corpus"]
    stated = divergence["this_repository"]
    assert "closed four-member vocabulary" in stated
    assert len(UNCERTAINTY_KINDS) == 4, (
        f"the survey describes a four-member vocabulary and there are "
        f"{len(UNCERTAINTY_KINDS)}: {UNCERTAINTY_KINDS}"
    )
    for kind in UNCERTAINTY_KINDS:
        assert kind in stated, f"{kind!r} is in the vocabulary and not in the survey"


def test_the_predicted_refusal_actually_happens_at_the_real_gate():
    """THE SURVEY'S CENTRAL CLAIM, run rather than asserted.

    The content is built from the corpus's own field set -- ncg/units.py
    Quantity is a value, a unit and an optional scalar `uncertainty`, and
    there is no kind field anywhere on it -- so this is the shape that
    boundary would actually receive, not a shape chosen to fail."""
    from_the_corpus = {
        "property": "Mn",
        "value": 12400.0,
        "unit": "g/mol",
        "uncertainty": 310.0,
        # and nothing else: Quantity has no third field.
    }
    verdict = quantity_is_typed(from_the_corpus)
    assert not verdict.admissible
    assert MISSING_UNCERTAINTY_KIND in verdict.reasons, (
        f"the survey predicts MISSING_UNCERTAINTY_KIND and the gate said "
        f"{verdict.reasons}"
    )


def test_the_gate_admits_the_same_value_once_the_kind_is_declared():
    """The counterpart, and the reason the refusal above means anything. A
    gate that refused every input would satisfy the test before this one
    while establishing nothing about uncertainty_kind. The ONLY difference
    between these two contents is the field the survey says is missing."""
    with_a_kind = {
        "property": "Mn",
        "value": 12400.0,
        "unit": "g/mol",
        "uncertainty": 310.0,
        "uncertainty_kind": STATED,
    }
    verdict = quantity_is_typed(with_a_kind)
    assert verdict.admissible, f"refused for {verdict.reasons}"


def test_a_declared_absence_is_not_the_same_as_a_missing_field():
    """The distinction the survey rests its `which side should move`
    argument on: `absent` is a real answer the corpus could give, and
    giving no answer is not it. If these two were treated alike, the
    divergence the survey reports would not exist."""
    declared_absent = {
        "property": "Mn",
        "value": 12400.0,
        "unit": "g/mol",
        "uncertainty": None,
        "uncertainty_kind": ABSENT,
    }
    assert quantity_is_typed(declared_absent).admissible
    said_nothing = dict(declared_absent)
    del said_nothing["uncertainty_kind"]
    assert MISSING_UNCERTAINTY_KIND in quantity_is_typed(said_nothing).reasons


def test_the_enumerated_check_the_survey_calls_enumerated_is_still_enumerated():
    """The survey's second finding claims this repository holds a check in
    the enumerated form that the corpus holds structurally. That claim is
    about THIS tree and is checked here: DERIVED_VARIABLES is a tuple of
    spellings, and its length is read rather than restated.

    If someone repairs it to a derived form, this test fails -- which is
    the right failure. The survey would then be describing a state that no
    longer holds, and saying so is the point."""
    from daf.extractors.gpc_report import DERIVED_VARIABLES

    assert isinstance(DERIVED_VARIABLES, tuple)
    assert all(isinstance(name, str) for name in DERIVED_VARIABLES)
    finding = SURVEY["where_the_two_diverge"]["the_derived_check_is_enumerated_here_and_derived_there"]
    for spelling in DERIVED_VARIABLES:
        assert spelling in finding["this_repository"], (
            f"{spelling!r} is in DERIVED_VARIABLES and the survey does not list it"
        )
    assert "dispersity" in DERIVED_VARIABLES
