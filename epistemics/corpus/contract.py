"""data-acquisition-fabric's conformance to the Notation Systems corpus contract.

WHAT THE CONTRACT IS FOR. Notation Systems operates more than one
provenance-bearing corpus. Two of them had independently built a lattice,
both called it the evidence class, and neither knew the other existed --
measured 2026-08-31. They are not duplicates. This fabric classifies HOW A
VALUE CAME TO EXIST (`asserted`, `computed`, `derived`, `measured`, fixed
at ingest). Payload Terminal classifies HOW HARD THE EVIDENCE IS
(`reported`, `estimated`, `representative`, `derived`, ranked). Two axes
of one property, each named after the whole.

WHY THIS FABRIC DOES NOT IMPLEMENT THE OTHER AXIS, and why that is a
decision rather than a gap. An acquisition fabric records how a value was
OBTAINED. Deciding how much a claim about the world is worth is a
different act, performed by whoever is making the claim, and assigning a
strength at ingest would be fabricating an assessment nobody made. The
contract records this as `absence_is_deliberate: true`, distinct from
Payload Terminal's missing production class, which is an open gap.

THE COLLISION THIS EXISTS TO STOP. `VOCABULARY_MAP` maps the presentation
term `reported` onto `asserted`. In Payload Terminal, `reported` is the
HARDEST claim strength there is. A value leaving here as `asserted` and
arriving there as `reported` would be promoted from *a party claimed
this* to *hardest available evidence* by nothing but a shared spelling.
The contract refuses that translation by name; this module is where the
refusal is checked against the code on this side.

WHAT THIS MODULE IS NOT. A second definition of the vocabulary.
`epistemics.evidence_class` and `architecture/evidence_class.yaml` own
that between them, and `tests/test_corpus_contract.py` asserts all three
agree rather than letting them drift. Two normative lists of one fact is
the defect the contract exists to close.

BOUNDARY: standard library only. No pool, no daf, no network, no clock.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Dict, Mapping, Tuple

#: sha256 of `contract.json` as vendored beside this file. Pinned so that
#: editing the local copy fails a test rather than silently redefining what
#: this corpus claims to conform to. It does NOT prove the copy matches the
#: canonical one in the archive -- see `CONFORMANCE_LIMIT`.
CONTRACT_DIGEST = "0622f794e1eb08f13eba3eee341043a8a3833aa1449d618954c41963c460bf7d"

CONTRACT_ID = "notation-systems.corpus.provenance"
CONTRACT_VERSION = "1.0.0"

CONTRACT_PATH = pathlib.Path(__file__).resolve().parent / "contract.json"

#: The axes this corpus implements, and where each one lives.
AXES_IMPLEMENTED: Mapping[str, str] = {
    "production_class": "epistemics/evidence_class.py:INGEST_CLASSES",
}

#: The axes this corpus does not implement. Deliberate, with the reason.
AXES_ABSENT: Mapping[str, str] = {
    "claim_strength": "DELIBERATE -- assessing a claim is not acquiring a value.",
    "interest": "DELIBERATE -- the stake behind a statement is a property of the claim, not of the fetch.",
}

#: What passing the conformance test does and does not establish. Stated in
#: the module rather than only in the test, because the limit is a property
#: of the arrangement and a reader of this module is who needs to know it.
CONFORMANCE_LIMIT = (
    "Each corpus verifies its own vendored copy against its own pin. Two equally "
    "stale copies pass every check either side has. Byte identity across corpora "
    "is coverage for divergence, not currency."
)


def contract_bytes() -> bytes:
    """The vendored contract, as bytes, so the digest is over what was read."""
    return CONTRACT_PATH.read_bytes()


def contract() -> Dict[str, Any]:
    """The vendored contract, parsed. Raises if it is not the pinned file."""
    raw = contract_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != CONTRACT_DIGEST:
        raise ContractDigestMismatch(
            f"{CONTRACT_PATH} hashes to {digest}, not the pinned {CONTRACT_DIGEST}. "
            "The vendored contract was edited; re-pin deliberately or restore it."
        )
    return json.loads(raw.decode("utf-8"))


class ContractDigestMismatch(Exception):
    """The vendored contract is not the file this module was written against."""


def refused_translations() -> Tuple[str, ...]:
    """Terms the contract refuses to translate across a corpus boundary.

    A caller at a boundary asks this rather than consulting a mapping table
    of its own, so the refusal cannot be forgotten in one direction.
    """
    terms = contract()["contested_terms"]
    return tuple(
        sorted(
            name
            for name, spec in terms.items()
            if name != "note" and spec.get("translation") == "refused"
        )
    )
