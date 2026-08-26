"""The shared tightening for the two verbatim pass-through extractors.

WHY THIS EXISTS. `local_dataset` and `graph_dataset` are deliberately
generic transports: they carry whatever a source record declares into
`Observation.content` without interpreting it. That genericity is correct
and is not what this module changes. What it changes is that a
pass-through route was, measurably, the way to get into content the
shapes every gate downstream exists to refuse -- so a rule enforced at
the gate was enforceable only on the paths that did not need it.

TWO SHAPES ARE REFUSED OR NORMALIZED HERE, both for reasons measured in
this repository rather than anticipated:

NON-FINITE NUMBERS ARE REFUSED. A NaN or an infinity reaching content
does three things quietly. `evidence.identity.content_hash` serializes it
as bare `NaN`/`Infinity`, which is NOT valid strict JSON, so the
Observation's id is computed over bytes no conformant reader in another
language will accept; `FilesystemEvidenceStore` then persists that
literal to disk; and `nan != nan`, so the value is not equal to itself
after a round trip. Measured, all three. A sentinel is also exactly what
`explicit_missing_value_semantics` forbids: missing must never be
expressible as an in-range value.

DICT-VALUED ENTRIES ARE FROZEN. Phase 35 measured that Phase 34 imposed
the hashable-Mapping representation at the READ boundary plus NOAA's
extractor by hand, and that `graph_dataset` therefore still constructed a
plain dict -- which raises `TypeError: unhashable type: 'dict'` in
`materials.analysis` IN-PROCESS and is repaired only by a restart. That
asymmetry was recorded and deliberately not fixed then, because fixing it
inside one extractor would have been per-source patching. Fixed here
instead, once, at the seam both pass-through routes share.

WHAT IS NOT DONE HERE. No key is added, renamed, dropped or interpreted.
No schema is imposed. A record that declares nothing this module refuses
passes through byte-for-byte as before, which is what keeps these
extractors generic transports rather than typed ones.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping

from daf.storage.frozen_mapping import FrozenMapping


class PassthroughRefusal(ValueError):
    """A source record declared a value that cannot be carried honestly.
    Raised at extraction -- loud and early, at the boundary that read it
    -- rather than admitted and left to fail at a consumer later."""


def _reject_non_finite(value: Any, path: str, record_id: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    if math.isfinite(value):
        return
    raise PassthroughRefusal(
        f"record {record_id!r} declares a non-finite number at {path}: {value!r}. "
        "It cannot be carried: content_hash would serialize it as invalid strict JSON, it would "
        "persist as that literal, and it would not compare equal to itself. If the intent is a "
        "missing value, state it explicitly -- see science/table.py's value_absence reasons."
    )


def _walk_and_tighten(value: Any, path: str, record_id: str) -> Any:
    """Depth-first: refuse non-finite numbers anywhere, freeze every
    Mapping. Lists are traversed but stay lists -- `freeze_nested_mappings`
    does not recurse into them either, and changing that here would make
    the two halves of the representation disagree."""
    if isinstance(value, dict):
        return FrozenMapping(
            {key: _walk_and_tighten(item, f"{path}.{key}", record_id) for key, item in value.items()}
        )
    if isinstance(value, list):
        return [_walk_and_tighten(item, f"{path}[{index}]", record_id) for index, item in enumerate(value)]
    _reject_non_finite(value, path, record_id)
    return value


def tighten_passthrough_content(content: Mapping[str, Any], record_id: str) -> Dict[str, Any]:
    """Applied by both pass-through extractors to whatever the source
    declared, immediately before it becomes `Observation.content`."""
    return {key: _walk_and_tighten(value, key, record_id) for key, value in content.items()}
