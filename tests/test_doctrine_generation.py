"""Doctrine is a generated projection, and the gate that keeps it one.

The failure this file exists to prevent: prose and enforcement drift
apart, and nobody can tell which is stale. Every check here either
regenerates and compares, or proves a fail-closed path actually fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import epistemics  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics import _yaml
from epistemics.doctrine import (
    DoctrineBudgetExceeded,
    VendorInDoctrine,
    generate,
    output_path,
)
from epistemics.invariants import (
    STATUSES,
    check_declarations,
    core_version,
    load_invariants,
)
from epistemics.model_binding import Binding, BindingViolation, check_bindings, load_bindings

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
CANONICAL_YAML = (
    sorted(ARCHITECTURE.glob("*.yaml"))
    + sorted(ARCHITECTURE.glob("_probes/*.yaml"))
    # The Phase-2 exchange artifacts and the joint decision record are
    # canonical architecture too, and their hashes are only reproducible
    # if both parsers agree on them -- so they belong under the same
    # parse and agreement guarantees as everything else here.
    + sorted(ARCHITECTURE.glob("exchange/*.yaml"))
    + sorted(ARCHITECTURE.glob("decisions/*.yaml"))
)


# --- the canonical sources parse, and mean what PyYAML says they mean ---


def test_every_committed_architecture_file_parses():
    assert CANONICAL_YAML, "no canonical architecture files found"
    for path in CANONICAL_YAML:
        document = _yaml.loads(path.read_text())
        assert isinstance(document, dict), f"{path.name} is not a mapping"


def test_the_minimal_parser_agrees_with_the_reference_implementation():
    """`pyproject.toml` declares `dependencies = []`, so the architecture
    is read by `epistemics/_yaml.py` rather than PyYAML. That is only
    defensible if the two agree on the real files -- measured here when
    PyYAML happens to be importable, skipped when it is not."""
    pyyaml = pytest.importorskip("yaml")
    for path in CANONICAL_YAML:
        text = path.read_text()
        assert _yaml.loads(text) == pyyaml.safe_load(text), f"{path.name} parses differently"


def test_every_architecture_artifact_declares_the_core_it_extends():
    """§24. `core.yaml` is the core itself and declares its version
    instead."""
    expected = core_version()
    for path in CANONICAL_YAML:
        if path.name == "core.yaml":
            continue
        document = _yaml.loads(path.read_text())
        assert document.get("extends") == expected, f"{path.name} does not declare extends: {expected}"


def test_the_core_version_is_the_one_actually_in_the_repository():
    """The synchronization prompts bind against `core@0.1`. That is not
    what is here, and the recorded version is the measured one."""
    core = _yaml.loads((ARCHITECTURE / "core.yaml").read_text())
    vendored = (REPO_ROOT / "vendor" / "scout-retrieval-agent" / "pyproject.toml").read_text()
    assert f'version = "{core["version"]}"' in vendored
    assert core_version() == "core@1.0.0"
    assert core_version() != "core@0.1"


# --- invariant declarations are internally consistent ---


def test_invariant_declarations_are_consistent():
    invariants = load_invariants()
    check_declarations(invariants)
    assert len(invariants) >= 30


def test_no_invariant_invents_a_status_to_avoid_saying_absent():
    for inv in load_invariants():
        assert inv.status in STATUSES


def test_every_named_enforcement_test_file_exists():
    """A status of `enforced` that names a test nobody wrote is worse
    than a status of `absent`."""
    for inv in load_invariants():
        if not inv.enforcement:
            continue
        for named in inv.enforcement.split(","):
            named = named.strip()
            if not named.endswith(".py"):
                continue
            candidate = REPO_ROOT / named
            vendored = REPO_ROOT / "vendor" / "scout-retrieval-agent" / named
            assert candidate.exists() or vendored.exists(), f"{inv.id}: {named} does not exist"


# --- generation ---


def test_regeneration_is_deterministic():
    assert generate().text == generate().text


def test_committed_doctrine_matches_regeneration():
    """The CI conformance gate. A non-zero diff fails closed."""
    committed = output_path()
    assert committed.exists(), "generated doctrine is not committed"
    assert committed.read_text() == generate().text, (
        "committed doctrine differs from regeneration -- run "
        "`python -c 'import epistemics.doctrine as d; d.write()'` and commit the result"
    )


def test_a_manual_edit_to_generated_doctrine_is_detected(tmp_path):
    """`manual_generated_doctrine_changes_fail`. Simulated on a copy so
    the committed file is never touched by a test."""
    copy = tmp_path / "DOCTRINE.md"
    copy.write_text(generate().text + "\n\nA paragraph someone added by hand.\n")
    assert copy.read_text() != generate().text


def test_generated_doctrine_carries_the_digest_of_its_sources():
    doctrine = generate()
    assert f"source-digest: {doctrine.source_digest}" in doctrine.text
    assert "Do not edit" in doctrine.text


def test_the_budget_fails_closed_and_names_the_overflow(tmp_path):
    """Proving the mechanism, not that the current document happens to
    fit. The real budget is not currently binding, which is exactly why
    this has to be shown on a tightened one."""
    for path in CANONICAL_YAML:
        target = tmp_path / path.relative_to(ARCHITECTURE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text())
    config = tmp_path / "doctrine.yaml"
    config.write_text(config.read_text().replace("max_words: 1400", "max_words: 50"))

    with pytest.raises(DoctrineBudgetExceeded) as excinfo:
        generate(tmp_path)
    message = str(excinfo.value)
    assert "largest section" in message
    assert "Do not raise the budget" in message


def test_doctrine_names_no_vendor():
    doctrine = generate()
    config = _yaml.loads((ARCHITECTURE / "doctrine.yaml").read_text())
    lowered = doctrine.text.lower()
    for token in config["forbidden_tokens"]:
        assert token.lower() not in lowered


def test_a_vendor_reaching_doctrine_fails_closed(tmp_path):
    for path in CANONICAL_YAML:
        target = tmp_path / path.relative_to(ARCHITECTURE)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text())
    graph = tmp_path / "control_graph.yaml"
    graph.write_text(
        graph.read_text().replace(
            "reason: \"retrieval output is not an observation\"",
            "reason: \"openai output is not an observation\"",
        )
    )

    with pytest.raises(VendorInDoctrine):
        generate(tmp_path)


def test_doctrine_carries_role_behaviour_and_not_the_binding_table():
    """§5's routing rule, checked on the projection itself."""
    text = generate().text
    assert "discovery and proposal" in text  # role behaviour: present
    assert "vendor-independent from the proposing lineage" in text  # the constraint: present
    # Execution configuration is absent. Checked against the binding
    # table's own field names rather than the word "snapshot", which the
    # invariant id `attested_snapshot_identity` legitimately contains.
    assert "vendor:" not in text.lower()
    assert "snapshot:" not in text.lower()
    assert "| Role | Behaviour | Lineage |" in text


