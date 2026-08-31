"""A reference API adapter — what a future integration writes.

THIS EXISTS TO BE COMPARED AGAINST. PC-6's last acceptance criterion is
that the manual adapter writes the same canonical events an API adapter
will, verified by a test asserting the two produce identical shapes. A
claim like that is worth nothing without a second adapter to check it
against, so this is a genuinely separate code path over a genuinely
different input shape: a nested TMS-style JSON payload with its own field
names, its own nesting, and its own idea of what a timestamp is.

IT IS NOT A REAL INTEGRATION and does not pretend to be. It is the shape
argument, made checkable.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Tuple

from commerce.events import (ACCESSORIAL_CLAIMED, ACCESSORIAL_PAID, CONTRIBUTION_EXPECTED,
                             CONTRIBUTION_REALIZED, PICKUP_ACTUAL, PICKUP_PROMISED,
                             RATE_ACCEPTED, RATE_INVOICED, RATE_QUOTED, TRANSIT_ESTIMATED,
                             TRANSIT_REALIZED, EventRefusal, LoadEvent, Source)

PAYLOAD_NOT_UNDERSTOOD = "PAYLOAD_NOT_UNDERSTOOD"
UNMAPPED_PAYLOAD_FIELD = "UNMAPPED_PAYLOAD_FIELD"

#: The vendor's field names, mapped onto the canonical vocabulary. This
#: map is the ENTIRE integration: everything else is shared.
FIELD_TO_KIND: Mapping[str, str] = {
    "quotedRate": RATE_QUOTED,
    "acceptedRate": RATE_ACCEPTED,
    "invoicedRate": RATE_INVOICED,
    "scheduledPickup": PICKUP_PROMISED,
    "actualPickup": PICKUP_ACTUAL,
    "estTransitDays": TRANSIT_ESTIMATED,
    "actualTransitDays": TRANSIT_REALIZED,
    "accessorialClaimed": ACCESSORIAL_CLAIMED,
    "accessorialPaid": ACCESSORIAL_PAID,
    "expectedMargin": CONTRIBUTION_EXPECTED,
    "realizedMargin": CONTRIBUTION_REALIZED,
}

UNIT_OF_KIND: Mapping[str, str] = {
    RATE_QUOTED: "CAD", RATE_ACCEPTED: "CAD", RATE_INVOICED: "CAD",
    PICKUP_PROMISED: "epoch_day", PICKUP_ACTUAL: "epoch_day",
    TRANSIT_ESTIMATED: "days", TRANSIT_REALIZED: "days",
    ACCESSORIAL_CLAIMED: "CAD", ACCESSORIAL_PAID: "CAD",
    CONTRIBUTION_EXPECTED: "CAD", CONTRIBUTION_REALIZED: "CAD",
}


def from_payload(payload: Mapping[str, Any]) -> Tuple[LoadEvent, ...]:
    """One TMS load record becomes N canonical events.

    An unmapped measure field is REFUSED rather than skipped. A vendor
    that adds `fuelSurchargeQuoted` next quarter would otherwise have it
    silently dropped, and the residual history would quietly stop covering
    part of the rate.
    """
    if not isinstance(payload, dict) or "loadId" not in payload:
        raise EventRefusal(PAYLOAD_NOT_UNDERSTOOD,
                           "the payload must be an object carrying `loadId`.")
    load = str(payload["loadId"])
    observed = payload.get("observed") or {}
    if not isinstance(observed, dict):
        raise EventRefusal(PAYLOAD_NOT_UNDERSTOOD, "`observed` must be an object of measures.")

    unmapped = sorted(set(observed) - set(FIELD_TO_KIND))
    if unmapped:
        raise EventRefusal(
            UNMAPPED_PAYLOAD_FIELD,
            f"load {load!r} carries measures this adapter does not map: {unmapped}. Refused "
            "rather than skipped — a silently dropped measure is a residual history that quietly "
            "stops covering part of the load.",
        )

    events = []
    for field, value in observed.items():
        if value is None:
            continue
        kind = FIELD_TO_KIND[field]
        events.append(LoadEvent(
            load=load,
            kind=kind,
            value=float(value),
            unit=UNIT_OF_KIND[kind],
            source=Source(
                source_id=f"tms:{payload.get('system', 'reference')}",
                source_class="asserted",
                method="api",
                known_at=str(payload["knownAt"]),
                recorded_by=None,
                artifact=str(payload.get("recordId")) if payload.get("recordId") else None,
                rung="api",
            ),
            period_start=payload.get("periodStart"),
            period_end=payload.get("periodEnd"),
        ))
    return tuple(events)


def load_payloads(raw: str) -> Tuple[LoadEvent, ...]:
    try:
        payloads = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EventRefusal(PAYLOAD_NOT_UNDERSTOOD, f"not JSON ({exc.msg})") from None
    if not isinstance(payloads, list):
        raise EventRefusal(PAYLOAD_NOT_UNDERSTOOD, "expected a JSON array of load records.")
    out: List[LoadEvent] = []
    for payload in payloads:
        out.extend(from_payload(payload))
    return tuple(out)
