"""to_dict / from_dict for each evidence.types object.

Every `*_from_dict` reconstructs its object by calling the SAME `make_*`
factory `scout.pipeline.run_scout` itself calls at acquisition time, from
the persisted raw fields (never from the persisted `id` directly), then
verifies the recomputed id matches the id it was stored under. This is
deliberate, not incidental: it means persistence can never silently
diverge from `evidence.identity.content_hash`'s own definition of
identity, and on-disk corruption or tampering is caught on read rather
than trusted -- with ONE measured exception that `strict_json_loads`
below exists to remove. See its docstring: recomputation is only as
strong as the bytes it runs over.

No new identity scheme is introduced anywhere in this module.

PHASE 34 -- `observation_from_dict`/`derived_value_from_dict` reconstruct
`content` through `freeze_nested_mappings` (`daf/storage/frozen_mapping.py`)
rather than passing `payload["content"]` straight through. This is a
no-op for every content shape shipped before this phase (none has a
dict-valued content entry), and exists so a `FrozenMapping`-valued entry
(e.g. `conditions`) an extractor constructs survives a disk round trip as
itself, not as the plain, unhashable `dict` `json.loads` would otherwise
produce -- see `frozen_mapping.py`'s own docstring for the measured
reason this is required on the read side, not just the write side.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from evidence.types import (
    ClaimedRelationship,
    DerivedGrounding,
    DerivedValue,
    Document,
    Observation,
    Record,
    Referent,
    Source,
    make_claimed_relationship,
    make_derived_grounding,
    make_derived_value,
    make_document,
    make_observation,
    make_record,
    make_referent,
    make_source,
)

from daf.storage.frozen_mapping import freeze_nested_mappings


#: The three bare words `json.dumps` emits for non-finite floats and
#: `json.loads` silently accepts. None of them is JSON (RFC 8259 section 6
#: admits no such literal); all three are a Python extension.
NON_JSON_CONSTANTS = ("NaN", "Infinity", "-Infinity")


class NonJsonConstantError(ValueError):
    """A stored file used a Python JSON extension, so it is not JSON."""


def strict_json_loads(text: str) -> Any:
    """`json.loads`, refusing the three constants that are not JSON.

    WHY THIS EXISTS, MEASURED. The writers in this repository all pass
    `allow_nan=False`, so none of them can emit a bare NaN. The readers
    were plain `json.loads`, which accepts one. A writer-only gate is a
    half-gate: it stops this repository producing the file and does
    nothing about consuming one, and files arrive from elsewhere --
    another tool, another language, an older commit, a hand edit.

    What made it worth closing rather than noting is what happened to a
    NaN-bearing file that DID arrive. It was not rejected and it was not
    detected:

      * `json.loads` read the bare `NaN` back as a float
      * `observation_from_dict` recomputed the id from those fields
      * `_verify` PASSED -- `content_hash` is deterministic over the
        bytes it is handed, so the recomputed id matched the stored one
      * and the value it certified was not equal to itself

    So the integrity check confirmed an identity, correctly by its own
    rules, over bytes that no conformant JSON implementation in any
    language can parse. Recomputable here; unverifiable by anyone else.
    That is the same divergence the canonical YAML emitter refuses a
    nested sequence for -- two readers, same bytes, different outcomes --
    arriving in the JSON identity path instead of the YAML one.

    This is a REFUSAL, not a normalization, and the distinction is the
    one section 6.2 turns on. Coercing NaN to null or to a sentinel on
    read would relocate the ambiguity into the store. Refusing says the
    file is not JSON, which is simply true."""
    def _refuse(constant: str) -> Any:
        raise NonJsonConstantError(
            f"stored file contains the bare literal {constant!r}, which is a Python "
            f"json extension and not JSON. Any id computed over these bytes is "
            f"reproducible only by this implementation, so it cannot be verified "
            f"independently -- which is the one thing a content address is for."
        )

    return json.loads(text, parse_constant=_refuse)



class ArtifactIdentityMismatch(RuntimeError):
    """Raised when a persisted object's own fields, re-run through the
    exact `make_*` factory used at acquisition time, do not reproduce the
    id it was stored under. This is the corruption/tamper detector: it
    can only fire if the on-disk JSON was altered after being written,
    since `make_*` is a pure, deterministic function of those fields."""


def _verify(type_name: str, stored_id: str, recomputed_id: str) -> None:
    if stored_id != recomputed_id:
        raise ArtifactIdentityMismatch(
            f"{type_name} persisted under id {stored_id!r} re-hashes to {recomputed_id!r} -- "
            "stored content no longer matches its own content-addressed identity"
        )


def source_to_dict(source: Source) -> Dict[str, Any]:
    return {"id": source.id, "kind": source.kind, "name": source.name}


def source_from_dict(payload: Dict[str, Any]) -> Source:
    reconstructed = make_source(kind=payload["kind"], name=payload["name"])
    _verify("Source", payload["id"], reconstructed.id)
    return reconstructed


def document_to_dict(document: Document) -> Dict[str, Any]:
    return {
        "id": document.id,
        "source_id": document.source_id,
        "raw_content": document.raw_content,
        "retrieval_method": document.retrieval_method,
        "retrieved_at": document.retrieved_at,
    }


def document_from_dict(payload: Dict[str, Any]) -> Document:
    reconstructed = make_document(
        source_id=payload["source_id"],
        raw_content=payload["raw_content"],
        retrieval_method=payload["retrieval_method"],
        retrieved_at=payload["retrieved_at"],
    )
    _verify("Document", payload["id"], reconstructed.id)
    return reconstructed


def record_to_dict(record: Record) -> Dict[str, Any]:
    return {
        "id": record.id,
        "document_id": record.document_id,
        "locator": record.locator,
        "raw_content": record.raw_content,
    }


def record_from_dict(payload: Dict[str, Any]) -> Record:
    reconstructed = make_record(
        document_id=payload["document_id"],
        locator=payload["locator"],
        raw_content=payload["raw_content"],
    )
    _verify("Record", payload["id"], reconstructed.id)
    return reconstructed


def observation_to_dict(observation: Observation) -> Dict[str, Any]:
    return {
        "id": observation.id,
        "record_ids": list(observation.record_ids),
        "extraction_method": observation.extraction_method,
        "content": dict(observation.content),
        "confidence": observation.confidence,
        "extracted_at": observation.extracted_at,
    }


def observation_from_dict(payload: Dict[str, Any]) -> Observation:
    reconstructed = make_observation(
        record_ids=tuple(payload["record_ids"]),
        extraction_method=payload["extraction_method"],
        content=freeze_nested_mappings(payload["content"]),
        confidence=payload["confidence"],
        extracted_at=payload["extracted_at"],
    )
    _verify("Observation", payload["id"], reconstructed.id)
    return reconstructed


def referent_to_dict(referent: Referent) -> Dict[str, Any]:
    return {"id": referent.id, "natural_key": referent.natural_key, "kind": referent.kind}


def referent_from_dict(payload: Dict[str, Any]) -> Referent:
    reconstructed = make_referent(natural_key=payload["natural_key"], kind=payload["kind"])
    _verify("Referent", payload["id"], reconstructed.id)
    return reconstructed


def claimed_relationship_to_dict(relationship: ClaimedRelationship) -> Dict[str, Any]:
    return {
        "id": relationship.id,
        "from_referent_id": relationship.from_referent_id,
        "to_referent_id": relationship.to_referent_id,
        "type": relationship.type,
        "observation_id": relationship.observation_id,
        "confidence": relationship.confidence,
    }


def claimed_relationship_from_dict(payload: Dict[str, Any]) -> ClaimedRelationship:
    reconstructed = make_claimed_relationship(
        from_referent_id=payload["from_referent_id"],
        to_referent_id=payload["to_referent_id"],
        type=payload["type"],
        observation_id=payload["observation_id"],
        confidence=payload["confidence"],
    )
    _verify("ClaimedRelationship", payload["id"], reconstructed.id)
    return reconstructed


def derived_value_to_dict(derived_value: DerivedValue) -> Dict[str, Any]:
    return {
        "id": derived_value.id,
        "derived_from": list(derived_value.derived_from),
        "method": derived_value.method,
        "content": dict(derived_value.content),
        "confidence": derived_value.confidence,
        "derived_at": derived_value.derived_at,
    }


def derived_value_from_dict(payload: Dict[str, Any]) -> DerivedValue:
    reconstructed = make_derived_value(
        derived_from=payload["derived_from"],
        method=payload["method"],
        content=freeze_nested_mappings(payload["content"]),
        confidence=payload["confidence"],
        derived_at=payload["derived_at"],
    )
    _verify("DerivedValue", payload["id"], reconstructed.id)
    return reconstructed


def derived_grounding_to_dict(grounding: DerivedGrounding) -> Dict[str, Any]:
    return {
        "id": grounding.id,
        "derived_value_id": grounding.derived_value_id,
        "referent_ids": list(grounding.referent_ids),
    }


def derived_grounding_from_dict(payload: Dict[str, Any]) -> DerivedGrounding:
    reconstructed = make_derived_grounding(
        derived_value_id=payload["derived_value_id"],
        referent_ids=payload["referent_ids"],
    )
    _verify("DerivedGrounding", payload["id"], reconstructed.id)
    return reconstructed
