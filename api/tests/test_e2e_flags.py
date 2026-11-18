"""Settings the isolated e2e stack relies on (Plan 3 Task 6)."""

import threading

from app import main
from app.config import get_settings


def test_corpus_bootstrap_can_be_switched_off(db_session, monkeypatch):
    # The e2e API shares the real corpus/index folders; it must never fetch pages or rebuild the index.
    monkeypatch.setattr(get_settings(), "corpus_bootstrap", False)
    started = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))
    main.create_app(init_corpus=True)
    assert not any(getattr(t, "_target", None) is main._bootstrap_corpus for t in started)
