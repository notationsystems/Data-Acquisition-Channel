"""Reads `architecture/invariants.yaml`.

The YAML is the source of truth for what the architecture claims; this
module is the only code that reads it, so there is exactly one place
where a status vocabulary is interpreted.

`STATUSES` is closed on purpose. An invariant whose status is not one of
these six is a status someone invented to avoid saying `absent`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from epistemics._yaml import loads

ARCHITECTURE_DIR = Path(__file__).resolve().parent.parent / "architecture"
INVARIANTS_YAML = ARCHITECTURE_DIR / "invariants.yaml"
CORE_YAML = ARCHITECTURE_DIR / "core.yaml"

ENFORCED = "enforced"
VACUOUSLY_ENFORCED = "vacuously_enforced"
PARTIALLY_ENFORCED = "partially_enforced"
REPRESENTED_UNENFORCED = "represented_unenforced"
BLOCKED = "blocked"
ABSENT = "absent"
STATUSES: Tuple[str, ...] = (
    ABSENT,
    BLOCKED,
    ENFORCED,
    PARTIALLY_ENFORCED,
    REPRESENTED_UNENFORCED,
    VACUOUSLY_ENFORCED,
)

# A status that claims something is checked must name the check; a status
# that claims something is not must name the blocker or the gap.
_REQUIRES_ENFORCEMENT = (ENFORCED, VACUOUSLY_ENFORCED, PARTIALLY_ENFORCED, REPRESENTED_UNENFORCED)
_REQUIRES_REASON = {BLOCKED: "blocked_by", ABSENT: "gap"}


class InvariantDeclarationError(ValueError):
    """The declaration is internally inconsistent -- a status claiming a
    check without naming one, or a gap without a reason."""


@dataclass(frozen=True)
class Invariant:
    id: str
    rule: str
    status: str
    enforcement: Optional[str]
    raw: Mapping[str, Any]


def core_version(path: Path = CORE_YAML) -> str:
    document = loads(path.read_text())
    return f"core@{document['version']}"


def load_invariants(path: Path = INVARIANTS_YAML) -> Tuple[Invariant, ...]:
    document = loads(path.read_text())
    return tuple(
        Invariant(
            id=entry["id"],
            rule=entry["rule"],
            status=entry["status"],
            enforcement=entry.get("enforcement"),
            raw=entry,
        )
        for entry in document["invariants"]
    )


def check_declarations(invariants: Tuple[Invariant, ...]) -> None:
    seen = set()
    for inv in invariants:
        if inv.id in seen:
            raise InvariantDeclarationError(f"duplicate invariant id {inv.id!r}")
        seen.add(inv.id)
        if inv.status not in STATUSES:
            raise InvariantDeclarationError(
                f"{inv.id!r} declares status {inv.status!r}, not one of {list(STATUSES)}"
            )
        if inv.status in _REQUIRES_ENFORCEMENT and not inv.enforcement:
            raise InvariantDeclarationError(
                f"{inv.id!r} is {inv.status} but names no enforcement"
            )
        required = _REQUIRES_REASON.get(inv.status)
        if required and not inv.raw.get(required):
            raise InvariantDeclarationError(
                f"{inv.id!r} is {inv.status} but names no {required!r}"
            )


def by_status(invariants: Tuple[Invariant, ...], status: str) -> Tuple[Invariant, ...]:
    return tuple(i for i in invariants if i.status == status)
