"""BlobStore: the smallest content-addressed raw-content store,
introduced in Phase K to eliminate the raw-content duplication Phase J
found (`Document.raw_content` and `Record.raw_content` are both
populated from the identical string by vendored
`scout.pipeline.run_scout` -- see that module's own
`make_document`/`make_record` calls -- and, until now,
`daf.storage.serialization`'s on-disk JSON wrote that same string
twice, once per category).

BlobStore stores content. Nothing else:

    put(content_hash, raw_content) -> None   -- idempotent
    get(content_hash) -> str                 -- raises BlobNotFoundError if absent
    has(content_hash) -> bool

`raw_content` is `str`, not `bytes` -- matching every acquired artifact
in this codebase (`RawDocument.content`, `Document.raw_content`,
`Record.raw_content` are all `str`; every real adapter -- arXiv, EDGAR,
USGS, NOAA -- decodes its HTTP response to text before constructing a
`RawDocument`) and matching `evidence.identity.content_hash`'s own
established call convention (`content_hash(document.raw_content)` is
already how `ArtifactStore.content_hash_of` computes this same hash).
Storing `str` here, not `bytes`, means BlobStore's content_hash is
byte-for-byte the same hash `make_document`/`make_record` already
compute -- not a re-encoding that could silently drift from it.

It has no concept of Document, Record, artifact identity, version
identity, acquisition state, or execution provenance -- those all stay
exactly where Phase A-J put them (`evidence.types`, `daf.orchestration`,
`daf.catalog`). This module only ever sees a hash and a string.

One file per unique content hash, in a flat directory -- the same
atomic-write discipline `FilesystemEvidenceStore` already established
(temp file + `os.replace`, atomic on POSIX): a crash mid-write can never
leave a half-written blob where a reader would see it.

Corruption detection: `get()` re-verifies the read content hashes to the
requested key before returning it, independent of and in addition to
the existing `Document`/`Record` identity re-verification in
`daf.storage.serialization` (defense in depth -- a caller that reads a
blob directly, without ever reconstructing a Document, still gets the
same guarantee Phase B established: corrupted-on-disk content is
detected on read, never silently trusted).
"""

from __future__ import annotations

from pathlib import Path

from evidence.identity import content_hash as _content_hash


class BlobNotFoundError(KeyError):
    """Raised when `get`/a required `has` check names no stored blob."""


class BlobCorruptionError(RuntimeError):
    """Raised when a blob read back from disk does not hash to the key
    it was stored under -- on-disk tampering or corruption, detected the
    same way Phase B detects it for Document/Record: by re-deriving the
    content-addressed identity from the content actually read, never by
    trusting the filename alone."""


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, content_hash: str) -> Path:
        return self.root / f"{content_hash}.blob"

    def has(self, content_hash: str) -> bool:
        return self._path(content_hash).exists()

    def put(self, content_hash: str, raw_content: str) -> None:
        """Idempotent: a matching existing blob is left untouched (the
        same "no-op on a legitimate duplicate" discipline
        `FilesystemEvidenceStore._write` already established) -- this
        function never compares the incoming content to what's on disk,
        since two callers computing the same content_hash from the
        content they hold can only disagree if one of them is wrong
        about content_hash in the first place, which is a caller bug
        this store cannot detect any better by re-comparing than by
        trusting its own name-your-own-key contract."""
        final_path = self._path(content_hash)
        if final_path.exists():
            return
        tmp_path = self.root / f"{content_hash}.blob.tmp"
        tmp_path.write_text(raw_content, encoding="utf-8")
        tmp_path.replace(final_path)  # atomic on POSIX -- readers never see a partial file

    def get(self, content_hash: str) -> str:
        path = self._path(content_hash)
        if not path.exists():
            raise BlobNotFoundError(f"no blob stored under content_hash {content_hash!r}")
        raw_content = path.read_text(encoding="utf-8")
        actual_hash = _content_hash(raw_content)
        if actual_hash != content_hash:
            raise BlobCorruptionError(
                f"blob stored under {content_hash!r} re-hashes to {actual_hash!r} -- "
                "stored content no longer matches its own content-addressed identity"
            )
        return raw_content
