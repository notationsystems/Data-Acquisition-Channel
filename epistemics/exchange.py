"""Canonical serialization for the DAQ/SCL exchange artifacts.

WHY THIS EXISTS. The joint decision record
(`architecture/decisions/*-workload-selection.yaml`) binds a decision to
the exact measurements that produced it by carrying the SHA-256 of each
Phase-2 exchange artifact. YAML has no canonical serialization, so
without a pinned encoding those hashes are not reproducible and the
traceability guarantee fails. The encoding is pinned by the joint brief
and restated here as executable code rather than prose:

    serialization : YAML 1.2, block style only
    keys          : sorted lexicographically at every level
    anchors/alias : forbidden (never emitted)
    floats        : shortest round-trip repr; no trailing zeros; no
                    exponent unless |x| < 1e-4 or >= 1e16
    strings       : double-quoted only where required
    encoding      : UTF-8, LF line endings, single trailing newline
    hash          : sha256 over the serialized bytes
    reference     : "sha256:<hex>"

WHY NOT `evidence.identity.content_hash`. That function hashes a
canonical JSON PAYLOAD and is the substrate's *evidence* identity. An
exchange artifact is a document, and what must be reproducible is the
digest of its exact committed bytes -- a different question, answered by
hashing the bytes themselves. This is the same thing
`daf/storage/filesystem_store.py` already does for blobs, and it
introduces no new evidence identity: nothing here is an Observation, a
DerivedValue, or an ExecutionRecord, and no id produced here ever enters
the evidence pool.

BOUNDARY. `epistemics` is a leaf layer (AST-asserted): it may import
`evidence.identity.content_hash` and nothing else from the substrate.
This module imports neither -- only `hashlib`, which is stdlib.

ROUND-TRIP CONSTRAINT. Everything emitted here must be readable by
`epistemics/_yaml.py`, the repository's own dependency-free reader, and
must parse identically under PyYAML. Both are asserted by
`tests/test_exchange_canonicalization.py`. That constrains the emitter to
the reader's supported subset: block mappings, block sequences, plain
scalars, and `{}`/`[]` for the empty cases -- no multi-line scalars, no
flow collections with contents, no anchors.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

INDENT = "  "
HASH_PREFIX = "sha256:"

# Bare strings that the reader would decode as a non-string scalar, so
# they must be quoted to survive a round trip as text.
_RESERVED = {"true", "True", "false", "False", "null", "~", "", "{}", "[]"}


class ExchangeSerializationError(ValueError):
    """The document contains something the pinned encoding cannot
    represent. Raised rather than silently degraded, because a silent
    degradation would change the artifact hash and break the decision
    record's binding to its measurements."""


def _format_float(value: float) -> str:
    if not math.isfinite(value):
        raise ExchangeSerializationError(f"non-finite float is not representable: {value!r}")
    magnitude = abs(value)
    if magnitude != 0.0 and (magnitude < 1e-4 or magnitude >= 1e16):
        text = repr(value)  # shortest round-trip; keeps the exponent form
    else:
        text = f"{value!r}"
        if "e" in text or "E" in text:
            # repr chose an exponent inside the plain-form band; expand it.
            text = f"{value:.17f}".rstrip("0")
            if text.endswith("."):
                text += "0"
    if text.endswith(".0"):
        text = text[:-2] + ".0"  # keep exactly one trailing zero: 1.0, never 1. or 1
    return text


def _looks_like_a_yaml_1_1_timestamp(text: str) -> bool:
    """PyYAML resolves a bare `2026-08-25` to `datetime.date` while this
    repository's own reader returns the string. An unquoted date is
    therefore parser-dependent, and a parser-dependent artifact has a
    parser-dependent hash -- exactly what the pinned encoding exists to
    prevent. Found by the cross-parser agreement check, not reasoned
    about in advance. Sexagesimals (`1:30`) are excluded by the `": "`
    rule above only when spaced, so they are caught here too."""
    parts = text.split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return len(parts[0]) == 4
    return ":" in text and all(part.isdigit() for part in text.split(":"))


def _needs_quoting(text: str) -> bool:
    if text in _RESERVED:
        return True
    if text != text.strip():
        return True
    if text[0] in "-?:,[]{}#&*!|>'\"%@`" or ": " in text or " #" in text:
        return True
    if "\n" in text or "\t" in text:
        return True
    if _looks_like_a_yaml_1_1_timestamp(text):
        return True
    for parser in (int, float):
        try:
            parser(text)
        except ValueError:
            continue
        return True
    return False


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        if _needs_quoting(value):
            if "\n" in value or "\t" in value:
                raise ExchangeSerializationError(
                    "multi-line and tab-bearing strings are outside the pinned encoding "
                    f"(the reader has no multi-line scalar support): {value[:60]!r}"
                )
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return value
    raise ExchangeSerializationError(f"unsupported scalar type {type(value).__name__}: {value!r}")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _emit(value: Any, depth: int, lines: list[str]) -> None:
    pad = INDENT * depth
    if isinstance(value, dict):
        for key in sorted(value):
            if not isinstance(key, str):
                raise ExchangeSerializationError(f"mapping keys must be strings, got {key!r}")
            child = value[key]
            rendered_key = _scalar(key)
            if isinstance(child, dict) and child or isinstance(child, list) and child:
                lines.append(f"{pad}{rendered_key}:")
                _emit(child, depth + 1, lines)
            elif isinstance(child, dict):
                lines.append(f"{pad}{rendered_key}: {{}}")
            elif isinstance(child, list):
                lines.append(f"{pad}{rendered_key}: []")
            else:
                lines.append(f"{pad}{rendered_key}: {_scalar(child)}")
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item:
                first = True
                for key in sorted(item):
                    child = item[key]
                    rendered_key = _scalar(key)
                    marker = f"{pad}- " if first else f"{pad}{INDENT}"
                    if isinstance(child, (dict, list)) and child:
                        lines.append(f"{marker}{rendered_key}:")
                        _emit(child, depth + 2, lines)
                    elif isinstance(child, dict):
                        lines.append(f"{marker}{rendered_key}: {{}}")
                    elif isinstance(child, list):
                        lines.append(f"{marker}{rendered_key}: []")
                    else:
                        lines.append(f"{marker}{rendered_key}: {_scalar(child)}")
                    first = False
            elif _is_scalar(item):
                lines.append(f"{pad}- {_scalar(item)}")
            else:
                raise ExchangeSerializationError(
                    "a sequence item must be a scalar or a non-empty mapping "
                    f"(the reader supports no other shape), got {item!r}"
                )
        return
    raise ExchangeSerializationError(f"top-level value must be a mapping or sequence, got {value!r}")


def canonical_yaml(document: Any) -> str:
    """The pinned encoding. Deterministic: the same document always
    produces the same bytes, on any machine, in any process."""
    if not isinstance(document, dict):
        raise ExchangeSerializationError("an exchange artifact must be a mapping at the top level")
    lines: list[str] = []
    _emit(document, 0, lines)
    return "\n".join(lines) + "\n"


def artifact_hash(text: str) -> str:
    """`sha256:<hex>` over the artifact's exact UTF-8 bytes."""
    return HASH_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Any) -> str:
    """The digest of a committed artifact, read as bytes so that what is
    hashed is exactly what is on disk -- never a re-serialization of it,
    which would hide a drift between the file and the encoder."""
    with open(path, "rb") as handle:
        return HASH_PREFIX + hashlib.sha256(handle.read()).hexdigest()
