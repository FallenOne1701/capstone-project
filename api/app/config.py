from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = API_ROOT / "app" / "corpus" / "sources.yaml"
ALLOWED_SOURCE_DOMAINS: frozenset[str] = frozenset({"groww.in", "amfiindia.com", "sebi.gov.in"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(API_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_model_fast: str = "openai/gpt-oss-20b"
    google_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_s: float = 8.0
    use_llm: bool = True
    groq_rpm: int = 30
    groq_tpm: int = 8000

    # Storage
    database_url: str = f"sqlite:///{(API_ROOT / 'data' / 'app.db').as_posix()}"
    console_password: str = "change-me"

    # Corpus (field names kept identical to M1 so ported modules work unchanged)
    data_raw_dir: Path = API_ROOT / "data" / "corpus" / "raw"
    data_processed_dir: Path = API_ROOT / "data" / "corpus" / "processed"
    data_index_dir: Path = API_ROOT / "data" / "corpus" / "index"
    schemes_path: Path = SOURCES_PATH
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_batch_size: int = 32
    chroma_collection_name: str = "mf_faq_chunks"
    retrieval_top_k: int = 3
    retrieval_top_k_unfiltered: int = 5
    retrieval_rerank_top_n: int = 3
    retrieval_min_similarity: float = 0.58
    chunk_max_section_tokens: int = 400
    chunk_size_tokens: int = 600
    chunk_overlap_tokens: int = 0
    fetch_timeout_seconds: float = 30.0
    fetch_delay_seconds: float = 1.0
    fetch_min_html_bytes: int = 2_000

    max_message_chars: int = 500

    # Voice (Plan 3)
    groq_stt_model: str = "whisper-large-v3-turbo"
    voice_max_bytes: int = 5_000_000
    voice_min_ms: int = 1000
    voice_max_ms: int = 61000
    ticket_worker_inline: bool = False  # tests: process tickets inside the /api/ask request

    # Weekly loop (Plan 2)
    data_outbox_dir: Path = API_ROOT / "data" / "outbox"
    scheduler_enabled: bool = False
    reviews_weeks: int = 8
    reviews_max: int = 3000
    play_package: str = "com.nextbillion.groww"
    repeat_threshold: int = 5
    repeat_days: int = 7
    pulse_doc_id: str = ""

    # Google delivery via MCP Server 1 (stdio)
    mcp_server_dir: Path = API_ROOT / "mcp_server"
    node_command: str = "node"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    pulse_draft_recipient: str = ""
    mcp_timeout_s: float = 60.0

    @property
    def allowed_source_domains(self) -> frozenset[str]:
        return ALLOWED_SOURCE_DOMAINS


def load_schemes(path: Path | None = None) -> dict[str, Any]:
    f = path or SOURCES_PATH
    with f.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not data or not data.get("schemes"):
        raise ValueError(f"Invalid sources registry: {f}")
    return data


def is_allowed_source_url(url: str, domains: frozenset[str] | None = None) -> bool:
    allowed = domains or ALLOWED_SOURCE_DOMAINS
    host = (urlparse(url).hostname or "").lower()
    return bool(host) and any(host == d or host.endswith("." + d) for d in allowed)


@lru_cache
def get_settings() -> Settings:
    return Settings()
