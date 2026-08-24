"""End-to-end tests for the SCOUT live-ingestion vertical slice: real
ArxivSourceAdapter + real ArxivExtractor, run through the UNMODIFIED
scout.pipeline.run_scout and evidence.admission gate.

These tests prove the specific properties required before this phase can
be considered done -- see docs/SCOUT_VERTICAL_SLICE.md for the full
report this file backs up.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import Observation
from scout.pipeline import run_scout

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.extractors.arxiv import ArxivExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_fetcher(name: str):
    def _fetch(url: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return _fetch


def _adapter(fixture_name: str, arxiv_ids=("9999.00001",), retrieved_at="2026-08-24T00:00:00Z"):
    return ArxivSourceAdapter(
        arxiv_ids=arxiv_ids, retrieved_at=retrieved_at, fetch_bytes=_fixture_fetcher(fixture_name)
    )


def test_full_pipeline_admits_evidence_through_existing_gate():
    """Property 3: evidence passes through the existing SCOUT admission gate."""
    pool = EvidencePool()
    findings, failures = run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)

    assert failures == ()
    assert len(findings) == 1
    finding = findings[0]

    # Every object the finding surfaces is the SAME object stored in the pool
    # via the unmodified admission gate -- no DAF-side shortcut object exists.
    assert pool.get_source(finding.source.id) == finding.source
    assert pool.get_document(finding.document.id) == finding.document
    assert pool.get_record(finding.record.id) == finding.record
    assert pool.get_observation(finding.observation.id) == finding.observation
    assert {r.id for r in finding.referents} <= {r.id for r in pool.all_referents()}


def test_observation_uses_existing_evidence_semantics():
    """Property 4: the Observation is produced using existing evidence
    semantics -- a real evidence.types.Observation, not a DAF-invented type."""
    pool = EvidencePool()
    findings, _ = run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)
    observation = findings[0].observation

    assert isinstance(observation, Observation)
    assert observation.confidence == 1.0
    assert observation.extraction_method == "xml:arxiv_atom_v1"
    assert observation.content["arxiv_id"] == "http://arxiv.org/abs/9999.00001v1"
    assert observation.content["title"] == "A Deterministic Fixture Paper on Test Adhesion"


def test_provenance_survives_the_complete_pipeline():
    """Property 5: every admitted Observation remains traceable back to
    external source -> acquisition -> raw content -> extraction."""
    pool = EvidencePool()
    findings, _ = run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)
    finding = findings[0]

    assert finding.observation.record_ids == (finding.record.id,)
    record = pool.get_record(finding.observation.record_ids[0])
    assert record.document_id == finding.document.id
    document = pool.get_document(record.document_id)
    assert document.source_id == finding.source.id
    source = pool.get_source(document.source_id)

    assert source.kind == "paper"
    assert source.name == "arXiv"
    assert document.retrieval_method == "http:arxiv_api_v1"
    assert "A Deterministic Fixture Paper on Test Adhesion" in record.raw_content


def test_identical_content_is_deduplicated():
    """Property 6: same source + same content -> same identity, no
    duplicate evidence proliferation."""
    pool = EvidencePool()
    run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)
    fingerprint_after_first = pool.fingerprint()

    run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)

    assert pool.fingerprint() == fingerprint_after_first
    assert len(pool.all_observations()) == 1


def test_changed_content_is_distinguishable_as_a_new_version():
    """Property 7: same source + changed content -> a distinct,
    coexisting evidence version, never a silent overwrite."""
    pool = EvidencePool()
    findings_v1, _ = run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)
    findings_v2, _ = run_scout(_adapter("arxiv_single_entry_v1_revised.xml"), ArxivExtractor(), pool)

    document_v1 = findings_v1[0].document
    document_v2 = findings_v2[0].document

    assert document_v1.id != document_v2.id
    assert pool.has_document(document_v1.id)
    assert pool.has_document(document_v2.id)
    assert len(pool.all_observations()) == 2


def test_shared_author_across_papers_resolves_to_one_referent():
    """Exact-match Referent identity means the same author named
    identically across two papers converges on one Referent -- no fuzzy
    entity resolution, matching the existing architecture's discipline."""
    pool = EvidencePool()
    findings, failures = run_scout(_adapter("arxiv_two_entries.xml", arxiv_ids=("9999.00001", "9999.00002")), ArxivExtractor(), pool)

    assert failures == ()
    assert len(findings) == 2

    ada_referents = {
        r.id
        for finding in findings
        for r in finding.referents
        if r.kind == "author" and r.natural_key == "Ada Example"
    }
    assert len(ada_referents) == 1


def test_failed_acquisition_is_handled_cleanly_not_silently():
    """Property 8: a broken source raises loudly instead of admitting
    corrupt or partial evidence."""

    def _broken_fetch(url: str) -> bytes:
        raise ConnectionError("simulated network failure")

    adapter = ArxivSourceAdapter(
        arxiv_ids=("9999.00001",), retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_broken_fetch
    )
    with pytest.raises(ConnectionError):
        adapter.fetch()


def test_admission_never_bypasses_existing_identity_computation():
    """Property 10: the admitted Observation's id is exactly what
    evidence.types.make_observation would independently compute -- no
    DAF-side identity shortcut exists anywhere in this pipeline."""
    pool = EvidencePool()
    findings, _ = run_scout(_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool)
    observation = findings[0].observation

    expected_id = content_hash(
        {
            "record_ids": list(sorted(observation.record_ids)),
            "extraction_method": observation.extraction_method,
            "content": dict(sorted(observation.content.items())),
        }
    )
    assert observation.id == expected_id


def test_adapter_and_extractor_never_reference_the_state_space_domain_layers():
    """Property 9: the DAF's adapter/extractor never import materials/
    (ModelState), experiment/, workbench/, core/ (CanonicalState), morpho/,
    or backends/ -- an AST-level import check, matching the house style
    the vendored repo's own boundary tests already use."""
    forbidden = {"materials", "experiment", "workbench", "core", "morpho", "backends", "runtime"}
    daf_root = Path(__file__).parent.parent / "daf"

    for path in (daf_root / "adapters" / "arxiv.py", daf_root / "extractors" / "arxiv.py"):
        tree = ast.parse(path.read_text())
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        crossed = imported_roots & forbidden
        assert not crossed, f"{path.name} imports {crossed}, crossing the DAF/State-Space boundary"
