"""The corpus contract, checked against THIS side's code and its own yaml.

Three declarations of one vocabulary exist on this side: the constants in
`epistemics.evidence_class`, the terminology lock in
`architecture/evidence_class.yaml`, and now the ecosystem contract. The
first two already had a test binding them. This adds the third to the same
binding rather than starting a fourth list -- which is the defect the
contract exists to close, and it would be a poor joke to commit it here.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

from epistemics import evidence_class as ec  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from epistemics.corpus import contract as cc  # noqa: E402

CONTRACT = cc.contract()
LOCK = loads((REPO_ROOT / "architecture" / "evidence_class.yaml").read_text())


class TestTheVendoredCopyIsThePinnedOne:
    def test_hashes_to_the_pin(self):
        digest = hashlib.sha256(cc.contract_bytes()).hexdigest()
        assert digest == cc.CONTRACT_DIGEST

    def test_an_edited_copy_raises_rather_than_loading(self, tmp_path, monkeypatch):
        # The digest check has to be reachable, not just present. A guard that
        # cannot be made to fire is the vacuous pass this program keeps filing.
        tampered = tmp_path / "contract.json"
        tampered.write_text('{"contract": "not-it"}')
        monkeypatch.setattr(cc, "CONTRACT_PATH", tampered)
        with pytest.raises(cc.ContractDigestMismatch):
            cc.contract()

    def test_is_the_contract_this_module_names(self):
        assert CONTRACT["contract"] == cc.CONTRACT_ID
        assert CONTRACT["version"] == cc.CONTRACT_VERSION


class TestTheLocalVocabularyIsTheContractVocabulary:
    def test_production_class_terms_match_the_code(self):
        axis = CONTRACT["axes"]["production_class"]
        assert sorted(axis["terms"]) == sorted(ec.INGEST_CLASSES)

    def test_production_class_terms_match_the_yaml_lock(self):
        # All three, pairwise, so a fix in one that misses another fails here.
        axis = CONTRACT["axes"]["production_class"]
        assert sorted(axis["terms"]) == sorted(LOCK["ingest_classes"])

    def test_the_absence_term_agrees_and_is_not_a_class(self):
        axis = CONTRACT["axes"]["production_class"]
        assert axis["absence"] == ec.UNCLASSIFIED == LOCK["migration_state"]
        assert ec.UNCLASSIFIED not in ec.INGEST_CLASSES
        assert ec.UNCLASSIFIED not in axis["terms"]

    def test_production_class_is_unordered_and_the_contract_says_why(self):
        # Ranking these would be answering claim_strength's question with this
        # axis's terms. The code carries no rank; the contract must not either.
        axis = CONTRACT["axes"]["production_class"]
        assert axis["ordered"] is False
        assert "rank" not in axis
        assert not hasattr(ec, "INGEST_RANK")


class TestThisFabricDeclaresWhatItHasAndWhatItDoesNot:
    def test_agrees_with_the_contract_about_its_axes(self):
        me = CONTRACT["implementations"]["data-acquisition-fabric"]
        assert sorted(me["axes_implemented"]) == sorted(cc.AXES_IMPLEMENTED)
        assert sorted(me["axes_absent"]) == sorted(cc.AXES_ABSENT)

    def test_its_absence_is_deliberate_and_the_other_corpus_is_not(self):
        # The two absences are different in kind. Filing them the same way
        # would turn an open gap into a decision nobody made.
        assert CONTRACT["implementations"]["data-acquisition-fabric"]["absence_is_deliberate"] is True
        assert CONTRACT["implementations"]["payload-terminal"]["absence_is_deliberate"] is False
        for reason in cc.AXES_ABSENT.values():
            assert reason.startswith("DELIBERATE")

    def test_every_implemented_axis_names_a_symbol_that_exists(self):
        # A declaration pointing at a deleted module would pass every other
        # check while claiming an axis nobody implements.
        for axis, where in cc.AXES_IMPLEMENTED.items():
            path, symbol = where.split(":")
            source = (REPO_ROOT / path).read_text()
            assert symbol in source, f"{axis} points at {path}:{symbol}"


class TestTheCollisionThisContractExistsToStop:
    def test_reported_is_refused_and_the_reason_names_asserted(self):
        # VOCABULARY_MAP sends `reported` to ASSERTED here. Over there it is
        # the hardest class there is. The contract must refuse the crossing.
        assert ec.VOCABULARY_MAP["reported"] == ec.ASSERTED
        term = CONTRACT["contested_terms"]["reported"]
        assert term["translation"] == "refused"
        assert "asserted" in term["refusal_reason"]

    def test_the_refusal_is_reachable_from_code_not_only_from_prose(self):
        # A boundary caller asks the module, so the refusal cannot be
        # remembered in one direction and forgotten in the other.
        assert "reported" in cc.refused_translations()

    def test_derived_is_allowed_downward_only(self):
        term = CONTRACT["contested_terms"]["derived"]
        assert term["translation"] == "one_way"
        assert term["direction"] == "production_class.derived -> claim_strength.derived"
        assert ec.DERIVED in ec.INGEST_CLASSES

    def test_every_contested_term_is_resolved_with_a_reason(self):
        allowed = {"refused", "one_way", "symmetric"}
        for name, spec in CONTRACT["contested_terms"].items():
            if name == "note":
                continue
            assert spec["translation"] in allowed, f"{name}: {spec['translation']}"
            assert spec.get("refusal_reason") or spec.get("direction_reason"), name

    def test_the_contested_set_covers_every_term_on_two_axes(self):
        # THE CONSERVATION CHECK. A term shared between axes and absent from
        # contested_terms is the worst state: it looks handled. `derived` was
        # found by reading; this finds the next one without anybody reading.
        axes = CONTRACT["axes"]
        production = set(axes["production_class"]["terms"])
        strength = set(axes["claim_strength"]["terms"])
        vocabulary = set(ec.VOCABULARY_MAP)
        shared = (production | vocabulary) & strength
        resolved = {k for k in CONTRACT["contested_terms"] if k != "note"}
        # Non-vacuity first: an empty `shared` would satisfy the subset check
        # while establishing nothing, which is how a conservation check passes
        # for the wrong reason.
        assert shared, "no term is shared between the axes -- the check found nothing to conserve"
        assert shared - resolved == set(), f"shared but unresolved: {sorted(shared - resolved)}"
        # And the reverse: a resolved term that is not actually contested is a
        # row in the contract doing nothing but looking load-bearing.
        assert resolved - shared == set(), f"resolved but not contested: {sorted(resolved - shared)}"


class TestWhatConformanceDoesNotProve:
    def test_the_limit_is_stated_in_the_module_not_only_in_the_contract(self):
        assert "stale" in cc.CONFORMANCE_LIMIT
        assert "does NOT prove" in " ".join(CONTRACT["what_conformance_proves"])
