def corpus_status() -> dict:
    try:
        from app.corpus.indexer import collection_count
        n = collection_count()
    except Exception:  # noqa: BLE001
        n = 0
    return {"vectors": n, "ready": n > 0}
