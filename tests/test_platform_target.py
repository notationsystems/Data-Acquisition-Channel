"""The platform directive's `have` and `missing` claims, re-measured.

A gap analysis read instead of the tree is worth nothing. Every
load-bearing claim in architecture/platform_target.yaml is checked here
against what is actually present, so a claim that stops being true fails
rather than ageing quietly.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

TARGET = loads((REPO_ROOT / "architecture" / "platform_target.yaml").read_text())
POSITION = TARGET["position_measured_against_each_layer"]


def _grep_count(needle: str, *roots: str) -> int:
    found = 0
    for root in roots:
        for path in (REPO_ROOT / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            found += path.read_text().lower().count(needle.lower())
    return found


def test_the_absences_the_record_claims_are_still_absent():
    """Four zero-counts the record rests on. If any becomes non-zero, a
    layer has moved and the position is stale."""
    assert POSITION["layer_3_outbox_and_workflows"]["have"].startswith("nothing")
    assert _grep_count("outbox", "daf", "science", "epistemics") == 0

    assert "zero occurrences" in POSITION["layer_1_object_storage"]["missing"]
    for absent in ("retention", "access_scope"):
        assert _grep_count(absent, "daf/storage") == 0, (
            f"{absent!r} now appears in daf/storage; layer 1's gap has narrowed and the "
            "record says it has not"
        )

    assert "zero occurrences" in POSITION["layer_2_canonical_state"]["the_substrate_is_not"]
    assert _grep_count("row_level_security", "daf") == 0
    assert "zero occurrences" in POSITION["layer_6_trust_and_assurance"]["missing"]
    assert _grep_count("opentelemetry", "daf", "science", "epistemics") == 0


def test_the_presences_the_record_claims_are_really_there():
    assert (REPO_ROOT / "daf" / "storage" / "blob_store.py").exists()
    assert (REPO_ROOT / "daf" / "execution" / "quarantine.py").exists()
    assert (REPO_ROOT / "daf" / "execution" / "record.py").exists()
    assert (REPO_ROOT / "daf" / "orchestration" / "orchestrator.py").exists()
    from daf.execution.quarantine import QuarantineRecord  # noqa: F401


def test_the_index_really_answers_exactly_the_five_queries_the_record_names():
    """The structural fact the seam revealed: the catalog half is a
    relational store whose five queries are what the directive gives to
    PostgreSQL. Enumerated from the callers, not from the class.
    """
    import ast

    called = set()
    for path in (REPO_ROOT / "daf").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "index"):
                continue
            # `self.index.record_*` is the filesystem store writing its OWN
            # index and is not part of the seam. A first version of this
            # walk did not exclude it and found is_empty and six record_*
            # writers -- which is what a protocol enumerated from the
            # class rather than from its collaborators would have carried,
            # and exactly what daf/storage/evidence_store.py says it
            # refuses to do.
            base = node.value.value
            if isinstance(base, ast.Name) and base.id == "self":
                continue
            called.add(node.attr)

    assert called == {"all_ids", "list_versions", "find_by_content_hash",
                      "list_source_artifacts", "locator_for_document"}, called

    from daf.storage.evidence_store import MetadataIndexQueries
    declared = {name for name in dir(MetadataIndexQueries) if not name.startswith("_")}
    assert declared == called, (
        f"the protocol and the call sites disagree: {sorted(declared ^ called)}. A "
        "protocol carrying a method nobody calls makes the next implementation carry "
        "this one's habits."
    )


def test_bitemporality_is_recorded_as_half_present_and_still_is():
    """`what did we know at T` is answerable; `what was true at T` is
    not. The record says so, and the tree must still agree."""
    claim = POSITION["layer_2_canonical_state"]["bitemporality_is_half_present"]
    assert "is answerable and" in claim and "is not" in claim
    # retrieved_at is on the Document and is caller-supplied.
    from daf.query import Provenance
    assert "retrieved_at" in Provenance.__dataclass_fields__
    # and the other axis is inside one extractor's content, not a dimension.
    holders = [p.name for p in (REPO_ROOT / "daf" / "extractors").glob("*.py")
               if "measurement_time" in p.read_text()]
    assert holders == ["noaa_water_level_measurements.py"], holders


def test_the_directives_projection_rule_is_enforced_and_not_merely_intended():
    """`no serving projection writes canonical truth` is the strongest
    position on the list because it is checked by parsing imports."""
    assert "enforced by parsing imports" in POSITION[
        "layer_5_serving_projections"]["the_strongest_position_on_the_list"]
    for path in (REPO_ROOT / "daf").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text()
        assert "import materials" not in text and "from materials" not in text, path


def test_the_two_items_that_get_more_expensive_are_named_with_why():
    cheap = TARGET["what_is_cheap_now_and_expensive_later"]
    assert "expensive later" in cheap["the_two_items"] or "EXCEPT two" in cheap["the_two_items"]
    assert "three type annotations" in cheap["first_the_store_seam"]
    assert "known AT ACQUISITION" in cheap[
        "second_and_it_is_the_real_one_rights_retention_and_access_scope"]
    assert "policy" in cheap["what_is_NOT_claimed"], (
        "the record must say the vocabularies are the owner's to set, or this layer "
        "invents them"
    )


def test_the_two_platform_records_are_bound_and_neither_is_a_subset():
    """Two records of one subject, written the same day by two sessions.
    proof_integrity.yaml's rule is to keep both, bind them, and give each
    a scope the other names -- not to choose.

    Fails in the state where one stops naming the other, which is how a
    pair of overlapping records drifts into two accounts of one thing.
    """
    other = REPO_ROOT / "architecture" / "data_platform_position.yaml"
    assert other.exists()
    assert "platform_target.yaml" in other.read_text(), (
        "the sibling record does not name this one"
    )

    bond = TARGET["relationship_to_data_platform_position"]
    assert "data_platform_position.yaml" in bond["the_fact"]
    assert "neither knew of the other until the merge" in bond["the_fact"]
    assert "Neither is a subset of the other" in bond[
        "the_disposition_is_the_one_this_pair_already_adopted"]
    # And each must be credited with what the other lacks.
    has = bond["what_each_has_that_the_other_does_not"]
    assert "IMPORT and DECLARED DEPENDENCY" in has
    assert "two substitutions and not one" in has
