"""The seam that decides whether layers 1 and 2 are a drop-in or a rewrite.

architecture/platform_target.yaml records a directive whose first two
layers are S3-compatible object storage and PostgreSQL as canonical
operational truth. Both are SUBSTITUTIONS of the durable store behind an
unchanged pool. Before this, `DurablePool` took the concrete
`FilesystemEvidenceStore`, so the substitution was a drop-in in shape and
refused by the checker.

WHAT IS TESTED HERE IS NOT THAT A PROTOCOL EXISTS. `isinstance` against a
runtime-checkable Protocol compares METHOD NAMES ONLY and never
signatures, so an object with eighteen methods that all raise would pass
it. The test that matters drives a real DurablePool through a SECOND
implementation and checks that the evidence comes back.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Dict, Tuple

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from daf.query import census, warrant_for  # noqa: E402
from daf.storage.durable_pool import DurablePool  # noqa: E402
from daf.storage.evidence_store import EvidenceStore  # noqa: E402
from daf.storage.filesystem_store import FilesystemEvidenceStore  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

ANCHOR = (REPO_ROOT / "tests" / "fixtures"
          / "physchem_study_anchor_wil_505902_water_solubility.json")

_CATEGORIES = ("sources", "documents", "records", "observations", "referents",
               "claimed_relationships", "derived_values", "derived_groundings")


class InMemoryIndex:
    """The catalog half, over the same dictionaries. Small on purpose:
    the point is that the five queries are answerable without a
    filesystem, which is what makes a PostgreSQL index a substitution
    rather than a redesign."""

    def __init__(self, by_category: Dict[str, Dict[str, Any]]) -> None:
        self._by_category = by_category

    def all_ids(self, category: str) -> Tuple[str, ...]:
        return tuple(sorted(self._by_category[category]))

    def list_versions(self, artifact_id: str) -> Tuple[str, ...]:
        return ()

    def find_by_content_hash(self, doc_content_hash: str) -> Tuple[str, ...]:
        return tuple(sorted(
            document_id for document_id, document in self._by_category["documents"].items()
            if getattr(document, "content_hash", None) == doc_content_hash))

    def list_source_artifacts(self, source_id: str) -> Tuple[str, ...]:
        return tuple(sorted(
            document_id for document_id, document in self._by_category["documents"].items()
            if getattr(document, "source_id", None) == source_id))

    def locator_for_document(self, document_id: str):
        for record in self._by_category["records"].values():
            if getattr(record, "document_id", None) == document_id:
                return record.locator
        return None


class InMemoryEvidenceStore:
    """A second implementation, deliberately sharing no code with the
    filesystem one. It is not a mock: it stores and returns the objects,
    so a pool driven through it either works or does not.

    It is what a PostgreSQL store would be shaped like from the pool's
    side -- put by type, get by id, enumerate by category -- and its
    existence is the only evidence that the protocol describes the pool's
    needs rather than the filesystem's habits.
    """

    def __init__(self) -> None:
        self._by_category: Dict[str, Dict[str, Any]] = {c: {} for c in _CATEGORIES}
        # A REAL INDEX, not None. Writing this store is what revealed that
        # `index` is a nested interface the pool depends on rather than an
        # opaque attribute -- and that its five queries are the ones the
        # directive gives to PostgreSQL.
        self.index = InMemoryIndex(self._by_category)

    def _put(self, category: str, obj: Any) -> None:
        self._by_category[category][obj.id] = obj

    def put_source(self, source: Any) -> None: self._put("sources", source)
    def put_document(self, document: Any) -> None: self._put("documents", document)
    def put_record(self, record: Any) -> None: self._put("records", record)
    def put_observation(self, observation: Any) -> None: self._put("observations", observation)
    def put_referent(self, referent: Any) -> None: self._put("referents", referent)

    def put_claimed_relationship(self, relationship: Any) -> None:
        self._put("claimed_relationships", relationship)

    def put_derived_value(self, derived_value: Any) -> None:
        self._put("derived_values", derived_value)

    def put_derived_grounding(self, grounding: Any) -> None:
        self._put("derived_groundings", grounding)

    def has_source(self, source_id: str) -> bool: return source_id in self._by_category["sources"]
    def has_document(self, document_id: str) -> bool: return document_id in self._by_category["documents"]
    def has_record(self, record_id: str) -> bool: return record_id in self._by_category["records"]

    def has_observation(self, observation_id: str) -> bool:
        return observation_id in self._by_category["observations"]

    def get_source(self, source_id: str) -> Any: return self._by_category["sources"][source_id]
    def get_document(self, document_id: str) -> Any: return self._by_category["documents"][document_id]
    def get_record(self, record_id: str) -> Any: return self._by_category["records"][record_id]

    def get_observation(self, observation_id: str) -> Any:
        return self._by_category["observations"][observation_id]

    def all_sources(self) -> Tuple[Any, ...]: return tuple(self._by_category["sources"].values())
    def all_documents(self) -> Tuple[Any, ...]: return tuple(self._by_category["documents"].values())
    def all_records(self) -> Tuple[Any, ...]: return tuple(self._by_category["records"].values())

    def all_observations(self) -> Tuple[Any, ...]:
        return tuple(self._by_category["observations"].values())

    def all_referents(self) -> Tuple[Any, ...]: return tuple(self._by_category["referents"].values())

    def all_claimed_relationships(self) -> Tuple[Any, ...]:
        return tuple(self._by_category["claimed_relationships"].values())

    def all_derived_values(self) -> Tuple[Any, ...]:
        return tuple(self._by_category["derived_values"].values())

    def all_derived_groundings(self) -> Tuple[Any, ...]:
        return tuple(self._by_category["derived_groundings"].values())

    def all_ids_by_filename(self, category: str) -> Tuple[str, ...]:
        return tuple(sorted(self._by_category[category]))


def _acquire_into(pool) -> None:
    run_scout(GpcReportSourceAdapter(
        path=ANCHOR, source_name="regulations-gov", retrieved_at="2026-08-30T00:00:00Z",
        data_provenance="instrument_measurement", sample_id="CDC-003",
        sample_kind="sample"), GpcReportExtractor(), pool)


# =====================================================================
# The substitution actually works
# =====================================================================

def test_a_second_store_implementation_carries_a_real_acquisition():
    """The discriminating case. Fails in the state where the protocol
    describes the filesystem store's habits rather than the pool's needs
    -- a second implementation then cannot satisfy it and this stops
    running at all."""
    pool = DurablePool(InMemoryEvidenceStore())
    _acquire_into(pool)

    observations = list(pool.all_observations())
    assert len(observations) == 20
    warrant = warrant_for(pool, observations[0].id)
    assert warrant.measured_property == "eluate_concentration"
    assert warrant.provenance[0].source_name == "regulations-gov"
    assert census(pool)["by_property"] == {"eluate_concentration": 20}


def test_the_two_stores_are_indistinguishable_from_the_pools_side(tmp_path):
    """Same acquisition, two substrates, identical evidence. This is the
    property the directive's layer-2 migration rests on."""
    memory = DurablePool(InMemoryEvidenceStore())
    disk = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    _acquire_into(memory)
    _acquire_into(disk)

    def summarise(pool):
        return sorted((o.id, o.content["value"]) for o in pool.all_observations())

    assert summarise(memory) == summarise(disk)
    assert census(memory) == census(disk)


