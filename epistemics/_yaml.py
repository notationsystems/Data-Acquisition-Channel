"""A deliberately small YAML reader for `architecture/*.yaml`.

WHY NOT PyYAML. `pyproject.toml` declares `dependencies = []`, and every
layer built so far has held that line. PyYAML happens to be importable in
the current environment, but committing the canonical architecture behind
an undeclared import would make the architecture unreadable in an
environment that satisfies the project's own declared dependencies.

WHAT IS SUPPORTED, exactly: block mappings, block sequences (of scalars
or of mappings), nested to any depth by two-space indentation; scalars
that are quoted strings, bare strings, integers, `true`/`false`, and
`null`/`~`/empty; `#` comments outside quotes. Nothing else -- no
anchors, no flow style, no multi-line scalars, no multiple documents.
Anything outside that subset raises rather than being guessed at, so a
file this parser accepts means what PyYAML would say it means.

`tests/test_doctrine_generation.py` cross-checks every committed
`architecture/*.yaml` against PyYAML when PyYAML is available, so this
parser's agreement with the reference implementation is measured on the
real files rather than assumed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

INDENT = 2


class YamlSubsetError(ValueError):
    """The document used a construct outside the supported subset, or is
    malformed. Never raised for a file this project commits."""


def _strip_comment(line: str) -> str:
    out: List[str] = []
    quote: Optional[str] = None
    for i, ch in enumerate(line):
        if quote is None and ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        if quote is None and ch in "\"'":
            quote = ch
        elif quote is not None and ch == quote:
            quote = None
        out.append(ch)
    return "".join(out).rstrip()


#: The complete escape set `architecture/exchange/canonical_yaml.py` can
#: emit. Its `_quote` escapes exactly these five, in this order, and the
#: always-quote rule means EVERY string passes through it -- so any value
#: containing a quote, a backslash or whitespace-as-a-control-character
#: arrives here escaped.
_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t"}


def _unescape(body: str) -> str:
    """Decode a double-quoted scalar's body.

    WHY THIS EXISTS. Measured: this reader used to return `text[1:-1]`,
    stripping the quotes and leaving every escape as literal characters.
    So `"he said \\"hi\\""` came back as the 14-character string with
    backslashes still in it, while PyYAML returned the 12-character string
    the emitter meant. Same bytes, two values -- which is precisely the
    condition the pinned encoding exists to rule out, and it reached a
    hash-bearing artifact before anything caught it.

    This is NOT the ambiguity class the always-quote rule closed, and the
    repair is deliberately the opposite one. There the BYTES were
    ambiguous, so the fix had to be emitter-side; a reader-side
    normalization would have hidden it. Here the bytes have exactly one
    correct meaning under YAML 1.2 and PyYAML already returns it -- this
    reader was simply non-conformant. Fixing a wrong reader is not
    relocating a problem, and it moves no artifact and no digest.

    An unrecognized escape RAISES rather than being guessed at. The
    canonical emitter cannot produce one, so encountering it means the
    document did not come from that emitter, and silently passing it
    through is how a subset parser stops being a subset parser."""
    out: List[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            raise YamlSubsetError(f"trailing backslash in quoted scalar: {body!r}")
        code = body[index + 1]
        if code not in _ESCAPES:
            sequence = "\\" + code
            raise YamlSubsetError(
                f"unsupported escape {sequence!r} in quoted scalar: {body!r}. The canonical "
                "emitter produces only backslash, double-quote, n, r and t."
            )
        out.append(_ESCAPES[code])
        index += 2
    return "".join(out)


def _scalar(text: str) -> Any:
    text = text.strip()
    if text == "" or text in ("null", "~"):
        return None
    # The only flow-style constructs supported, and only when empty:
    # `{}` and `[]` are the honest way to say "declared, and currently
    # nothing", which `null` does not distinguish from "not declared".
    if text == "{}":
        return {}
    if text == "[]":
        return []
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        if text[0] == "'":
            return text[1:-1]
        return _unescape(text[1:-1])
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _lines(text: str) -> List[Tuple[int, str]]:
    result: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_comment(raw)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        if indent % INDENT:
            raise YamlSubsetError(f"indent {indent} is not a multiple of {INDENT}: {raw!r}")
        result.append((indent, stripped.strip()))
    return result


def _split_key(item: str) -> Tuple[str, str]:
    quote: Optional[str] = None
    for i, ch in enumerate(item):
        if quote is None and ch in "\"'":
            quote = ch
        elif quote is not None and ch == quote:
            quote = None
        elif quote is None and ch == ":" and (i + 1 == len(item) or item[i + 1] == " "):
            key = item[:i].strip()
            if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
                key = key[1:-1] if key[0] == "'" else _unescape(key[1:-1])
            return key, item[i + 1 :].strip()
    raise YamlSubsetError(f"expected 'key: value', got {item!r}")


def _parse_block(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Any, int]:
    if start >= len(lines):
        return None, start
    if lines[start][1].startswith("- "):
        return _parse_sequence(lines, start, indent)
    return _parse_mapping(lines, start, indent)


def _parse_sequence(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[List[Any], int]:
    items: List[Any] = []
    i = start
    while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
        body = lines[i][1][2:].strip()
        try:
            key, value = _split_key(body)
        except YamlSubsetError:
            items.append(_scalar(body))
            i += 1
            continue
        # An item that opens a mapping. Its remaining keys sit at
        # indent + 2, which is exactly where "- " left off.
        entry: Dict[str, Any] = {}
        inner = indent + INDENT
        if value:
            entry[key] = _scalar(value)
            i += 1
        else:
            i += 1
            if i < len(lines) and lines[i][0] > inner:
                entry[key], i = _parse_block(lines, i, lines[i][0])
            else:
                entry[key] = None
        while i < len(lines) and lines[i][0] == inner and not lines[i][1].startswith("- "):
            k, v = _split_key(lines[i][1])
            if v:
                entry[k] = _scalar(v)
                i += 1
            else:
                i += 1
                if i < len(lines) and lines[i][0] > inner:
                    entry[k], i = _parse_block(lines, i, lines[i][0])
                else:
                    entry[k] = None
        items.append(entry)
    return items, i


def _parse_mapping(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Dict[str, Any], int]:
    mapping: Dict[str, Any] = {}
    i = start
    while i < len(lines) and lines[i][0] == indent:
        if lines[i][1].startswith("- "):
            raise YamlSubsetError(f"sequence item where a mapping key was expected: {lines[i][1]!r}")
        key, value = _split_key(lines[i][1])
        if key in mapping:
            raise YamlSubsetError(f"duplicate key {key!r}")
        if value:
            mapping[key] = _scalar(value)
            i += 1
            continue
        i += 1
        if i < len(lines) and lines[i][0] > indent:
            mapping[key], i = _parse_block(lines, i, lines[i][0])
        elif i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
            mapping[key], i = _parse_sequence(lines, i, indent)
        else:
            mapping[key] = None
    return mapping, i


def loads(text: str) -> Any:
    lines = _lines(text)
    if not lines:
        return None
    if lines[0][0] != 0:
        raise YamlSubsetError("document does not start at column 0")
    value, consumed = _parse_block(lines, 0, 0)
    if consumed != len(lines):
        raise YamlSubsetError(f"unconsumed content at line {consumed}: {lines[consumed][1]!r}")
    return value
