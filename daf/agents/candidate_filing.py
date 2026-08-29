"""Refuse the shapes EDGAR_SCOUT's contract forbids.

The contract's prohibitions -- do not invent accession numbers, an
unknown is null, uncertainty is expressed inside the schema -- are prose
until something rejects the output that violates them. This is that
something.

IT IS NOT A JSON SCHEMA ENGINE AND MUST NOT BE MISTAKEN FOR ONE. It
implements the keywords the prohibitions actually rest on and REFUSES a
schema using any keyword it does not implement, so its scope is
mechanical rather than a claim in a docstring. A validator that silently
ignored an unimplemented constraint would report a verdict about the
subset it happened to understand -- which is the shape this repository
files under `a check reads a PROXY for its target`.

Why not the `jsonschema` package: `[project] dependencies = []`, and the
runtime has no third-party dependency. Four keywords carry the
prohibitions; a general engine would be a dependency for that.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Keywords this module evaluates.
IMPLEMENTED = frozenset({
    "type", "properties", "required", "additionalProperties", "const",
    "enum", "pattern", "minimum", "maximum", "items", "oneOf", "$ref", "$defs",
})

#: Keywords that carry no assertion here and are skipped BY DECISION.
#: `format` is annotation-only in JSON Schema unless a validator opts in,
#: and this one does not opt in -- a date-time string is not checked.
ANNOTATION_ONLY = frozenset({"$schema", "$id", "title", "description", "format"})

_TYPES: Dict[str, Any] = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}


class SchemaNotSupported(ValueError):
    """The schema uses a keyword this validator does not implement.

    Raised rather than ignored: a constraint that is not evaluated must
    not be reported as satisfied.
    """


def _keywords(node: Any) -> Sequence[str]:
    found: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(key)
            found.extend(_keywords(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_keywords(item))
    return found


def check_schema_is_supported(schema: Dict[str, Any]) -> None:
    """Every keyword in the schema is implemented or deliberately skipped.

    Property NAMES are not keywords, so only the positions where a
    keyword can appear are inspected: a property called `type` would
    otherwise read as the keyword.
    """
    unsupported = set()

    def walk(node: Any, in_properties: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if in_properties:
            for value in node.values():
                walk(value)
            return
        for key, value in node.items():
            if key not in IMPLEMENTED and key not in ANNOTATION_ONLY:
                unsupported.add(key)
            walk(value, in_properties=key in ("properties", "$defs"))

    walk(schema)
    if unsupported:
        raise SchemaNotSupported(
            f"schema uses keyword(s) this validator does not implement: {sorted(unsupported)}. "
            "Refused rather than ignored -- an unevaluated constraint must not be reported as "
            "satisfied."
        )


def _resolve(ref: str, root: Dict[str, Any]) -> Dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaNotSupported(f"only local refs are implemented, got {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _type_ok(value: Any, declared: Any) -> bool:
    names = declared if isinstance(declared, list) else [declared]
    for name in names:
        expected = _TYPES[name]
        if name in ("number", "integer") and isinstance(value, bool):
            continue                      # bools are ints in python; not numbers here
        if isinstance(value, expected):
            return True
    return False


def _violations(value: Any, schema: Dict[str, Any], root: Dict[str, Any],
                path: str) -> List[str]:
    out: List[str] = []
    if "$ref" in schema:
        return _violations(value, _resolve(schema["$ref"], root), root, path)

    if "const" in schema and value != schema["const"]:
        out.append(f"{path}: expected const {schema['const']!r}, got {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if "type" in schema and not _type_ok(value, schema["type"]):
        out.append(f"{path}: expected type {schema['type']}, got {type(value).__name__}")
        return out
    if "pattern" in schema and isinstance(value, str):
        if not re.search(schema["pattern"], value):
            out.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            out.append(f"{path}: {value} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            out.append(f"{path}: {value} is above maximum {schema['maximum']}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                out.append(f"{path}: missing required key {name!r}")
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    out.append(f"{path}: unexpected key {name!r}")
        for name, sub in properties.items():
            if name in value:
                out.extend(_violations(value[name], sub, root, f"{path}.{name}"))

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            out.extend(_violations(item, schema["items"], root, f"{path}[{index}]"))

    if "oneOf" in schema:
        branches = [_resolve(b["$ref"], root) if "$ref" in b else b
                    for b in schema["oneOf"]]
        matched = [b for b in branches if not _violations(value, b, root, path)]
        if len(matched) != 1:
            out.extend(_why_no_branch(value, branches, matched, root, path))
    return out


def _why_no_branch(value: Any, branches: List[Dict[str, Any]],
                   matched: List[Dict[str, Any]], root: Dict[str, Any],
                   path: str) -> List[str]:
    """`matched 0 of 3 branches` is a verdict with no information in it.

    Where the union is discriminated -- every branch pinning the same
    property to a different `const` -- the branch the value SELECTED is
    known, and its violations are the answer. Reported that way, with the
    branch-count line kept only when nothing discriminates.
    """
    if len(matched) > 1:
        return [f"{path}: matched {len(matched)} branches, expected exactly 1"]

    discriminators = set()
    for branch in branches:
        for name, sub in branch.get("properties", {}).items():
            if "const" in sub:
                discriminators.add(name)
    if isinstance(value, dict):
        for name in sorted(discriminators):
            selected = [b for b in branches
                        if b.get("properties", {}).get(name, {}).get("const") == value.get(name)]
            if len(selected) == 1:
                return _violations(value, selected[0], root, path)
        if discriminators:
            allowed = sorted(
                {b["properties"][n]["const"] for b in branches
                 for n in discriminators if n in b.get("properties", {})})
            present = {n: value.get(n) for n in sorted(discriminators)}
            return [f"{path}: {present} selects no branch; expected one of {allowed}"]
    return [f"{path}: matched no branch of {len(branches)}"]


def validate(payload: Any, schema: Dict[str, Any]) -> Tuple[str, ...]:
    """Every way `payload` violates `schema`. Empty means it conforms, as
    far as the implemented keywords reach -- and the schema was refused
    if it reached further."""
    check_schema_is_supported(schema)
    return tuple(_violations(payload, schema, schema, "$"))


def first_refusal(payload: Any, schema: Dict[str, Any]) -> Optional[str]:
    """The contract says output that would violate the schema is not
    emitted. This is what the emitter asks before emitting."""
    problems = validate(payload, schema)
    return problems[0] if problems else None
