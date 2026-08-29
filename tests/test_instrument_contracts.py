"""The agent contract is generated, and every claim in it is checked
against the code that would have to enforce it.

A contract is what an executing model reads. Two failure modes matter:
the contract drifting from its source, and the source asserting a control
the instrument does not have. The first is a regeneration diff. The
second is the one that costs something, because a caller relies on it.
"""

from __future__ import annotations

import ast
import json
import re
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.agents.candidate_filing import (SchemaNotSupported,  # noqa: E402
                                         check_schema_is_supported, first_refusal, validate)
from epistemics._yaml import loads  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "instruments.yaml").read_text())
INSTRUMENT = RECORD["instruments"]["edgar_acquisition"]
AGENT = INSTRUMENT["agents"]["EDGAR_SCOUT"]
SCHEMA = json.loads((REPO_ROOT / "architecture" / "schemas"
                     / "candidate_filing.schema.json").read_text())
CONTRACT = REPO_ROOT / "docs" / "generated" / "AGENT_EDGAR_SCOUT.md"


# =====================================================================
# The contract is a projection of its source
# =====================================================================

def test_the_contract_regenerates_identically():
    result = subprocess.run([sys.executable, "generate.py", "--check"],
                            cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert result.returncode == 0, (
        f"the committed contract differs from regeneration: {result.stdout.strip()} -- run "
        "`python3 generate.py` and commit the result"
    )


def test_the_banner_names_a_source_and_a_regenerate_command_that_both_exist():
    """The arriving contract named three paths and none of them was here.
    A banner is a claim about the tree like any other."""
    banner = CONTRACT.read_text().splitlines()[0]
    assert "GENERATED FILE" in banner and "DO NOT EDIT" in banner
    assert (REPO_ROOT / "architecture" / "instruments.yaml").exists()
    assert (REPO_ROOT / "generate.py").exists()
    assert (REPO_ROOT / AGENT["output_schema"]).exists()

    digest = banner.split("Source digest:")[1].split("-->")[0].strip()
    assert len(digest) == 16 and all(c in "0123456789abcdef" for c in digest)
    assert digest != "66629e18fca40af9", (
        "this repository does not hold the source the arriving contract was generated from, so "
        "reproducing its digest would mean fabricating one"
    )


def test_the_digest_moves_when_either_input_moves():
    """A digest over one of two inputs would go stale silently when the
    other changed, and the schema is appended into the contract."""
    import generate

    baseline = generate.source_digest([generate.INSTRUMENTS,
                                       REPO_ROOT / AGENT["output_schema"]])
    assert baseline == CONTRACT.read_text().split("Source digest:")[1].split("-->")[0].strip()
    only_one = generate.source_digest([generate.INSTRUMENTS])
    assert only_one != baseline, "the schema must contribute to the digest"


# =====================================================================
# Every claim in the record is true of the code
# =====================================================================

def _defined_names(path: pathlib.Path) -> set:
    """Every name the module DEFINES -- assignments, functions, classes,
    dataclass fields, and the string literals it assigns. Derived, so a
    reference is checked against what the module actually declares rather
    than against a list of words someone kept up to date."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def test_every_enforced_claim_names_a_file_and_a_symbol_that_exist():
    """`implemented_by` is the difference between a control and a wish.

    Each entry must name a module that exists AND at least one name that
    module actually defines. A claim citing a file that does not mention
    its own mechanism is a citation to nothing."""
    for name, body in INSTRUMENT["enforced"].items():
        reference = body["implemented_by"]
        modules = [part.rstrip(".,;") for part in reference.split()
                   if part.rstrip(".,;").endswith(".py")]
        assert modules, f"{name} names no module"
        matched = []
        for module in modules:
            path = REPO_ROOT / module
            assert path.exists(), f"{name} names {module}, which does not exist"
            defined = _defined_names(path)
            tokens = {token.rstrip(".,;:")
                      for token in re.findall(r"[A-Za-z_][A-Za-z0-9_:.]{3,}", reference)}
            matched.extend(sorted(tokens & defined))
        assert matched, (
            f"{name}: the reference {reference!r} names nothing that "
            f"{modules} defines -- a claim citing a file that does not mention its own "
            "mechanism is a citation to nothing"
        )


def test_the_adapter_really_has_no_inter_request_delay():
    """THE `not_enforced` ENTRY, MEASURED RATHER THAN ASSERTED.

    The arriving contract said the instrument runs under a hard
    request-rate ceiling. Derived from the source: the only sleep is
    inside the retry helper, and the fetch loop that issues the requests
    contains none. If someone adds a rate limiter, this fails and the
    record must be moved from `not_enforced` to `enforced`."""
    module = ast.parse((REPO_ROOT / "daf" / "adapters"
                        / "edgar_daily_index.py").read_text())
    sleeping = set()
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call):
                target = inner.func
                name = getattr(target, "attr", None) or getattr(target, "id", None)
                if name == "sleep":
                    sleeping.add(node.name)
    assert sleeping == {"_fetch_with_retries"}, (
        f"sleep is called in {sorted(sleeping)}. If the fetch loop now paces itself, the "
        "`a_hard_request_rate_ceiling` entry has become true and belongs under `enforced`."
    )
    assert "a_hard_request_rate_ceiling" in INSTRUMENT["not_enforced"]
    stated = INSTRUMENT["not_enforced"]["a_hard_request_rate_ceiling"]["what_is_actually_there"]
    assert "no inter-request delay on the normal path" in stated, (
        "the entry must say what IS there, not merely that the control is absent"
    )
    assert "_RETRY_DELAY_SECONDS" in stated


def test_the_contract_does_not_repeat_the_control_that_does_not_exist():
    """The generated text is where the overstatement would land."""
    text = CONTRACT.read_text()
    assert "hard request-rate ceiling" not in text.split("Controls it does NOT have")[0], (
        "the contract asserts a rate ceiling above the section that denies it"
    )
    assert "Controls it does NOT have" in text
    assert "the pacing controls named below" in text


# =====================================================================
# The validator refuses what the prohibitions forbid
# =====================================================================

def _candidate(**over):
    base = {"kind": "candidate", "form_type": "10-K", "relevance": 0.7,
            "basis": "annual reports are where segment disclosures appear",
            "source": "index", "provenance": {"ref": "idx:company.20240102.idx"}}
    base.update(over)
    return base


def test_a_conforming_proposal_passes():
    """Asserted before the refusals. A validator that rejects everything
    refuses the forbidden shapes for the wrong reason."""
    assert validate([_candidate()], SCHEMA) == ()
    assert validate([_candidate(accession_number="0000320193-23-000106",
                                cik="320193", confidence=0.4)], SCHEMA) == ()
    assert validate([], SCHEMA) == ()


@pytest.mark.parametrize("payload,fragment", [
    (_candidate(accession_number="0001234567-24-00012"), "does not match"),
    (_candidate(accession_number="ACCN-2024-000123"), "does not match"),
    (_candidate(cik="not-a-cik"), "does not match"),
    (_candidate(relevance=1.4), "above maximum"),
    (_candidate(relevance=-0.1), "below minimum"),
    (_candidate(confidence=2), "above maximum"),
    (_candidate(source="guess"), "is not one of"),
    (_candidate(note="I think this one is likely"), "unexpected key"),
    (_candidate(provenance={"ref": "x", "hunch": "strong"}), "unexpected key"),
], ids=["short-accession", "invented-accession", "bad-cik", "relevance-high",
        "relevance-low", "confidence-high", "bad-source", "commentary-key",
        "commentary-in-provenance"])
def test_the_forbidden_shapes_are_refused(payload, fragment):
    """DETECTOR PROOFS, one per prohibition that the schema can carry.
    A plausible-looking accession number is the one the contract names
    explicitly, and it is refused by pattern rather than by judgement."""
    problems = validate([payload], SCHEMA)
    assert problems, f"{payload} was accepted"
    assert any(fragment in problem for problem in problems), problems


def test_an_unknown_identifier_may_be_null_but_may_not_be_omitted_from_required():
    assert validate([_candidate(accession_number=None, cik=None, filer_name=None)],
                    SCHEMA) == ()
    missing = dict(_candidate())
    del missing["provenance"]
    assert any("provenance" in p for p in validate([missing], SCHEMA))


def test_narration_outside_the_schema_cannot_be_carried_inside_it():
    """`Uncertainty is expressed inside the schema, never by narrating
    outside it` -- and additionalProperties false is what stops the
    narration being smuggled back in as a field."""
    assert any("unexpected key" in p
               for p in validate([_candidate(reasoning="step 1...")], SCHEMA))


def test_the_error_object_this_session_actually_emitted_validates():
    """The response returned when both inputs were absent, checked rather
    than assumed well-formed."""
    emitted = [{
        "kind": "error",
        "reason": "Both required inputs are absent. No research question was supplied "
                  "(with its domain and time window), and no acquisition ledger was supplied.",
        "offending_input": None,
    }]
    assert validate(emitted, SCHEMA) == ()
    assert first_refusal(emitted, SCHEMA) is None


def test_a_query_gap_needs_a_question_and_an_error_does_not():
    """Why the absent-input case is an error and not a query_gap: a
    query_gap asserts a question exists that could not be mapped."""
    assert validate([{"kind": "query_gap", "reason": "no filer named",
                      "missing": ["a company name or CIK"]}], SCHEMA) == ()
    assert any("missing required key" in p
               for p in validate([{"kind": "query_gap", "reason": "no filer named"}], SCHEMA))


def test_the_oneOf_discriminates_rather_than_accepting_anything():
    """An item matching no branch, and an item matching none because it
    mixes two."""
    unknown = validate([{"kind": "proposal"}], SCHEMA)
    assert any("selects no branch" in p for p in unknown), unknown
    assert any("'candidate', 'error', 'query_gap'" in p for p in unknown), (
        "the message must name the branches, not the count -- `matched 0 of 3` is a verdict "
        "with no information in it"
    )

    mixed = {"kind": "error", "reason": "x", "missing": []}
    reported = validate([mixed], SCHEMA)
    assert any("unexpected key 'missing'" in p for p in reported), (
        f"the discriminator selected the error branch, so the reason must come from it: {reported}"
    )


# =====================================================================
# The validator's own scope is mechanical
# =====================================================================

def test_the_validator_refuses_a_schema_keyword_it_does_not_implement():
    """THE POINT OF THE MODULE. A validator that ignored an unimplemented
    constraint would report a verdict about the subset it understood."""
    check_schema_is_supported(SCHEMA)                       # the real one is in scope

    widened = json.loads(json.dumps(SCHEMA))
    widened["$defs"]["candidate"]["properties"]["relevance"]["multipleOf"] = 0.05
    with pytest.raises(SchemaNotSupported, match="multipleOf"):
        check_schema_is_supported(widened)
    with pytest.raises(SchemaNotSupported, match="multipleOf"):
        validate([_candidate()], widened)


def test_a_property_named_like_a_keyword_is_not_read_as_one():
    """The discriminating case for the scope check: `properties` contains
    NAMES, and a field called `type` would otherwise refuse the schema."""
    schema = {"type": "object", "additionalProperties": False,
              "properties": {"type": {"type": "string"}, "enum": {"type": "string"}}}
    check_schema_is_supported(schema)
    assert validate({"type": "10-K", "enum": "x"}, schema) == ()
    assert any("expected type" in p for p in validate({"type": 7}, schema))


def test_the_record_states_what_the_validator_does_not_check():
    enforcement = AGENT["mechanical_enforcement"]
    assert enforcement["validator"] == "daf/agents/candidate_filing.py"
    assert "NOT a general JSON Schema engine" in enforcement["what_it_does_not_check"]
    assert "REFUSAL rather than a silent pass" in enforcement["what_it_does_not_check"]
    assert "dependencies = []" in enforcement["why_it_is_not_jsonschema"]


def test_the_record_says_it_is_a_reconstruction():
    """The source the arriving contract named did not exist here. A record
    that quietly presented itself as the original would be the fabrication
    its own rules forbid."""
    header = " ".join(line.lstrip("#").strip() for line in
                      (REPO_ROOT / "architecture" / "instruments.yaml")
                      .read_text().split("extends:")[0].splitlines())
    assert "none of the three existed here" in header
    assert "cannot be reproduced" in header
    assert "this is a reconstruction and says so" in header
