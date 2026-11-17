from pathlib import Path

import pytest

from app.corpus.chunker import chunk_scheme_pages
from app.corpus.embedder import EmbeddingService
from app.corpus.indexer import build_index
from app.corpus.parser import parse_scheme_pages
from app.corpus.retriever import Retriever

FIXTURES = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture(scope="module")
def built_index(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    processed, index = root / "processed", root / "index"
    assert parse_scheme_pages(raw_dir=FIXTURES, processed_dir=processed).ok_count == 15
    chunk_scheme_pages(processed_dir=processed)
    report = build_index(processed_dir=processed, index_dir=index, embedder=EmbeddingService())
    assert report.all_ok
    return index


def test_embedder_dimension():
    assert EmbeddingService().dimension == 384


def test_retrieves_mid_cap_exit_load(built_index):
    r = Retriever(index_dir=built_index).retrieve("What is the exit load of HDFC Mid Cap Fund?")
    assert r.status == "ok"
    assert r.winner.fact_key == "exit_load"
    assert r.winner.source_url == "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth"


def test_hinglish_query_still_resolves(built_index):
    r = Retriever(index_dir=built_index).retrieve("mid cap ka exit load kitna hai")
    assert r.status == "ok" and r.winner.fact_key == "exit_load"


def test_ambiguous_scheme(built_index):
    r = Retriever(index_dir=built_index).retrieve("exit load of mid cap and small cap")
    assert r.status == "ambiguous_scheme"
