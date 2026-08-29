#!/usr/bin/env python3
"""Generate the agent contracts from architecture/instruments.yaml.

An agent contract is what an executing model reads. It must therefore be
DERIVED from the instrument record rather than written beside it: a
contract and a record that drift apart give an agent authority the
instrument never granted, and nothing downstream can tell.

Same discipline as epistemics/doctrine.py -- a banner naming the source,
a digest over the inputs, and a test that regenerates and compares. The
digest is over BOTH inputs, the instrument record and the schema it
appends, because a schema edit changes the contract an agent reads.

    python3 generate.py            write the contracts
    python3 generate.py --check    exit 1 if any is stale
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor" / "scout-retrieval-agent"))

from epistemics._yaml import loads  # noqa: E402

INSTRUMENTS = ROOT / "architecture" / "instruments.yaml"
OUT_DIR = ROOT / "docs" / "generated"

#: Sixteen hex characters, the shape the arriving contract used. It is a
#: truncation and is named as one: it identifies a source revision, it is
#: not a collision-resistant commitment.
DIGEST_CHARS = 16


def source_digest(paths: List[pathlib.Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:DIGEST_CHARS]


def _bullets(items: Any) -> str:
    return "\n".join(f"* {item}" for item in items)


def render(instrument_id: str, instrument: Dict[str, Any], agent_id: str,
           agent: Dict[str, Any], record: Dict[str, Any], digest: str) -> str:
    schema_path = ROOT / agent["output_schema"]
    schema_text = schema_path.read_text().rstrip("\n")
    enforced = instrument["enforced"]
    pacing = "\n".join(
        f"* {name}: {body['claim']} Enforced by {body['implemented_by']}"
        for name, body in enforced.items())
    not_enforced = "\n".join(
        f"* {name}: {body['what_is_actually_there']}"
        for name, body in instrument.get("not_enforced", {}).items())

    failure = agent["failure_behaviour"]
    parts = [
        f"<!-- GENERATED FILE -- DO NOT EDIT. Source: architecture/instruments.yaml"
        f" Regenerate: python3 generate.py Source digest: {digest} -->",
        "",
        f"AGENT -- {agent_id}",
        "",
        "You are a computational component inside a larger system. You perform one",
        "function, through one interface, and you are not authorised to do anything",
        "outside it. You do not need to understand how the system is built or how it is",
        "developed. You need to understand your contract.",
        "",
        "This contract specifies a function, not a model. Whatever executes you reads",
        "exactly this.",
        "",
        "System context",
        "",
        f"Program. {record['program']} Instrument you operate within."
        f" {instrument['title']} (`{instrument_id}`, layer {instrument['layer']}).",
        "",
        f"What the instrument is for. {instrument['purpose']}",
        "",
        "Rules of the system that bind you.",
        "",
        _bullets(record["system_rules"]),
        "",
        "Pacing controls this instrument actually has.",
        "",
        pacing,
        "",
        "Controls it does NOT have, stated so no caller relies on them.",
        "",
        not_enforced,
        "",
        "Your role",
        "",
        agent["role"],
        "",
        "Inputs",
        "",
        _bullets(agent["inputs"]),
        "",
        "Output contract",
        "",
        "Form. A JSON array of CandidateFiling objects. Nothing else. No prose, no",
        "preamble, no explanation outside the schema.",
        "",
        f"Schema. `{agent['output_schema']}` -- appended below in full. Output that would",
        "violate it is not emitted, and",
        f"`{instrument['agents'][agent_id]['mechanical_enforcement']['validator']}`"
        " is what refuses it.",
        "",
        "Estimation rules",
        "",
        "You produce estimates. An estimate is never promoted to a fact by passing",
        "through a function boundary -- yours included.",
        "",
        _bullets(agent["estimation_rules"]),
        "",
        "Authority boundary",
        "",
        "You may.",
        "",
        _bullets(agent["may"]),
        "",
        "You may not.",
        "",
        _bullets(agent["may_not"]),
        "",
        "Provenance",
        "",
        _bullets(agent["provenance_rules"]),
        "",
        "Failure behaviour",
        "",
        failure["preamble"],
        "",
        _bullets(failure["rules"]),
        "",
        "Prohibited in all cases",
        "",
        _bullets(agent["prohibited"]),
        "",
        "Output schema (authoritative)",
        "",
        "```json",
        schema_text,
        "```",
        "",
    ]
    return "\n".join(parts)


def contracts() -> Dict[pathlib.Path, str]:
    record = loads(INSTRUMENTS.read_text())
    written: Dict[pathlib.Path, str] = {}
    for instrument_id, instrument in sorted(record["instruments"].items()):
        for agent_id, agent in sorted(instrument["agents"].items()):
            digest = source_digest([INSTRUMENTS, ROOT / agent["output_schema"]])
            path = OUT_DIR / f"AGENT_{agent_id}.md"
            written[path] = render(instrument_id, instrument, agent_id, agent, record, digest)
    return written


def main(argv: List[str]) -> int:
    check_only = "--check" in argv
    stale = []
    for path, text in contracts().items():
        current = path.read_text() if path.exists() else None
        if current == text:
            continue
        stale.append(path.relative_to(ROOT).as_posix())
        if not check_only:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if check_only and stale:
        print("STALE: " + ", ".join(stale))
        return 1
    if not check_only:
        for path in contracts():
            print(f"wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
