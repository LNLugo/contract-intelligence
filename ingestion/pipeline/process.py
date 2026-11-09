"""One entry point for one document. Both the batch script and the Function call this."""
import hashlib
import time
from dataclasses import asdict, dataclass

from . import chunk as chunking
from . import embed, extract, index
from .config import SETTINGS as S


def document_id(pdf: bytes) -> str:
    """Content hash: the same file always gets the same ID, whatever it is named."""
    return hashlib.sha256(pdf).hexdigest()[:16]


@dataclass
class Result:
    doc_id: str
    file_name: str
    pages: int
    extraction_cached: bool
    chunks: int
    embed_tokens: int
    max_chunk_tokens: int
    seconds: float


def process(pdf: bytes, file_name: str, meta: dict) -> Result:
    t0 = time.time()
    doc_id = document_id(pdf)
    layout, cached = extract.extract(doc_id, pdf, file_name)
    chunks = chunking.chunk(layout, S.chunk_tokens, S.overlap_tokens)
    if not chunks:
        raise ValueError(f"No text extracted from {file_name}")
    vectors, used = embed.embed([chunking.embedding_text(c, file_name) for c in chunks])
    meta = {**meta, "file_name": file_name}
    meta.setdefault("vendor_id", "V" + doc_id[:6].upper())
    count = index.replace_document(doc_id, chunks, vectors, meta)
    return Result(doc_id, file_name, len(layout.get("pages", [])), cached, count, used,
                  max(c.tokens for c in chunks), round(time.time() - t0, 1))


def as_dict(r: Result) -> dict:
    return asdict(r)
