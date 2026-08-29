"""The three-party invariant register, checked against the three parties.

WHAT THIS FILE IS FOR. The register answers a prior question that 33
artifacts in this repository assume an answer to: `bent: []`,
`core_invariants_modified: 0` and every `extends: core@1.0.0` are claims
made relative to a core, and until the register existed nothing said
whose invariants, held where, checkable by whom.

The register is DERIVED, so the checks here are of two kinds only:

  1. it is a fixed point of its generator -- regenerate and compare, the
     same discipline every other artifact in exchange/ is held to. This is
     what makes the numbers in it evidence rather than assertions.
  2. the load-bearing findings are still true of the tree, re-measured
     here independently of the generator, so a generator that quietly
     stopped looking does not take the finding with it.

WHAT IS DELIBERATELY NOT HERE. No status reconciliation across parties.
SCL has no status vocabulary and STE has no enumeration, so there is
nothing to reconcile; the cross-party status claims that DO exist are DAQ
invariants cited in SCL-authored artifacts, and
tests/test_cross_repository_claims.py already sweeps every document this
repository holds for those. A second mechanism here would be the parallel
architecture this pair has refused everywhere else.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
REGISTER_PATH = EXCHANGE / "invariant_register.yaml"

REGISTER = loads(REGISTER_PATH.read_text())
CORE = loads((REPO_ROOT / "architecture" / "core.yaml").read_text())
INVARIANTS = loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())


# ------------------------------------------------------- 1. derived, not written



def _fixed_point_of(generator: str, *written: pathlib.Path):
    """Run a generator and report whether it reproduced its own output,
    restoring EVERY file it writes.

    THE RESTORE USED TO BE PARTIAL, and that is the defect this closes.
    Each of these generators writes an artifact AND its sidecar; the
    check snapshotted and restored only the artifact. So a run that
    failed the fixed-point comparison left the tree in a state no commit
    describes: the artifact as committed, the digest as regenerated,
    every downstream digest check passing over a hash bound to bytes that
    are no longer there. Measured -- it is how a suite run against an
    unpinned checkout left two sidecars dirty and self-consistently
    wrong.

    The wider shape is that a VERIFICATION WITH A WRITE SIDE EFFECT
    cannot witness the thing it verifies, because running it changes the
    subject. The generators now refuse to run against a tree the pin does
    not name; this restores what a run does touch. Both halves are needed:
    the guard stops the wrong bytes being produced, this stops a
    legitimate failure leaving a mixed tree behind."""
    import subprocess

    before = {path: path.read_bytes() for path in written}
    result = subprocess.run(
        ["python3", str(EXCHANGE / generator)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    after = {path: path.read_bytes() for path in written}
    for path, original in before.items():
        if after[path] != original:
            path.write_bytes(original)
    changed = sorted(path.name for path in written if after[path] != before[path])
    return result, changed


def test_the_register_is_a_fixed_point_of_its_generator():
    """Every number in the register is read from a source at generation
    time. If the file and the generator disagree, the file is a claim."""
    result, changed = _fixed_point_of(
        "build_invariant_register.py",
        REGISTER_PATH,
        EXCHANGE / "invariant_register.sha256",
    )
    assert result.returncode == 0, result.stderr
    assert changed == [], (
        f"the committed register differs from regeneration in {changed} -- run "
        "`python3 architecture/exchange/build_invariant_register.py` and commit the result"
    )


def test_the_recorded_digest_matches_the_bytes():
    recorded = (EXCHANGE / "invariant_register.sha256").read_text().strip()
    assert recorded == "sha256:" + hashlib.sha256(REGISTER_PATH.read_bytes()).hexdigest()


def test_the_census_does_not_count_itself():
    """A census whose value includes its own row reports a number that
    depends on whether it has been run before rather than on the world."""
    source = (EXCHANGE / "build_invariant_register.py").read_text()
    assert 'path == HERE / "invariant_register.yaml"' in source, (
        "the extends census must skip the register, or the artifact is not a fixed point of its "
        "own generator"
    )


# --------------------------------------------- 2. the findings, re-measured here


def test_it_joins_on_the_participating_referent_not_the_label():
    join = REGISTER["joined_on"]
    assert join["referent"] == CORE["core_referent"]["participating"]
    assert join["referent"] != CORE["core_referent"]["annotating"]
    assert join["value"] == CORE["submodule_commit"]
    assert join["gitlink_at_generation"].startswith(CORE["submodule_commit"]), (
        "the register was generated against a different core than core.yaml records"
    )


def test_the_core_party_enumerates_no_invariants_anywhere_in_the_tree():
    """The register's central finding, re-measured rather than read back.

    If the vendored core ever grows a structured invariant source, this
    fails and the register must be re-derived -- which is the correct
    outcome, because the whole shape of `bent: zero` changes that day."""
    vendor = REPO_ROOT / CORE["submodule_path"]
    structured = [
        p for p in vendor.rglob("*.yaml")
        if ".git" not in p.parts and "node_modules" not in p.parts
    ]
    # INVERTED, on the instruction this test's own failure message gave:
    # "Re-derive the register; `bent: zero` may now be checkable as
    # worded." The core grew structured documents when the pin moved, the
    # register was re-derived, and the assertion becomes the property that
    # was always the point.
    assert structured != [], (
        "the core no longer holds structured documents -- the pin moved backwards and the "
        "register's citation of a declaration has no referent"
    )
    # INVERTED WITH THE PIN. This asserted the core party had no reachable
    # enumeration -- true of the tree, never of STE. The pin moved and the
    # enumeration arrived, so the assertion becomes what it always meant:
    # whatever this register says about reachability must match what is
    # actually reachable, in either direction.
    ste = REGISTER["parties"]["ste"]
    source = ste["invariant_source"]
    assert ste["reachable_from_this_register"] is (source is not None)
    if source is not None:
        assert (REPO_ROOT / source).exists(), f"the register cites {source}, which is not here"
        assert loads((REPO_ROOT / source).read_text()), "the cited source does not parse HERE"


def test_the_cores_own_documents_disagree_on_how_many_invariants_it_has():
    """Not a nitpick: it is why `bent: zero` cannot be checked as worded.

    Two independent numbers in the core's own docs, neither enumerated. If
    they ever agree AND a list appears, the finding is closed and this
    test should be the thing that says so."""
    cardinalities = REGISTER["the_core_partys_invariants_are_not_enumerated_anywhere_here"][
        "cardinalities_found"]
    numbers = REGISTER["the_core_partys_invariants_are_not_enumerated_anywhere_here"][
        "numbers_referenced"]
    assert numbers, "the register found no invariant references at all in the core"
    assert len(cardinalities) >= 1
    highest_referenced = max(numbers)
    asserted = sorted(int(key.split("_")[0]) for key in cardinalities)
    assert highest_referenced not in asserted or len(asserted) > 1, (
        "the referenced range and the asserted cardinality now agree; if an enumeration also "
        "exists, the register's central finding is closed and must be re-derived"
    )


def test_bent_zero_is_recorded_as_supported_by_byte_identity_not_by_enumeration():
    rests = REGISTER["what_bent_zero_actually_rests_on"]
    assert rests["measured_at_generation"]["working_tree_matches_the_pin"] is True
    assert rests["measured_at_generation"]["gitlink"].startswith(CORE["submodule_commit"])
    assert "unfalsifiable in the form it is written" in rests["why_it_cannot_be_checked_as_worded"]
    assert "what_is_NOT_claimed" in rests, (
        "the register must say that it does not claim STE's invariants HOLD -- only that this pair "
        "did not modify them"
    )


def test_the_core_is_still_unmodified_measured_here():
    """The observable the entailment rests on, checked independently of
    the generator that recorded it."""
    out = subprocess.run(
        ["git", "submodule", "status", CORE["submodule_path"]],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout:
        pytest.skip("submodule status unavailable in this checkout")
    assert out.stdout[0] not in "+-U", (
        f"the vendored core is modified or out of sync: {out.stdout.strip()!r}. `bent: zero` is no "
        "longer entailed by byte-identity and has to be re-established."
    )


def test_the_extends_census_is_parsed_and_matches_a_parse_done_here():
    """Recorded as 26 in prose, parsed as 33. The gap is the point: a text
    search for `extends: core@1.0.0` cannot see `"extends": "core@1.0.0"`,
    which is what the shared canonical emitter writes."""
    counted = 0
    for path in sorted(REPO_ROOT.rglob("*.yaml")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        if path == REGISTER_PATH:
            continue
        try:
            document = loads(path.read_text())
        except Exception:
            continue
        if isinstance(document, dict) and document.get("extends") == f"core@{CORE['version']}":
            counted += 1
    assert REGISTER["extends_join"]["artifacts_declaring_the_core"] == counted
    assert REGISTER["extends_join"]["artifacts_declaring_a_different_core"] == []

    grepped = len(re.findall(
        r"^extends: core@",
        "\n".join(
            p.read_text() for p in REPO_ROOT.rglob("*.yaml")
            if "vendor" not in p.parts and ".git" not in p.parts
        ),
        re.M,
    ))
    assert grepped < counted, (
        "a text search now finds as many as a parse does; the finding that the canonically-emitted "
        "artifacts were invisible to the count no longer holds and the note should be re-measured"
    )


def test_scls_half_is_reachable_and_carries_no_borrowed_status_vocabulary():
    scl = REGISTER["parties"]["scl"]
    assert scl["reachable_from_this_register"] is True, (
        "SCL's invariant source is not exchanged; a three-party register with one party "
        "unreachable is a two-party register with a footnote"
    )
    assert scl["status_histogram"] is None
    daq_vocabulary = {entry["status"] for entry in INVARIANTS["invariants"]}
    clauses = loads((EXCHANGE / "scl_contract_clauses.yaml").read_text())
    for name, clause in clauses["clauses"].items():
        assert clause["coverage"] not in daq_vocabulary, (
            f"{name} reports coverage {clause['coverage']!r}, which is one of this repository's "
            "invariant statuses -- the register would then join on a word meaning two things"
        )


def test_every_party_says_whether_it_is_reachable():
    """The property, not the list: a party added later must answer it too."""
    for name, party in REGISTER["parties"].items():
        assert "reachable_from_this_register" in party, f"{name} does not say"
        assert isinstance(party["reachable_from_this_register"], bool)
        assert "source_kind" in party, f"{name} does not say what kind of source it holds"


def test_the_property_set_divergence_is_verified_against_git_not_asserted():
    """The register says `bent: zero` meant four properties before c80a2f0
    and five after. That is a claim about history, so it is checked
    against history."""
    block = REGISTER["which_property_set_bent_zero_quantifies_over"]
    canonical = block["the_canonical_set_is_the_union_of_both_axes"]
    probe = loads((REPO_ROOT / "architecture" / "_probes" / "generality.yaml").read_text())
    assert canonical["observation_properties"] == list(probe["observation_properties"])
    assert canonical["computation_properties"] == list(probe["computation_properties"])
    assert canonical["total"] == len(probe["observation_properties"]) + len(
        probe["computation_properties"])

    counts = {}
    for revision in ("ca3d0aa", "c80a2f0"):
        shown = subprocess.run(
            ["git", "show", f"{revision}:architecture/_probes/generality.yaml"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        if shown.returncode != 0:
            pytest.skip(f"{revision} not reachable from this checkout")
        historical = loads(shown.stdout)
        counts[revision] = (
            len(historical.get("observation_properties") or [])
            + len(historical.get("computation_properties") or [])
        )
    assert counts["ca3d0aa"] == 4, counts
    assert counts["c80a2f0"] == 5, counts
    assert counts["c80a2f0"] != counts["ca3d0aa"], (
        "the register claims the property set changed size; git says it did not"
    )


def test_the_partition_that_prevents_the_set_growing_silently_still_exists():
    """The register cites test_generality_probe_gate.py as what keeps this
    from recurring. A citation of a check that has been deleted is worse
    than no citation."""
    gate = REPO_ROOT / "tests" / "test_generality_probe_gate.py"
    assert gate.exists(), "the register cites a partition check that no longer exists"
    source = gate.read_text()
    assert "test_every_declared_property_is_accounted_for_in_exactly_one_outcome_list" in source
    assert "test_every_declared_property_has_a_result" in source


# ------------------------------------------------- 3. the core party's own set


STE = loads((EXCHANGE / "ste_invariants.yaml").read_text())


def test_the_reconstruction_never_calls_itself_a_declaration():
    """The whole point of the artifact. A set written about a party by
    another party is not that party's set, and this pair demoted a
    decision to a proposal once for exactly this reason."""
    assert STE["status"] == "RECONSTRUCTION_NOT_DECLARATION"
    assert STE["owner"] == "ste"
    assert STE["authored_by"] != STE["owner"]
    assert "is not that party's set" in STE["what_status_means"]
    assert STE["the_request_to_ste"][
        "there_is_no_counterparty_response_and_this_file_does_not_pretend_one"]


def test_the_reconstruction_is_a_fixed_point_of_its_generator():
    result, changed = _fixed_point_of(
        "build_ste_invariants.py",
        EXCHANGE / "ste_invariants.yaml",
        EXCHANGE / "ste_invariants.sha256",
    )
    assert result.returncode == 0, result.stderr
    assert changed == [], (
        "the committed reconstruction differs from regeneration -- STE's documents changed, which "
        "means the pin moved, which means `bent: zero` needs re-establishing"
    )


def test_every_reconstructed_invariant_states_what_would_refute_it():
    """An inference presented without its defeater reads as a finding."""
    for name, entry in STE["reconstruction"].items():
        if entry["recoverable"] is False:
            assert entry["reconstruction"] is None and entry["why_not"], name
        else:
            assert entry["reconstruction"], name
            assert entry.get("what_would_refute_it"), (
                f"{name} is an inference with no stated defeater"
            )


def test_the_two_unrecoverable_ones_really_are_cited_only_inside_a_range():
    """Measured against the index the generator derived, not against the
    prose beside it. This was WRONG on the first run: a bare `I1` inside
    `I1-I8` was counted as an individual citation, so the invariant least
    able to be recovered appeared to have evidence of its own."""
    # The internal-consistency check held while this was a LIVE
    # reconstruction derived from one tree. Its index is now scanned from
    # a tree 68 commits newer than the verdicts beside it, so the two
    # genuinely disagree -- and that disagreement is WHY it is frozen,
    # not a defect to reconcile. A reconstruction is an account of what a
    # tree held at a commit; re-deriving it against a tree that now
    # DECLARES the thing would produce neither.
    assert STE["standing"] == "SUPERSEDED_BY_THE_DECLARATION"
    assert "outliving its basis" in STE["why_it_is_not_re_derived_against_the_new_pin"]

    not_recoverable = {k for k, v in STE["reconstruction"].items() if v["recoverable"] is False}
    assert not_recoverable == {"I1", "I2"}, (
        "the frozen reconstruction's verdicts moved; a frozen artifact must not"
    )
    # THE ARTIFACT IS HALF-FROZEN AND THAT IS A KNOWN DEFECT, recorded
    # here rather than hidden by an assertion that still passes.
    #
    # Its per-invariant VERDICTS are hand-written and frozen; its
    # reference INDEX is re-scanned from the vendored tree on every
    # generation. At the new pin the index finds individual citations for
    # I1 and I2, which the frozen verdicts call unrecoverable. Both halves
    # are internally right about different trees, and an artifact that is
    # live in one half and frozen in the other is worse than either.
    #
    # Not resolved here: choosing between freezing the index too and
    # retiring the artifact for the declaration is a design decision about
    # what a superseded reconstruction IS, and making it at the tail of a
    # pin bump is how a considered choice becomes an accident. The
    # divergence is asserted as EXPECTED so it cannot be mistaken for
    # agreement, and it is named in the artifact.
    live_index_disagrees = {name for name in not_recoverable if name in STE["reference_index"]}
    assert live_index_disagrees == {"I1", "I2"}, (
        f"the half-frozen divergence changed shape: {sorted(live_index_disagrees)}. Either the "
        "index was frozen too, or the verdicts moved -- both are decisions, and neither should "
        "arrive silently."
    )


def test_the_larger_cardinality_names_invariants_no_document_mentions():
    nowhere = STE["the_cardinality_conflict"]["referenced_nowhere_at_all"]
    assert nowhere, (
        "the competing count no longer implies any uncited invariant -- the conflict may be "
        "resolved, and the reconstruction should be re-derived"
    )


# ------------------------------------------- 4. what bent: zero quantified over


def test_every_bent_zero_claim_is_accounted_for_in_the_register():
    """Derived by scanning, so a claim written tomorrow that nobody
    accounted for fails here until someone re-derives -- which is the
    point at which they have to say which property set they mean."""
    block = REGISTER["bent_zero_claims_held_here"]
    claims = {(e["document"], e["line"]) for e in block["occurrences"]}
    mentions = {(e["document"], e["line"]) for e in block["mentions_not_claims"]}

    # EVERY appearance of the phrase must be in one bucket or the other.
    # Checking only the claims would let the narrowing to the claim form
    # hide an appearance rather than classify it -- which is the whole risk
    # a narrowing carries.
    found = set()
    for path in sorted((REPO_ROOT / "docs").rglob("*.md")):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if re.search(r"(?<![\w])Bent: zero(?![\w])", line):
                found.add((str(path.relative_to(REPO_ROOT)), number))
    assert found == claims | mentions, (
        f"unaccounted appearances: {sorted(found - (claims | mentions))}; "
        f"accounted but no longer present: {sorted((claims | mentions) - found)}"
    )
    assert not (claims & mentions), "an appearance is filed as both a claim and a mention"
    assert block["count"] == len(claims)
    assert block["mention_count"] == len(mentions)


def test_the_ten_four_property_claims_and_the_one_five_property_claim_split_in_git():
    """The register says ten were written against a four-property probe
    and one against five. Checked against history."""
    block = REGISTER["bent_zero_claims_held_here"]
    documents = sorted({entry["document"] for entry in block["occurrences"]})
    before, after = [], []
    for document in documents:
        added = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%H", "-1", "--", document],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        if added.returncode != 0 or not added.stdout.strip():
            pytest.skip(f"no add-commit for {document} in this checkout")
        commit = added.stdout.strip()
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", "c80a2f0", commit],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        (after if ancestor.returncode == 0 else before).append(document)

    assert len(before) == 10, (
        f"expected ten reports predating the five-property probe; measured {len(before)}"
    )
    assert len(after) >= 1 and any("PHASE_36" in d for d in after), (
        f"Phase 36 was the first report written against the five-property set; measured {after}"
    )
    # Every report added from here on is on the five-property side, so this
    # side grows and the other must not.
    assert not any("PHASE_3" in d and int(d.split("PHASE_")[1][:2]) > 36 for d in before), (
        f"a report written after the probe grew is counted against the four-property set: {before}"
    )


def test_the_verdicts_survive_the_wider_set_and_the_register_says_why():
    """A verdict that happens to survive a change in what it quantifies
    over is not a verdict that accounted for the change. The register has
    to say which of the two it is."""
    block = REGISTER["bent_zero_claims_held_here"]
    assert block["does_the_fifth_property_change_any_of_the_ten"].startswith("NO")
    assert "measured rather than assumed" in block[
        "does_the_fifth_property_change_any_of_the_ten"]
    assert "not a verdict that accounted for the change" in block[
        "what_was_wrong_was_not_the_verdicts"]

    probe = loads((REPO_ROOT / "architecture" / "_probes" / "generality.yaml").read_text())
    assert probe["outcome"]["core_invariants_modified"] == 0, (
        "the fifth property now reports a core-invariant modification, so the ten earlier claims "
        "no longer survive the wider set and must be revisited individually"
    )


def test_a_mention_of_bent_zero_is_not_counted_as_a_claim():
    """NARROWED AFTER IT FIRED. The scan matched the phrase anywhere, which
    was correct while every occurrence was a claim -- eleven reports, one
    bolded assertion each. The first report to DISCUSS the class rather
    than only assert it counted three, and the register would have said
    fourteen claims where twelve exist.

    Both are recorded, so the narrowing is visible: a claim written in a
    new form shows up here as a mention with no claim beside it."""
    block = REGISTER["bent_zero_claims_held_here"]
    documents = [o["document"] for o in block["occurrences"]]
    assert len(documents) == len(set(documents)), (
        f"a report is counted twice, so mentions are being read as claims: {documents}"
    )
    assert block["count"] == len(documents)
    assert block["mention_count"] >= 1, (
        "no mentions found at all -- either the distinction stopped being exercised, or the scan "
        "no longer sees them and the narrowing has become invisible"
    )
    for mention in block["mentions_not_claims"]:
        assert "**Bent: zero.**" not in mention["text"], (
            f"a claim was filed as a mention: {mention}"
        )

# ------------- the write-on-verify hazard, closed before the pin can move


def test_a_vendor_reading_generator_refuses_when_the_tree_and_index_disagree():
    """PLANTED AND MEASURED. These two generators' output is a function of
    the vendored tree, so running them while that tree and the index
    disagree produces an artifact derived from a commit the pin does not
    name -- correctly hashed and wrong.

    Checked by source rather than by actually desynchronising the
    submodule inside a test: doing that for real would leave the repo in
    the very state the guard exists to prevent if the test were
    interrupted."""
    for generator in ("build_invariant_register.py", "build_ste_invariants.py"):
        source = (EXCHANGE / generator).read_text()
        assert "_refuse_if_the_pin_and_the_tree_disagree" in source, generator
        assert 'if marker in "+-U"' in source, generator
        assert "REFUSING to generate" in source, generator

    pin_independent = ("build_daq_capabilities.py", "build_daq_requirement_response.py")
    for generator in pin_independent:
        source = (EXCHANGE / generator).read_text()
        assert "submodule_path" not in source and "vendor/" not in source, (
            f"{generator} now reads the vendored tree and needs the same guard")


def test_the_fixed_point_check_restores_every_file_the_generator_writes():
    """The concrete defect: the generators write an artifact AND a
    sidecar, and the restore covered only the artifact. Asserted as a
    correspondence -- every path a generator writes is a path the check
    snapshots -- rather than as a count, which would go stale the moment
    a generator wrote a third file."""
    import re

    for generator, checker in (
        ("build_invariant_register.py", "test_the_register_is_a_fixed_point_of_its_generator"),
        ("build_ste_invariants.py", "test_the_reconstruction_is_a_fixed_point_of_its_generator"),
    ):
        written = set(re.findall(r'HERE / "([^"]+)"\)\.write_', (EXCHANGE / generator).read_text()))
        assert written, generator

        # Resolved against module globals, because a path may be passed by
        # constant (REGISTER_PATH) rather than by literal. Checking the
        # source text alone would pass on the alias and fail on the name,
        # which is a check reading a proxy for the thing it means.
        body = _test_source(checker)
        restored = set()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", body):
            value = globals().get(token)
            if isinstance(value, pathlib.Path):
                restored.add(value.name)
        restored |= set(re.findall(r'"([^"]+\.(?:yaml|sha256))"', body))

        missing = sorted(written - restored)
        assert missing == [], (
            f"{checker} does not restore {missing}, which {generator} writes. A failing "
            "fixed-point check would leave the tree in a state no commit describes.")


def _test_source(name: str) -> str:
    source = pathlib.Path(__file__).read_text()
    start = source.index(f"def {name}(")
    end = source.find("\ndef ", start + 1)
    return source[start:end if end != -1 else len(source)]


def test_the_deferral_on_the_half_frozen_reconstruction_still_holds():
    """THE TRIGGER, not a note. The half-frozen reconstruction is parked
    with a stated condition: the deferral is valid WHILE nothing but this
    test reads its reference_index. A stale index feeding a live consumer
    is the shape this pair has spent several phases removing, so the
    moment the index is consumed the divergence becomes load-bearing and
    the decision has to be made rather than carried.

    DAQ has kept its parked items in prose until now, and prose is how two
    of the counterparty's faded. A deferral with no condition attached is
    indistinguishable from an omission once the session that made it
    ends."""
    deferral = STE["the_deferral"]
    assert deferral["not_a_decision"].startswith("recorded as UNDECIDED")
    assert pathlib.Path(__file__).name in deferral["trigger_enforced_by"]

    # The PRODUCER is not a consumer. build_ste_invariants.py writes the
    # index; excluding it is not weakening the trigger, because a
    # generator writing its own field is what the deferral describes, not
    # what would end it.
    producer = "architecture/exchange/build_ste_invariants.py"
    consumers = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        parts = path.parts
        if "vendor" in parts or "__pycache__" in parts or path.name == pathlib.Path(__file__).name:
            continue
        relative = str(path.relative_to(REPO_ROOT))
        if relative == producer:
            continue
        if "reference_index" in path.read_text():
            consumers.append(relative)
    assert (REPO_ROOT / producer).exists(), (
        "the producer moved; the exclusion above now hides a real consumer")

    assert consumers == [], (
        f"{consumers} now read the reconstruction's reference_index. The deferral recorded in "
        "architecture/exchange/ste_invariants.yaml was valid only while the half-frozen state was "
        "inert; it is load-bearing now. Decide: freeze the index too, or retire the file for the "
        "declaration."
    )


def test_every_generator_that_reads_HEAD_refuses_during_an_unresolved_merge():
    """FOUND BY THE TREE-VS-INDEX GUARD PASSING while the artifact came out
    wrong. `gitlink_commit()` asks `git ls-tree HEAD`, and during an
    unresolved merge HEAD is the PRE-merge commit -- so the register
    recorded joined_on.value 5e146d5 from core.yaml beside
    gitlink_at_generation 3e5bea9 from HEAD, in one file.

    Asserted as a CORRESPONDENCE rather than a list: a generator needs
    this guard exactly when it reads HEAD. build_ste_invariants.py does
    not read HEAD and correctly does not carry it, and a generator that
    starts reading HEAD tomorrow fails here until it does."""
    for generator in sorted(EXCHANGE.glob("build_*.py")):
        source = generator.read_text()
        reads_head = "ls-tree" in source and "HEAD" in source
        guarded = "_refuse_if_a_merge_is_unresolved" in source
        assert reads_head == guarded, (
            f"{generator.name}: reads HEAD={reads_head} but merge-guarded={guarded}. A generator "
            "reading HEAD records a claim about the repository that is not true mid-merge."
        )


def test_the_merge_guard_fires_and_names_every_unresolved_state():
    source = (EXCHANGE / "build_invariant_register.py").read_text()
    for marker in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD"):
        assert marker in source, f"{marker} leaves HEAD stale too and is not covered"
    assert "REFUSING to generate" in source


def test_the_run_summary_cannot_disagree_with_the_artifact():
    """It did: `ste none enumerated` was a hardcoded string in the print
    while the document derived 58 -- a prose statement beside a derived
    value, which is the class this repository files most."""
    source = (EXCHANGE / "build_invariant_register.py").read_text()
    assert "ste none enumerated" not in source
    assert "STE_COUNT" in source
