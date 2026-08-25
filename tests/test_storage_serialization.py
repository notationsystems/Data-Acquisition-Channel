"""Round-trip and corruption-detection tests for daf.storage.serialization."""

from __future__ import annotations

import pytest
from evidence.types import (
    make_claimed_relationship,
    make_derived_grounding,
    make_derived_value,
    make_document,
    make_observation,
    make_record,
    make_referent,
    make_source,
)

from daf.storage import serialization


def test_source_round_trip():
    source = make_source(kind="paper", name="arXiv")
    assert serialization.source_from_dict(serialization.source_to_dict(source)) == source


def test_document_round_trip_preserves_exact_raw_content():
    document = make_document(
        source_id="src-1",
        raw_content="<entry>hello, world</entry>",
        retrieval_method="http:arxiv_api_v1",
        retrieved_at="2026-08-24T00:00:00Z",
    )
    reconstructed = serialization.document_from_dict(serialization.document_to_dict(document))
    assert reconstructed == document
    assert reconstructed.raw_content == "<entry>hello, world</entry>"


def test_record_round_trip():
    record = make_record(document_id="doc-1", locator="loc-1", raw_content="<entry>hi</entry>")
    assert serialization.record_from_dict(serialization.record_to_dict(record)) == record


def test_observation_round_trip_preserves_content_and_metadata():
    observation = make_observation(
        record_ids=("rec-1", "rec-2"),
        extraction_method="xml:arxiv_atom_v1",
        content={"title": "T", "arxiv_id": "a1", "primary_category": None},
        confidence=1.0,
        extracted_at="2026-08-24T00:00:00Z",
    )
    reconstructed = serialization.observation_from_dict(serialization.observation_to_dict(observation))
    assert reconstructed == observation
    assert reconstructed.confidence == 1.0
    assert reconstructed.extracted_at == "2026-08-24T00:00:00Z"


def test_referent_round_trip():
    referent = make_referent(natural_key="Ada Example", kind="author")
    assert serialization.referent_from_dict(serialization.referent_to_dict(referent)) == referent


def test_claimed_relationship_round_trip():
    relationship = make_claimed_relationship(
        from_referent_id="r1",
        to_referent_id="r2",
        type="authored_by",
        observation_id="obs-1",
        confidence=1.0,
    )
    reconstructed = serialization.claimed_relationship_from_dict(
        serialization.claimed_relationship_to_dict(relationship)
    )
    assert reconstructed == relationship


def test_derived_value_round_trip():
    derived_value = make_derived_value(
        derived_from=("obs-1", "obs-2"),
        method="average",
        content={"value": 1.5},
        confidence=0.9,
        derived_at="2026-08-24T00:00:00Z",
    )
    reconstructed = serialization.derived_value_from_dict(serialization.derived_value_to_dict(derived_value))
    assert reconstructed == derived_value


def test_derived_grounding_round_trip():
    grounding = make_derived_grounding(derived_value_id="dv-1", referent_ids=("r1", "r2"))
    reconstructed = serialization.derived_grounding_from_dict(
        serialization.derived_grounding_to_dict(grounding)
    )
    assert reconstructed == grounding


def test_tampered_content_is_detected_as_identity_mismatch():
    document = make_document(
        source_id="src-1",
        raw_content="<entry>hello</entry>",
        retrieval_method="http:arxiv_api_v1",
        retrieved_at="2026-08-24T00:00:00Z",
    )
    payload = serialization.document_to_dict(document)
    payload["raw_content"] = "<entry>tampered</entry>"  # content changed, stored id left stale

    with pytest.raises(serialization.ArtifactIdentityMismatch):
        serialization.document_from_dict(payload)
