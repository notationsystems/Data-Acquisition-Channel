"""Claims one repository makes ABOUT THE OTHER, checked against the other.

A DIFFERENT SHAPE FROM SELF-DESCRIPTION, and the difference is why nothing
covered it. tests/test_self_description_matches_the_artifact.py checks an
artifact against its OWN encoding -- the artifact and the thing described
are the same object, so the artifact's bytes are their own evidence. A
claim about the SIBLING's state has its evidence in another repository, so
the artifact cannot be its own witness and no check scoped to one artifact
can reach it.

MEASURED, LIVE, BEFORE THIS FILE EXISTED. scl_requirements.yaml said
generation_depth_bounded is "declared with status vacuously_enforced".
This repository corrected that to represented_unenforced on 2026-08-25 and
then to enforced when it closed the row. The compute layer's artifact was
two corrections behind, every suite in both repositories was green, and
the sibling had REPORTED the staleness rather than editing someone else's
artifact -- which is the correct boundary and also means the report had
nowhere to land except prose.

THE DISTINCTION THIS CHECK HAS TO PRESERVE. A stale status is not
automatically a defect. This pair deliberately retains superseded
measurements, because an artifact records what was measured and when
rather than a continuously-updated view of the counterparty. So:

    a superseded status RETAINED, with the current one stated beside it
        -> a dated measurement, legitimate
    a superseded status STANDING ALONE
        -> nobody noticed, which is the defect

Both are expressible and only one passes.

DERIVED, NOT LISTED. The invariant ids come from this repository's own
invariants.yaml, and the status vocabulary comes from the statuses those
invariants actually carry -- so an invariant added later, or a status word
used for the first time, is covered without anyone adding it here.

AND THE DOCUMENTS ARE DERIVED TOO, since 2026-08-26. They were not. This
file swept `scl_requirements.yaml` and `daq_requirement_response.yaml` --
the two artifacts someone had thought of -- which is coverage specified by
enumeration in the check written to end a coverage failure. Found by
applying the general form the same day it was recorded: name the event the
policy fires on, then ask what goes red when it happens.

    architecture/decisions/2026-08-26-joint-workload-decision.yaml
      carried_forward_not_resolved.recursive_depth:
        "generation_depth_bounded's status was corrected this phase from
         vacuously_enforced to represented_unenforced"

That is a claim about this repository, standing alone, two corrections
behind -- the identical defect, in an artifact the sweep did not look at,
while the sweep reported green. The domain is now every YAML document the
repository holds outside vendor/, so a hash-bearing decision record, a
probe or an artifact nobody has invented yet is covered by being a file.

Widening it flagged FOUR rows on the first run where the enumerated
version reported green: three real stale claims -- the decision record
above, architecture/exchange/daq_capabilities.yaml, and
architecture/structured_uncertainty.yaml, all about the same invariant --
and one false positive.

THE PRECISION LIMIT, and the disposition chosen for it. The status
vocabulary overlaps ordinary English: `absent` and `blocked` are statuses
here AND words. daq_capabilities.yaml said `unit` is "refused as
MISSING_UNIT when absent" beside the id `quantity_is_typed`, and this
check cannot tell a status word used as a status from one used as
English. Distance does not separate them either -- the false positive sat
in one sentence while a real claim spanned two.

The disposition is to REWORD THE PROSE, not to teach this check an
exception. An exception is a permanent hole in a check whose entire value
is that it has none, and it would be added by whoever is annoyed rather
than by whoever measured. A false positive costs one wording change and
stays visible; a false negative is the defect this file exists for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
INVARIANTS = loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
REQUIREMENTS = loads((EXCHANGE / "scl_requirements.yaml").read_text())
RESPONSE = loads((EXCHANGE / "daq_requirement_response.yaml").read_text())


def _documents():
    """Every YAML document this repository holds, outside the vendored
    substrate. Derived by walking the tree: a claim about the sibling can
    live in any hand-authored file, and the ones that carried it were not
    the ones anybody would have listed."""
    found = []
    for path in sorted(REPO_ROOT.rglob("*.yaml")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        try:
            document = loads(path.read_text())
        except Exception:                                    # pragma: no cover
            continue
        if document is not None:
            found.append((str(relative), document))
    return found


DOCUMENTS = _documents()

#: id -> current status, from this repository's own ledger.
CURRENT = {entry["id"]: entry["status"] for entry in INVARIANTS["invariants"]}
#: the vocabulary, taken from what is actually in use rather than retyped.
VOCABULARY = sorted(set(CURRENT.values()), key=len, reverse=True)


def _strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


#: Sentence boundaries, for the predication rule below. Deliberately
#: crude: splitting too eagerly only narrows further, and the narrowing
#: is measured against every claim in the tree rather than reasoned about.
_SENTENCE_BREAK = re.compile(r"(?<=[.;])\s+")


def _predicated_of(value, invariant, word):
    """Is `word` asserted AS THE STATUS OF `invariant`, or merely present
    in the same string?

    THE NARROWING THE DEFERRAL'S CONDITION REQUIRED. The sweep counted
    any status-vocabulary word anywhere in a string that named an
    invariant. `absent` is also ordinary English, so a sentence about an
    invariant followed by a sentence using the word tripped it.

    The rule is derived from every status claim actually in this tree,
    not invented: each one either uses the word `status` explicitly, or
    puts the status word in the SAME SENTENCE as the invariant it is
    predicated of. A string doing neither is not making a status claim.

    WHAT IT GIVES UP, stated rather than discovered later: a genuine
    stale claim that spans two sentences without using the word `status`
    -- "X was measured in Phase 3. It is vacuously_enforced." -- is no
    longer caught. And it does NOT address the OTHER false-positive mode:
    a string about the FUNCTION `no_context_free_property` still reads as
    a string about the INVARIANT of that name, in the same sentence or
    not. That mode is unrepaired and is measured by the collision test
    below."""
    if re.search(r"(?<![\w])status(?![\w])", value, re.IGNORECASE):
        return True
    for sentence in _SENTENCE_BREAK.split(value):
        if invariant in sentence and re.search(rf"(?<![\w]){word}(?![\w])", sentence):
            return True
    return False


def _rows_with_status_claims(predicate=_predicated_of):
    """Every mapping in the requirements artifact that names one of this
    repository's invariants together with a status word PREDICATED of
    it.

    `predicate` is an argument so the narrowing can be measured against
    the unnarrowed sweep by passing the rule that admits everything --
    the comparison then runs the real path twice rather than comparing
    the real one against a paraphrase of the old one."""
    found = []

    def visit(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str):
                    for invariant in CURRENT:
                        if invariant not in value:
                            continue
                        said = [w for w in VOCABULARY
                                if re.search(rf"(?<![\w]){w}(?![\w])", value)
                                and predicate(value, invariant, w)]
                        if said:
                            found.append((f"{path}.{key}", invariant, said, node))
                else:
                    visit(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    for name, document in DOCUMENTS:
        visit(document, name)
    return found


def test_the_domain_is_non_empty_so_the_check_can_fail():
    """Asserted before the check, not after it. A sweep that finds no
    claims reports no stale claims and means nothing."""
    assert CURRENT, "no invariants declared"
    assert VOCABULARY, "no status vocabulary in use"
    assert DOCUMENTS, "no YAML documents found -- the sweep is not reaching the tree"
    assert _rows_with_status_claims(), (
        "no document in this repository makes a status claim about any invariant here "
        "-- either the artifacts changed shape or this check stopped reaching them")


def test_the_sweep_can_confuse_an_invariant_with_a_function_of_the_same_name():
    """The measured root cause of this sweep's false-positive mode,
    DERIVED rather than listed so it cannot go stale by a name being
    added or removed.

    Not a weakening and not a repair -- it makes the collision a fact the
    next person meets rather than a surprise they diagnose again."""
    import ast

    invariant_ids = set(CURRENT)
    function_names = set()
    for module in sorted((REPO_ROOT / "science").glob("*.py")):
        function_names |= {
            node.name for node in ast.walk(ast.parse(module.read_text()))
            if isinstance(node, ast.FunctionDef)
        }

    collisions = invariant_ids & function_names
    assert collisions, (
        "no invariant id is also a function name, so this sweep can no longer confuse the two "
        "and the deferral recorded in the docstring above is moot -- retire it rather than "
        "leaving it standing"
    )
    assert collisions == {"quantity_is_typed", "no_context_free_property"}, (
        f"the collision set moved to {sorted(collisions)}. A new name that is both an invariant "
        "and a function is a new way for this sweep to misread; re-measure before trusting it."
    )


def _unmarked_claims(predicate=_predicated_of):
    """The check's VERDICT, extracted so the narrowing can be compared on
    what it reports rather than on what it intermediately collects.

    A row whose status word merely moves between the two passing branches
    -- `the field itself is current` and `superseded, and marked as such`
    -- has not changed the answer, and comparing intermediates would call
    that a difference."""
    unmarked = []
    for path, invariant, said, row in _rows_with_status_claims(predicate):
        now = CURRENT[invariant]
        if now in said:
            continue                       # the field itself is current
        siblings = " ".join(v for _, v in _strings(row)).lower()
        if re.search(rf"(?<![\w]){now}(?![\w])", siblings):
            continue                       # superseded, and marked as such
        unmarked.append((path, invariant, tuple(sorted(said)), now))
    return unmarked


def test_no_superseded_status_claim_stands_alone():
    """The property. A superseded status may be RETAINED -- this pair does
    that deliberately -- but only where the current one is stated in the
    same row, so the reader meets both. Standing alone, it is a claim
    about the sibling that the sibling has already contradicted.

    THE DEFERRAL WAS DISCHARGED ON ITS OWN CONDITION, and discharging it
    corrected the diagnosis a second time.

    It fired twice on 2026-08-27 and both were reworded. The note then
    recorded a single root cause -- TWO NAMES ARE BOTH AN INVARIANT ID
    AND A FUNCTION (derived in the test below) -- and demoted the earlier
    `absent`-is-also-English reading to a symptom of it. The deferral
    carried a condition: a THIRD firing, or any firing against an artifact
    that must not be edited, and the sweep must be narrowed rather than
    the prose reworded again.

    IT FIRED A THIRD TIME, and it was not the function collision. The row
    named the INVARIANT `no_context_free_property` explicitly -- "in a
    stronger form than the invariant states" -- and the word `absent`
    appeared in the NEXT SENTENCE as ordinary English. So the two modes
    are independent and the earlier note was wrong to fold the first into
    the second. There are two, and only one of them is now repaired.

    REPAIRED: the predication rule in `_predicated_of`, derived from every
    status claim in this tree rather than invented. Measured against the
    unnarrowed sweep, it changes the flagged set by exactly one row -- the
    false positive -- which is the evidence that it is a narrowing and not
    a weakening.

    UNREPAIRED, and no longer deferred behind a condition it has already
    met: the function/invariant collision. It is stated in
    `_predicated_of` and measured below. Distinguishing a string about the
    function from a string about the invariant needs more than a text
    sweep, and that is a different piece of work rather than a pending
    one."""
    unmarked = _unmarked_claims()

    assert not unmarked, "\n".join(
        f"{path}: says {said} about {invariant!r}, which this repository now "
        f"records as {now!r}, and no field in the same row says so"
        for path, invariant, said, now in unmarked)


def test_a_quoted_requirement_is_verbatim():
    """The response artifact QUOTES the compute layer's requirement text.
    A quote that has been truncated or paraphrased is a claim about what
    the counterparty asked for, and the counterparty cannot see the drift
    -- the same reason the rows addressed are derived rather than listed.

    The requirement was to read the text programmatically. This is the
    check that the reading stayed a reading."""
    # KEYED BY (workload, requirement), because a requirement NAME is not a
    # row identity: `stable_sample_and_variable_identity` is a row in both
    # least_squares and pca with DIFFERENT statement text. Keyed by name,
    # the two collide and one quote silently answers the other's question
    # -- and this check would have compared the surviving quote against the
    # surviving row and passed.
    rows = {(workload, row["requirement"]): row
            for workload, entry in REQUIREMENTS["workloads"].items()
            for row in entry.get("blocking_requirements", ())}
    assert RESPONSE["responses"], "no responses to check"

    collisions = [name for name in {r for _, r in rows}
                  if len({rows[k]["statement"] for k in rows if k[1] == name}) > 1]
    assert collisions, (
        "no requirement name appears in two workloads with different text, so this check cannot "
        "distinguish keying by name from keying by row -- re-measure before trusting it")

    for key, body in RESPONSE["responses"].items():
        workload, _, name = key.partition("::")
        assert name, f"{key} is not a workload::requirement key"
        assert (workload, name) in rows, f"{key} responds to a row the artifact does not list"
        assert body["what_the_requirement_asked"].strip() == rows[(workload, name)]["statement"].strip(), (
            f"{key}: the quoted requirement has drifted from the original")


def test_every_row_the_response_answers_still_exists_upstream():
    """A response to a requirement that has since been withdrawn is a
    different failure from a stale status, and would otherwise pass
    silently: the row simply would not be looked at."""
    # THE OWNER TOKEN DIFFERS ACROSS THE BOUNDARY and this check is what
    # found it: this repository calls itself `daf`, the compute layer
    # addresses its rows to `daq`. Both consistent internally, so nothing
    # inside either repository could see it -- only a JOIN on the token
    # can, and nothing joined until this test did.
    #
    # Resolved by the party naming itself, not by either side renaming the
    # other. `also_known_as` is read rather than assumed, and a response
    # whose owner matches neither token fails here rather than silently
    # matching no rows -- which is how this would otherwise have passed:
    # an empty upstream set compared against an empty answered set is a
    # vacuous pass, and the artifact would have looked answered.
    tokens = {RESPONSE["owner"]}
    alias = RESPONSE.get("also_known_as", "")
    tokens |= {part.strip() for part in re.split(r"[,\s]+", alias.split(",")[0]) if part.strip()}
    assert RESPONSE.get("the_names_are_one_party") is True or len(tokens) == 1, (
        "more than one owner token is in play and the party has not declared them the same")

    # THE ALIAS MUST DENOTE THIS PARTY, NOT MERELY SELECT A CONSISTENT SET.
    #
    # Set equality below asserts that what was ANSWERED equals what was
    # SELECTED, which is self-consistency and not identity. An alias naming
    # the WRONG party selects that party's rows, and a response answering
    # exactly those rows passes it. Probed: with a verbatim quote, that case
    # went straight through.
    #
    # THE FIRST FIX FOR THIS WAS CIRCULAR AND IS WORTH RECORDING. It derived
    # the counterparty's names as "every owner token that is not in
    # `tokens`" -- and `tokens` contains the alias, so the very token under
    # test excluded itself from the set meant to catch it. It passed the
    # probe it was written for. The check was reading its own input as its
    # own authority.
    #
    # Derived from the DECLARED SELF instead, which does not move when the
    # alias does, and only from TOP-LEVEL artifact ownership: a top-level
    # `owner` says whose artifact this is, while an `owner` inside a
    # requirement row says who a row is ADDRESSED to. `scl` is a top-level
    # owner and so is a party's self-name; `daq` is only ever an addressing
    # token, which is exactly what an alias should be.
    declared_self = RESPONSE["owner"]
    counterparty_self_names = set()
    for artifact in (sorted(EXCHANGE.glob("*.yaml"))
                     + sorted((REPO_ROOT / "architecture").glob("*.yaml"))
                     + sorted((REPO_ROOT / "architecture" / "decisions").glob("*.yaml"))):
        try:
            document = loads(artifact.read_text())
        except Exception:
            continue
        owner = document.get("owner") if isinstance(document, dict) else None
        if isinstance(owner, str) and owner != declared_self and len(owner) < 12:
            counterparty_self_names.add(owner)

    assert counterparty_self_names, (
        "no counterparty self-name found; the check below would pass vacuously")
    stolen = tokens & counterparty_self_names
    assert not stolen, (
        f"the alias claims {sorted(stolen)}, which is a token another party uses as its "
        f"OWN artifact ownership. An alias naming the wrong party still selects a "
        f"self-consistent set of rows, so set equality below cannot catch it.")

    # SCOPED TO THE ARTIFACT'S OWN PARTITION, not to a workload named in
    # the response. The previous version read RESPONSE["responds_to_workload"]
    # -- a single hardcoded string -- so a DAQ-owned row in any other
    # workload was not unanswered here, it was INVISIBLE. The row derivation
    # was genuine and its scope was an enumeration of one, which is the
    # shape that looks complete while covering one partition of seven.
    upstream = {f"{workload}::{row['requirement']}"
                for workload, entry in REQUIREMENTS["workloads"].items()
                for row in entry.get("blocking_requirements", ())
                if row["owner"] in tokens}
    assert upstream, (
        f"no row in the artifact is owned by any of {sorted(tokens)} -- an empty upstream "
        f"set would compare equal to an empty answered set and pass vacuously")
    assert len({key.split("::")[0] for key in upstream}) > 1, (
        "every DAQ-owned row is in one workload, so this check cannot distinguish a partition-wide "
        "scope from a single-workload one -- the condition that made the old version look right")

    answered = set(RESPONSE["responses"])
    accounted = set(RESPONSE["row_accounting"]["not_answered_and_why"])
    overlap = answered & accounted
    assert not overlap, f"a row is both answered and recorded as unanswered: {sorted(overlap)}"
    assert answered | accounted == upstream, (
        f"answered {sorted(answered)} and accounted-for {sorted(accounted)} do not together cover "
        f"the artifact's DAQ-owned rows {sorted(upstream)}. A row in neither set is one nobody "
        f"looked at, and nothing else in this repository would notice it.")
    assert RESPONSE["row_accounting"]["daq_owned_rows_upstream"] == len(upstream)


# ----------------------------------------------------------------------
# The narrowing, measured rather than argued
# ----------------------------------------------------------------------

def _admits_everything(value, invariant, word):
    """The rule this sweep used before the third firing."""
    return True


def test_the_narrowing_drops_the_false_positive_and_nothing_else():
    """THE EVIDENCE THAT IT IS A NARROWING AND NOT A WEAKENING.

    Both rules are run over the same tree through the same code path. The
    unnarrowed one flags every row the narrowed one does, plus exactly the
    rows where a status word sits in a different sentence from the
    invariant and the string never says `status`. If that difference ever
    contains a row that is a real claim, this test is the place it shows
    up."""
    rows = lambda predicate: {(path, invariant)
                              for path, invariant, _, _ in _rows_with_status_claims(predicate)}
    wide_rows, narrow_rows = rows(_admits_everything), rows(_predicated_of)
    assert narrow_rows <= wide_rows, "the narrowed rule must not flag anything the wide one missed"
    assert wide_rows - narrow_rows == {
        ("architecture/post_anchor_predictions.yaml.predictions_for_a_second_anchor"
         ".p2_a_per_slice_validity_flag_that_tracks_the_elution_window"
         ".why_it_is_the_sharpest_of_the_four", "no_context_free_property")
    }, (
        f"rows dropped: {sorted(wide_rows - narrow_rows)}. Exactly one row must be dropped and "
        "it must be the measured false positive; any other drop is a weakening."
    )

    wide_verdict = set(_unmarked_claims(_admits_everything))
    narrow_verdict = set(_unmarked_claims(_predicated_of))
    assert narrow_verdict == set(), "the check must be green under the narrowed rule"
    assert {(path, invariant) for path, invariant, _, _ in wide_verdict} == wide_rows - narrow_rows, (
        "and the only thing the narrowing changed about the VERDICT is that false positive -- "
        "a row moving between the two passing branches is not a change in the answer"
    )


def test_a_genuine_stale_claim_is_still_caught_in_every_form_the_tree_uses():
    """DETECTOR PROOF, planted in each shape the corpus actually
    contains. A narrowing that also silenced the real claims would pass
    the test above -- the flagged set would still only lose false
    positives, because the true ones would have been in neither set."""
    invariant = "generation_depth_bounded"
    stale = "vacuously_enforced"
    assert CURRENT[invariant] != stale, "the plant must be a status this repository has moved off"

    same_sentence = f"{invariant} is {stale} and nothing checks it"
    assert _predicated_of(same_sentence, invariant, stale)

    with_the_marker = (f"{invariant} was measured in an earlier phase. "
                       f"Its status is {stale}.")
    assert _predicated_of(with_the_marker, invariant, stale), (
        "a claim spanning two sentences must still be caught when it says `status`"
    )

    ordinary_english = (f"it is {invariant} in a stronger form. "
                        "The context is not merely absent from the document.")
    assert not _predicated_of(ordinary_english, invariant, "absent"), (
        "and the measured false positive must NOT be caught, or nothing was narrowed"
    )

    and_the_limit = f"{invariant} was measured in an earlier phase. It is {stale}."
    assert not _predicated_of(and_the_limit, invariant, stale), (
        "the stated limit, asserted rather than described: a cross-sentence claim with no "
        "`status` marker is now missed. If this ever starts passing, the docstring's "
        "'what it gives up' is stale and must be corrected."
    )
