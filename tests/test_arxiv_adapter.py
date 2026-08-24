"""Tests for daf.adapters.arxiv.ArxivSourceAdapter -- the real
SourceAdapter half of the SCOUT vertical slice."""

from __future__ import annotations

from pathlib import Path

import pytest

from daf.adapters.arxiv import ArxivFetchError, ArxivSourceAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_fetch_parses_single_entry_from_fixture():
    adapter = ArxivSourceAdapter(
        arxiv_ids=("9999.00001",),
        retrieved_at="2026-08-24T00:00:00Z",
        fetch_bytes=lambda url: _fixture_bytes("arxiv_single_entry_v1.xml"),
    )
    documents = adapter.fetch()

    assert len(documents) == 1
    doc = documents[0]
    assert doc.source_name == "arXiv"
    assert doc.source_kind == "paper"
    assert doc.locator == "http://arxiv.org/abs/9999.00001v1"
    assert doc.retrieval_method == "http:arxiv_api_v1"
    assert doc.retrieved_at == "2026-08-24T00:00:00Z"  # caller-supplied, never wall-clock
    assert doc.content.startswith("<entry>")
    assert doc.content.endswith("</entry>")
    assert "A Deterministic Fixture Paper on Test Adhesion" in doc.content


def test_fetch_parses_multiple_entries_from_fixture():
    adapter = ArxivSourceAdapter(
        arxiv_ids=("9999.00001", "9999.00002"),
        retrieved_at="2026-08-24T00:00:00Z",
        fetch_bytes=lambda url: _fixture_bytes("arxiv_two_entries.xml"),
    )
    documents = adapter.fetch()

    assert len(documents) == 2
    assert {d.locator for d in documents} == {
        "http://arxiv.org/abs/9999.00001v1",
        "http://arxiv.org/abs/9999.00002v1",
    }


def test_fetch_empty_ids_returns_empty_tuple_without_a_network_call():
    def _must_not_be_called(url: str) -> bytes:
        raise AssertionError("fetch_bytes must not be called when arxiv_ids is empty")

    adapter = ArxivSourceAdapter(
        arxiv_ids=(), retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_must_not_be_called
    )
    assert adapter.fetch() == ()


def test_fetch_propagates_underlying_network_error_uncaught():
    """Failed acquisition must be visible, never silently swallowed into
    an empty or partial result."""

    def _broken(url: str) -> bytes:
        raise TimeoutError("simulated timeout")

    adapter = ArxivSourceAdapter(
        arxiv_ids=("9999.00001",), retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_broken
    )
    with pytest.raises(TimeoutError):
        adapter.fetch()


def test_fetch_raises_a_clear_error_when_entry_has_no_id():
    adapter = ArxivSourceAdapter(
        arxiv_ids=("9999.00003",),
        retrieved_at="2026-08-24T00:00:00Z",
        fetch_bytes=lambda url: _fixture_bytes("arxiv_entry_missing_id.xml"),
    )
    with pytest.raises(ArxivFetchError):
        adapter.fetch()


@pytest.mark.network
def test_live_fetch_against_the_real_arxiv_api():
    """Demonstrates the adapter against the real, live, public arXiv API
    -- '1706.03762' (Attention Is All You Need) is a permanent, stable
    arXiv id chosen specifically so this test stays meaningful over
    time. Skips cleanly (rather than failing) if this environment has no
    outbound network access, per the task's own guidance that a live
    test should demonstrate integration without making CI depend on it."""
    adapter = ArxivSourceAdapter(arxiv_ids=("1706.03762",), retrieved_at="2026-08-24T00:00:00Z")
    try:
        documents = adapter.fetch()
    except OSError as exc:
        pytest.skip(f"arXiv API unreachable from this environment: {exc}")

    assert len(documents) == 1
    assert documents[0].locator.startswith("http://arxiv.org/abs/1706.03762")
    assert "Attention Is All You Need" in documents[0].content