# --- bindings ---


def test_no_binding_is_instantiated_and_the_check_passes_vacuously():
    document, bindings = load_bindings()
    assert document["bindings"] == {}
    assert bindings == ()
    check_bindings(bindings)


def test_cross_vendor_validation_fails_when_the_validator_shares_a_vendor():
    """Authored before a binding exists, so the first one added is
    checked by a rule that did not accommodate it."""
    shared = (
        Binding(role="scout", vendor="v1", snapshot="s-1", hosted=True, lineage="proposing"),
        Binding(role="validator", vendor="v1", snapshot="s-2", hosted=True, lineage="accepting"),
    )
    with pytest.raises(BindingViolation, match="cross_vendor_validation"):
        check_bindings(shared)


def test_a_placeholder_is_not_a_pin():
    placeholder = (
        Binding(role="scout", vendor="v1", snapshot="<pinned-id>", hosted=True, lineage="proposing"),
    )
    with pytest.raises(BindingViolation, match="not a pin"):
        check_bindings(placeholder)


def test_snapshot_verification_is_recorded_as_blocked_not_faked():
    """§8's explicit refusal: a requested-string/echoed-response
    comparison verifies nothing about served weights, so `pin_accepted`
    and `behavioral_canary` are recorded blocked rather than stubbed."""
    document, _ = load_bindings()
    verification = document["snapshot_verification"]
    assert verification["pin_accepted"]["status"] == "not_implementable"
    assert verification["behavioral_canary"]["status"] == "not_implementable"
    assert verification["attested_identity"]["status"] == "unavailable"
    for entry in ("pin_accepted", "behavioral_canary"):
        assert verification[entry]["blocked_by"] == "no_binding_instantiated"

    blocked = {i.id: i for i in load_invariants() if i.status == "blocked"}
    assert {"pin_accepted", "behavioral_canary", "attested_snapshot_identity"} <= set(blocked)