def test_restore_reconstructs_through_the_protocol_and_not_through_a_filesystem():
    """`DurablePool.restore` is the process-restart path. If it needed a
    filesystem it would be the one method blocking a Postgres store."""
    store = InMemoryEvidenceStore()
    _acquire_into(DurablePool(store))

    restored = DurablePool.restore(store)
    assert len(list(restored.all_observations())) == 20


# =====================================================================
# The protocol describes the pool's needs, and says what it cannot prove
# =====================================================================

def test_the_filesystem_store_satisfies_the_protocol_without_knowing_it_exists(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    assert isinstance(store, EvidenceStore)
    source = (REPO_ROOT / "daf" / "storage" / "filesystem_store.py").read_text()
    # The IMPORT, not the substring -- the class is called
    # FilesystemEvidenceStore and contains the protocol's name by accident.
    assert "from daf.storage.evidence_store import" not in source, (
        "the concrete store must not import the protocol; structural satisfaction is "
        "the whole point, and an explicit base class would make the next "
        "implementation inherit from this one's assumptions"
    )


def test_the_protocol_states_that_isinstance_proves_almost_nothing():
    """A guard against this file's own weakest test. `isinstance` on a
    Protocol compares method NAMES, so an object whose methods all raise
    passes it."""
    source = (REPO_ROOT / "daf" / "storage" / "evidence_store.py").read_text()
    assert "METHOD NAMES ONLY" in source
    assert "is not a working store" in source

    class NamesOnly:
        pass

    for name in ("put_source", "put_document", "put_record", "put_observation",
                 "put_referent", "put_claimed_relationship", "put_derived_value",
                 "put_derived_grounding", "has_source", "has_document", "has_record",
                 "has_observation", "get_source", "get_document", "get_record",
                 "get_observation", "all_sources", "all_documents", "all_records",
                 "all_observations", "all_referents", "all_claimed_relationships",
                 "all_derived_values", "all_derived_groundings", "all_ids_by_filename"):
        setattr(NamesOnly, name, lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError))
    NamesOnly.index = InMemoryIndex({c: {} for c in _CATEGORIES})
    assert isinstance(NamesOnly(), EvidenceStore), (
        "if this stops passing, isinstance has become meaningful and the warning "
        "in the module is stale"
    )
    with pytest.raises(RuntimeError):
        DurablePool(NamesOnly()).all_observations()


