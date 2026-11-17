"""Shared helper: build a retriever over the fixture corpus in a temp dir (one per module)."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


def build_fixture_retriever(root: Path):
    from app.corpus.chunker import chunk_scheme_pages
    from app.corpus.indexer import build_index
    from app.corpus.parser import parse_scheme_pages
    from app.corpus.retriever import Retriever
    parse_scheme_pages(raw_dir=FIXTURES, processed_dir=root / "p")
    chunk_scheme_pages(processed_dir=root / "p")
    build_index(processed_dir=root / "p", index_dir=root / "i")
    return Retriever(index_dir=root / "i")
