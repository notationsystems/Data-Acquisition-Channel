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


def _rows_with_status_claims():
    """Every mapping in the requirements artifact that names one of this
    repository's invariants together with a status word."""
    found = []

    def visit(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str):
                    for invariant in CURRENT:
                        if invariant not in value:
                            continue
                        said = [w for w in VOCABULARY
                                if re.search(rf"(?<![\w]){w}(?![\w])", value)]
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


def test_no_superseded_status_claim_stands_alone():
    """The property. A superseded status may be RETAINED -- this pair does
    that deliberately -- but only where the current one is stated in the
    same row, so the reader meets both. Standing alone, it is a claim
    about the sibling that the sibling has already contradicted.

    A MEASURED FALSE-POSITIVE MODE, recorded rather than silently worked
    around. This sweep is TEXT PROXIMITY: a row naming an invariant and a
    status-vocabulary word must also name the current status. But `absent`
    is both a status in that vocabulary AND an ordinary domain word in this
    repository -- `uncertainty_kind: absent`, `value_absence`, a missing
    unit. A row discussing absence near an invariant name trips this with
    no status claim in it.

    It fired that way once, on 2026-08-27, against a requirement-response
    row describing a missing unit beside `quantity_is_typed`. The wording
    was changed to `missing`, which is clearer anyway -- and the collision
    is recorded HERE because rewording to get past a check, without saying
    the check misread, is how a proxy's failure mode gets buried by the
    person best placed to report it. The sweep is not weakened: a genuine
    stale claim using the word `absent` is still caught, and the cost of
    this mode is a reworded sentence rather than a missed claim."""
    unmarked = []
    for path, invariant, said, row in _rows_with_status_claims():
        now = CURRENT[invariant]
        if now in said:
            continue                       # the field itself is current
        siblings = " ".join(v for _, v in _strings(row)).lower()
        if re.search(rf"(?<![\w]){now}(?![\w])", siblings):
            continue                       # superseded, and marked as such
        unmarked.append((path, invariant, said, now))

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
