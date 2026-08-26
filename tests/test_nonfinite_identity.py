"""The non-finite identity forensic, and the reader gate it produced.

The question was "does anything already stored have an id that cannot be
recomputed". Measured, such an id recomputes perfectly AND passes the
repository's own integrity check -- so the honest answer is not the one
the question was shaped for, and these tests pin the measurement rather
than the reassuring summary of it.

See architecture/nonfinite_identity_reachability.yaml.
"""

from __future__ import annotations

import json
import math
import pathlib
import re

import pytest

import daf  # noqa: F401  -- installs the vendored import path
from daf.storage import serialization
from daf.storage.serialization import NonJsonConstantError, strict_json_loads
from evidence.identity import content_hash
from evidence.types import make_observation

REPO = pathlib.Path(__file__).resolve().parent.parent
NON_JSON = ("NaN", "Infinity", "-Infinity")


# ----------------------------------------------------- the forensic --

def _stored_json_files():
    """Every JSON file in the repository except the vendored submodule."""
    out = []
    for pattern in ("*.json", "*.jsonl", "*.ndjson"):
        out += [p for p in REPO.rglob(pattern)
                if "vendor" not in p.relative_to(REPO).parts
                and ".git" not in p.relative_to(REPO).parts]
    return sorted(set(out))


def test_the_forensic_domain_is_non_empty_so_the_sweep_can_fail():
    """THE SWEEP'S OWN PRECONDITION, asserted before its result.

    A scan over zero files reports zero violations and means nothing.
    That is the vacuous-guard failure this project has now hit twice, so
    the domain is asserted to be non-empty rather than assumed to be."""
    files = _stored_json_files()
    assert files, "no JSON files found -- the sweep below would pass vacuously"
    assert len(files) >= 20, f"only {len(files)} files found; the sweep was written against 23"


@pytest.mark.parametrize("constant", NON_JSON)
def test_no_stored_json_contains_a_python_json_extension_constant(constant):
    """The forensic result itself: nothing stored is affected.

    Bare NaN/Infinity/-Infinity in value position. Held as a test rather
    than written down as a one-off finding, because 'unreached' is a fact
    about today and this is where it reports when it stops being true."""
    pattern = re.compile(r"(^|[\[\]{},:\s])" + re.escape(constant) + r"([\[\]{},\s]|$)")
    offenders = [p.relative_to(REPO) for p in _stored_json_files()
                 if pattern.search(p.read_text(errors="replace"))]
    assert not offenders, (
        f"{constant} appears in stored JSON: {offenders}. Any id minted over "
        f"those bytes is reproducible only by this implementation."
    )


# ------------------------------------ what the measurement actually was --

def test_a_nonfinite_id_recomputes_perfectly_which_is_the_defect():
    """NOT a test that recomputation fails -- it does not.

    The id is stable, reproducible, and correct by content_hash's own
    rules. It is simply computed over bytes that are not JSON, so no
    independent implementation can reproduce it. A check that only asked
    'does recomputation succeed' would score this as a clean pass, which
    is why the forensic is recorded in the shape the measurement took."""
    content = {"property": "water_level", "unit": "m", "value": float("nan")}
    first = make_observation(("rec-1",), "regex:tide", content, 1.0, "2026-08-26T00:00:00Z")
    again = make_observation(("rec-1",), "regex:tide", dict(content), 1.0, "2026-08-26T00:00:00Z")

    assert first.id == again.id                       # perfectly deterministic
    assert first.content["value"] != first.content["value"]   # over a value unequal to itself

    raw = json.dumps({"value": float("nan")}, sort_keys=True, separators=(",", ":"))
    assert "NaN" in raw, "the bytes identity is computed over are not JSON"
    with pytest.raises(ValueError):
        json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_the_writers_refuse_what_the_readers_used_to_accept():
    """The half-gate, pinned from both sides so neither can regress alone."""
    payload = {"value": float("nan")}
    with pytest.raises(ValueError, match="not JSON compliant"):
        json.dumps(payload, allow_nan=False)          # writer: shut
    with pytest.raises(NonJsonConstantError):
        strict_json_loads('{"value": NaN}')           # reader: now shut too


# ---------------------------------------------------------- the gate --

@pytest.mark.parametrize("constant", NON_JSON)
def test_the_reader_refuses_every_python_json_extension_constant(constant):
    with pytest.raises(NonJsonConstantError, match=re.escape(constant)):
        strict_json_loads('{"value": %s}' % constant)


def test_the_reader_still_accepts_ordinary_json():
    """The refusal is narrow: it costs nothing any real stored file does."""
    for text in ('{"a": 1}', '{"a": 1.5, "b": [1, 2], "c": null}',
                 '{"a": "NaN"}',            # the STRING is fine -- only the bare token is not
                 '{"a": 1e308}', '{"a": -0.0}'):
        assert strict_json_loads(text) == json.loads(text)


def test_a_stored_nan_file_no_longer_passes_the_integrity_check():
    """THE DECISIVE CASE, and the reason this is a defect and not a nit.

    Before the gate: json.loads read it, observation_from_dict recomputed
    the id, and `_verify` PASSED. The repository's own corruption-and-
    tamper check confirmed an identity over bytes no conformant JSON
    implementation can parse. It did not fail to catch the corruption --
    it certified it."""
    content = {"property": "water_level", "unit": "m", "value": float("nan")}
    obs = make_observation(("rec-1",), "regex:tide", content, 1.0, "2026-08-26T00:00:00Z")
    text = json.dumps(
        {"id": obs.id, "record_ids": ["rec-1"], "extraction_method": "regex:tide",
         "content": content, "confidence": 1.0, "extracted_at": "2026-08-26T00:00:00Z"},
        sort_keys=True, indent=2,
    )
    assert "NaN" in text, "the file under test must actually contain the bare token"

    # what it did before: reconstructed, verified, and blessed
    blessed = serialization.observation_from_dict(json.loads(text))
    assert blessed.id == obs.id
    assert math.isnan(blessed.content["value"])

    # what it does now
    with pytest.raises(NonJsonConstantError):
        serialization.observation_from_dict(strict_json_loads(text))


def test_every_writer_that_refuses_has_a_reader_that_refuses():
    """The RULE, not the six instances of it.

    Stated over the pairing rather than over a list of files, so a new
    store added later with a strict writer and a lax reader is caught by
    this test rather than by the next forensic."""
    import ast

    def lax_reads(source):
        """`json.loads(...)` calls with no parse_constant, found in the AST.

        AST rather than a regex, deliberately: a regex over the source also
        matches the word inside `strict_json_loads`'s own docstring and its
        own implementation line, which are the definition of the fix rather
        than instances of the defect. The first version of this test did
        exactly that and reported the fix as one of the failures."""
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in ("loads", "load") \
               and isinstance(f.value, ast.Name) and f.value.id == "json":
                if not any(k.arg == "parse_constant" for k in node.keywords):
                    yield node.lineno

    lax = []
    for path in sorted((REPO / "daf").rglob("*.py")):
        source = path.read_text()
        if "allow_nan=False" not in source:
            continue
        at = sorted(lax_reads(source))
        if at:
            lax.append(f"{path.relative_to(REPO)}:{at}")
    assert not lax, (
        "these modules refuse non-finite floats when WRITING and accept them when "
        f"READING, which is the half-gate this phase closed: {lax}"
    )
