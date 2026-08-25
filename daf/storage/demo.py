"""Two-subcommand CLI demonstrating durable persistence across a REAL
process restart (two separate `python -m` invocations, sharing nothing
but the on-disk storage directory):

    python -m daf.storage.demo acquire <storage_dir> <arxiv_id> [<arxiv_id> ...]
    python -m daf.storage.demo retrieve <storage_dir>

`acquire` runs the unmodified SCOUT vertical slice
(daf.adapters.arxiv.ArxivSourceAdapter + daf.extractors.arxiv.ArxivExtractor
+ scout.pipeline.run_scout) against a `DurablePool`, then exits -- nothing
survives in memory past that point. `retrieve`, run as a brand new
process afterward, reconstructs a pool purely from `storage_dir` and
prints back the same artifact/version identities, content hash, raw
bytes, and acquisition metadata, so the two invocations' output can be
diffed to prove restart persistence end to end.
"""

from __future__ import annotations

import sys
from pathlib import Path

import daf  # noqa: F401  -- vendored repo onto sys.path
from evidence.identity import content_hash
from scout.pipeline import run_scout

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.storage.artifact_store import ArtifactStore
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore


def _acquire(storage_dir: str, arxiv_ids: list) -> None:
    store = FilesystemEvidenceStore(Path(storage_dir))
    pool = DurablePool(store)
    adapter = ArxivSourceAdapter(arxiv_ids=tuple(arxiv_ids), retrieved_at="2026-08-24T00:00:00Z")
    findings, failures = run_scout(adapter, ArxivExtractor(), pool)

    if failures:
        print(f"{len(failures)} admission failure(s): {failures}")

    artifact_store = ArtifactStore(store)
    for finding in findings:
        document = finding.document
        record = finding.record
        artifact_id = artifact_store.put(document, record)
        print("ACQUIRED")
        print(f"  artifact_id   = {artifact_id}")
        print(f"  version_id    = {document.id}")
        print(f"  content_hash  = {content_hash(document.raw_content)}")
        print(f"  retrieval_method = {document.retrieval_method}")
        print(f"  retrieved_at     = {document.retrieved_at}")
        print(f"  raw_bytes_len    = {len(document.raw_content)}")
    print(f"pool.fingerprint() = {pool.fingerprint()}")


def _retrieve(storage_dir: str) -> None:
    store = FilesystemEvidenceStore(Path(storage_dir))
    pool = DurablePool.restore(store)  # a BRAND NEW pool object; nothing shared with `acquire`
    artifact_store = ArtifactStore(store)

    for document in store.all_documents():
        record = next(r for r in store.all_records() if r.document_id == document.id)
        artifact_id = artifact_store.artifact_id(document.source_id, record.locator)
        print("RETRIEVED")
        print(f"  artifact_id   = {artifact_id}")
        print(f"  version_id    = {document.id}")
        print(f"  content_hash  = {content_hash(document.raw_content)}")
        print(f"  retrieval_method = {document.retrieval_method}")
        print(f"  retrieved_at     = {document.retrieved_at}")
        print(f"  raw_bytes_len    = {len(document.raw_content)}")
        print(f"  versions of this artifact = {artifact_store.list_versions(artifact_id)}")
    print(f"pool.fingerprint() = {pool.fingerprint()}")


def _main() -> None:  # pragma: no cover -- manual/CLI demonstration only
    if len(sys.argv) < 3 or sys.argv[1] not in ("acquire", "retrieve"):
        print(__doc__)
        raise SystemExit(2)

    command, storage_dir, *rest = sys.argv[1:]
    if command == "acquire":
        _acquire(storage_dir, rest or ["1706.03762"])
    else:
        _retrieve(storage_dir)


if __name__ == "__main__":  # pragma: no cover
    _main()
