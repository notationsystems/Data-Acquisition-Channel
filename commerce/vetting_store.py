"""Vetting observations, persisted — so a verdict is reproducible later.

A verdict computed from observations nobody kept is a verdict nobody can
re-take. The store is append-only JSONL like the book and the register,
and for the same reason: an insurance record that could be edited in
place is a coverage history that can be corrected into compliance.

`as at` IS THE QUERY. Every read takes an asof and filters on `known_at`,
so the question `what verdict would we have reached on the fifth` is
answerable on the fifteenth — which is the question a dispute actually
asks.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from commerce.vetting import OBSERVATION_KINDS, VettingObservation, VettingProvenance

DEFAULT_PATH = pathlib.Path(os.environ.get(
    "COMMERCE_VETTING",
    str(pathlib.Path(os.environ.get("COMMERCE_LEDGER", "commerce-ledger.jsonl")).parent
        / "commerce-vetting.jsonl")))

VETTING_LINE_IS_NOT_JSON = "VETTING_LINE_IS_NOT_JSON"
VETTING_LINE_LACKS_A_KIND = "VETTING_LINE_LACKS_A_KIND"
VETTING_EMPTY_BECAUSE_IT_DOES_NOT_EXIST = "VETTING_EMPTY_BECAUSE_IT_DOES_NOT_EXIST"


@dataclass(frozen=True)
class VettingRead:
    observations: Tuple[VettingObservation, ...]
    bad: Tuple[Tuple[int, str], ...]
    lines: int
    path: str
    empty_because: Optional[str] = None

    def for_carrier(self, carrier: str) -> Tuple[VettingObservation, ...]:
        return tuple(o for o in self.observations if o.subject == carrier)


def append(observations: Sequence[VettingObservation], *,
           path: pathlib.Path = DEFAULT_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for o in observations:
            handle.write(json.dumps({
                "subject": o.subject, "kind": o.kind, "value": o.value, "unit": o.unit,
                "period_start": o.period_start, "period_end": o.period_end,
                "known_at": o.known_at, "supersedes": o.supersedes,
                "provenance": {"source_id": o.provenance.source_id,
                               "source_class": o.provenance.source_class,
                               "rung": o.provenance.rung,
                               "retrieved_at": o.provenance.retrieved_at,
                               "artifact_id": o.provenance.artifact_id},
            }, sort_keys=True) + "\n")
    return len(observations)


def read(*, path: pathlib.Path = DEFAULT_PATH) -> VettingRead:
    if not path.exists():
        return VettingRead((), (), 0, str(path), empty_because=(
            f"{VETTING_EMPTY_BECAUSE_IT_DOES_NOT_EXIST}: no vetting store at {path}. No carrier "
            "has any recorded observation, so every verdict is undetermined — which is correct "
            "and is not the same as every carrier being clean."))
    observations: List[VettingObservation] = []
    bad: List[Tuple[int, str]] = []
    lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            lines += 1
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                bad.append((number, f"{VETTING_LINE_IS_NOT_JSON}: {exc.msg}"))
                continue
            if not isinstance(payload, dict) or payload.get("kind") not in OBSERVATION_KINDS:
                bad.append((number, VETTING_LINE_LACKS_A_KIND))
                continue
            body = payload.get("provenance") or {}
            try:
                observations.append(VettingObservation(
                    subject=str(payload["subject"]), kind=str(payload["kind"]),
                    value=payload["value"], unit=payload.get("unit"),
                    period_start=str(payload["period_start"]),
                    period_end=payload.get("period_end"),
                    known_at=str(payload["known_at"]),
                    supersedes=payload.get("supersedes"),
                    provenance=VettingProvenance(
                        source_id=str(body.get("source_id", "")),
                        source_class=str(body.get("source_class", "")),
                        rung=int(body.get("rung", 4)),
                        retrieved_at=str(body.get("retrieved_at", "")),
                        artifact_id=body.get("artifact_id"))))
            except (KeyError, ValueError) as exc:
                bad.append((number, str(exc)))
    return VettingRead(tuple(observations), tuple(bad), lines, str(path))