#: The sites that are GENUINELY filesystem-bound, with what each needs.
#: A BASELINE OF A KNOWN COUPLING, never a permission: the check below
#: fires the moment a third joins them, and fires if one leaves without
#: the baseline being tightened.
FILESYSTEM_BOUND = {
    "daf/storage/classified_pool.py": "ClassAssignmentStore(store.root) -- the "
                                      "evidence-class register is persisted beside the "
                                      "evidence, keyed by a path",
    "daf/execution/metrics.py": "store.categories, a filesystem-store attribute",
}


def test_only_the_genuinely_filesystem_bound_sites_still_type_against_the_concrete_store():
    """The coupling this removed, asserted as a property rather than at
    three known sites -- and the two that remain are named with what they
    need, because a coupling with no reason recorded is indistinguishable
    from one nobody got to."""
    # PARSED, not grepped. A first version matched lines and flagged the
    # protocol module's own docstring, which explains the coupling it
    # removed -- prose about an annotation is not an annotation.
    #
    # And STRING annotations count. The first parsed version looked only
    # for ast.Name, so `store: "FilesystemEvidenceStore"` -- a forward
    # reference, which is how a coupling gets written when the import is
    # under TYPE_CHECKING -- parsed as a Constant and went straight past
    # it. Found by planting exactly that and watching the guard stay
    # green, which is the whole reason plants are planted.
    import ast

    def _names_the_concrete_store(annotation) -> bool:
        for node in ast.walk(annotation):
            if isinstance(node, ast.Name) and node.id == "FilesystemEvidenceStore":
                return True
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                try:
                    inner = ast.parse(node.value, mode="eval").body
                except SyntaxError:
                    continue
                if any(isinstance(n, ast.Name) and n.id == "FilesystemEvidenceStore"
                       for n in ast.walk(inner)):
                    return True
        return False

    offenders = []
    for path in (REPO_ROOT / "daf").rglob("*.py"):
        if path.name == "filesystem_store.py":
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            annotations = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                annotations = [a.annotation for a in
                               node.args.args + node.args.kwonlyargs if a.annotation]
                if node.returns is not None:
                    annotations.append(node.returns)
            elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
                annotations = [node.annotation]
            for annotation in annotations:
                if _names_the_concrete_store(annotation):
                    offenders.append(
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    coupled = {site.split(":")[0] for site in offenders}
    assert coupled == set(FILESYSTEM_BOUND), (
        f"the filesystem coupling moved: {sorted(coupled ^ set(FILESYSTEM_BOUND))}. "
        "If it GREW, a new site types against the concrete store and the directive's "
        "layers 1 and 2 have one more thing to move. If it SHRANK, tighten this "
        "baseline; a stale allowance is how a coupling becomes permanent."
    )
    # And each remaining site must say WHY, at the site.
    for path in FILESYSTEM_BOUND:
        source = (REPO_ROOT / path).read_text()
        assert "FilesystemEvidenceStore" in source
        assert "filesystem" in source.lower(), f"{path} is coupled and does not say why"


def test_the_platform_record_and_the_tree_agree_on_this_seam():
    target = loads((REPO_ROOT / "architecture" / "platform_target.yaml").read_text())
    seam = target["position_measured_against_each_layer"]["layer_2_canonical_state"][
        "the_seam_that_makes_layer_2_cheap_or_expensive"]
    assert "the difference is three annotations" in seam, (
        "the record describes the seam as it was BEFORE this repair; if the repair is "
        "being described instead, the measurement and the record have been conflated"
    )
