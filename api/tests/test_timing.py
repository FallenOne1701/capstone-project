import asyncio
import logging

import pytest

from app.tickets.service import create_ticket, process_ticket
from tests.conftest_corpus import build_fixture_retriever

QUESTION = "my pan is ABCDE1234F, what is the expense ratio of HDFC Mid Cap Fund?"


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    return build_fixture_retriever(tmp_path_factory.mktemp("tm"))


def test_step_logs_name_and_duration_only(db_session, retriever, caplog):
    caplog.set_level(logging.INFO, logger="app.desk.timing")
    t, _ = asyncio.run(create_ticket(db_session, QUESTION))
    asyncio.run(process_ticket(db_session, t.id, retriever=retriever))
    lines = [r.getMessage() for r in caplog.records if r.name == "app.desk.timing"]
    for step in ("classify", "canonical", "desk", "total"):
        assert any(f"step={step} " in ln and "ms=" in ln and f"ticket={t.id}" in ln for ln in lines), (step, lines)
    for ln in lines:
        assert "ABCDE1234F" not in ln and "[PAN]" not in ln and "expense ratio" not in ln


def test_startup_warms_the_search_in_the_background(monkeypatch):
    """The first question after a deploy must not pay the ~5 s embedding-model load."""
    import threading

    from app import main
    started = []
    monkeypatch.setattr(main, "_warm_up", lambda: started.append(threading.current_thread().name))
    monkeypatch.setattr("app.scheduler.start_scheduler", lambda: None)
    monkeypatch.setattr(main.get_settings(), "corpus_bootstrap", False)
    main.create_app(init_corpus=True)
    for th in threading.enumerate():
        if th.name == "warm-up":
            th.join(5)
    assert started == ["warm-up"]


def test_warm_up_loads_the_model_and_a_query(monkeypatch):
    from app import main
    seen = []

    class FakeEmbedder:
        def embed_query(self, text):
            seen.append(text)
            return [0.0]

    monkeypatch.setattr("app.corpus.embedder.get_embedding_service", lambda: FakeEmbedder())
    main._warm_up()
    assert seen == ["warm up"]


def test_warm_up_never_raises(monkeypatch):
    from app import main

    def boom():
        raise RuntimeError("no model")

    monkeypatch.setattr("app.corpus.embedder.get_embedding_service", boom)
    main._warm_up()   # logs and returns; the app keeps starting


def test_warm_up_retries_once_after_an_import_race(monkeypatch):
    """On Railway the first try hit an ImportError at startup; a second try must still warm the model."""
    from app import main
    seen, tries = [], []

    class FakeEmbedder:
        def embed_query(self, text):
            seen.append(text)
            return [0.0]

    def flaky():
        tries.append(1)
        if len(tries) == 1:
            raise ImportError("cannot import name 'x' from partially initialized module")
        return FakeEmbedder()

    monkeypatch.setattr("app.corpus.embedder.get_embedding_service", flaky)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    main._warm_up()
    assert seen == ["warm up"] and len(tries) == 2


def test_warm_up_failure_logs_the_reason(monkeypatch, caplog):
    from app import main

    def boom():
        raise ImportError("cannot import name 'TextEmbedding'")

    monkeypatch.setattr("app.corpus.embedder.get_embedding_service", boom)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    main._warm_up()
    assert any("cannot import name 'TextEmbedding'" in r.getMessage() for r in caplog.records)


def test_model_loads_once_when_two_threads_ask_at_the_same_time(monkeypatch):
    """Warm-up and the first question must not both load the ONNX model (double memory, slower first answer)."""
    import sys
    import threading
    import time as _t
    import types

    from app.corpus.embedder import EmbeddingService
    built = []

    class SlowModel:
        def __init__(self, model_name):
            built.append(model_name)
            _t.sleep(0.3)

        def embed(self, texts, batch_size=None):
            return [[0.0] for _ in texts]

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=SlowModel))
    svc = EmbeddingService()
    threads = [threading.Thread(target=lambda: svc.embed_query("q")) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(5)
    assert len(built) == 1
