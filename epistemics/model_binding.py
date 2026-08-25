"""Binding constraints, checked against `architecture/model_binding.yaml`.

There are no bindings in this repository. `check_bindings` therefore
passes vacuously today -- and that is the point of writing it now rather
than later: the first binding anyone adds is checked by a rule that was
authored before there was a binding to accommodate.

`cross_vendor_validation` is a BOUNDARY requirement, not an independence
claim. Two vendors are not thereby statistically independent, and this
module says so in one place (`INDEPENDENCE_CAVEAT`) rather than letting
the constraint's name imply more than it delivers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from epistemics._yaml import loads

ARCHITECTURE_DIR = Path(__file__).resolve().parent.parent / "architecture"
MODEL_BINDING_YAML = ARCHITECTURE_DIR / "model_binding.yaml"

PROPOSING = "proposing"
ACCEPTING = "accepting"

INDEPENDENCE_CAVEAT = (
    "different vendors are not thereby statistically independent; "
    "the constraint is a boundary requirement, not an independence claim"
)


class BindingViolation(ValueError):
    """A declared binding breaks a constraint the architecture states."""


@dataclass(frozen=True)
class Binding:
    role: str
    vendor: str
    snapshot: str
    hosted: bool
    lineage: str


def load_bindings(path: Path = MODEL_BINDING_YAML) -> Tuple[Mapping[str, Any], Tuple[Binding, ...]]:
    document = loads(path.read_text())
    roles: Dict[str, Any] = document["roles"] or {}
    declared = document["bindings"] or {}
    bindings = tuple(
        Binding(
            role=role,
            vendor=spec["vendor"],
            snapshot=spec["snapshot"],
            hosted=bool(spec.get("hosted", True)),
            lineage=roles.get(role, {}).get("lineage", PROPOSING),
        )
        for role, spec in sorted(declared.items())
    )
    return document, bindings


def check_bindings(bindings: Tuple[Binding, ...]) -> None:
    """Raises on the first violation. Vacuous while `bindings` is empty."""
    proposing = tuple(b for b in bindings if b.lineage == PROPOSING)
    accepting = tuple(b for b in bindings if b.lineage == ACCEPTING)

    proposing_vendors = {b.vendor for b in proposing}
    for validator in accepting:
        if validator.vendor in proposing_vendors:
            raise BindingViolation(
                f"cross_vendor_validation: the {validator.role} binding's vendor "
                f"{validator.vendor!r} also appears in the proposing lineage "
                f"{sorted(proposing_vendors)}"
            )
        if any(b.role == validator.role for b in proposing):
            raise BindingViolation(
                f"no_self_validation: {validator.role!r} appears in both lineages"
            )

    for b in bindings:
        if not b.snapshot or b.snapshot.startswith("<"):
            raise BindingViolation(
                f"{b.role!r} declares snapshot {b.snapshot!r}; a placeholder is not a pin"
            )
