"""Rate limits on the public question, preview and voice routes (Plan 3b Task 4)."""

from app.config import get_settings
from app.guard import ratelimit
from app.guard.ratelimit import RATE_MSG, RateLimiter

Q = {"text": "What is the exit load of HDFC Mid Cap Fund?"}


def test_eleventh_question_in_ten_minutes_is_429(client):
    for _ in range(10):
        assert client.post("/api/ask", json=Q).status_code == 200
    r = client.post("/api/ask", json=Q)
    assert r.status_code == 429 and r.json()["detail"] == RATE_MSG


def test_window_slides():
    now = [0.0]
    lim = RateLimiter(2, 600, clock=lambda: now[0])
    assert lim.hit("a") and lim.hit("a") and not lim.hit("a")
    assert lim.hit("b")                      # other clients are separate
    now[0] = 601
    assert lim.hit("a")


def test_forwarded_for_used_only_when_trusted(client, monkeypatch):
    def burst(ip):
        return [client.post("/api/ask/preview", json=Q, headers={"X-Forwarded-For": f"10.0.0.1, {ip}"}).status_code
                for _ in range(16)]
    # untrusted: both "visitors" are the same socket client, sharing one limit of 30
    assert 429 not in burst("1.1.1.1") and 429 in burst("2.2.2.2")
    ratelimit.reset_limits()
    monkeypatch.setattr(get_settings(), "trust_proxy", True)
    assert 429 not in burst("3.3.3.3") and 429 not in burst("4.4.4.4")


def test_daily_cap_applies_across_clients(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "_ask_daily", RateLimiter(3, 86_400))
    monkeypatch.setattr(get_settings(), "trust_proxy", True)
    codes = [client.post("/api/ask", json=Q, headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(4)]
    assert codes == [200, 200, 200, 429]


def test_voice_limit_three_per_minute(client):
    files = {"audio": ("q.webm", b"\x1a" * 100, "audio/webm")}
    codes = [client.post("/api/voice/transcribe", files=files, data={"duration_ms": "2500"}).status_code
             for _ in range(4)]
    assert codes[:3] == [503, 503, 503] and codes[3] == 429   # USE_LLM=0 → 503 until the limit is hit


def test_spoofed_forwarded_for_cannot_dodge_the_limit(client, monkeypatch):
    # the proxy appends the real client as the LAST hop; anything before it was typed by the client
    monkeypatch.setattr(get_settings(), "trust_proxy", True)
    codes = [client.post("/api/ask/preview", json=Q,
                         headers={"X-Forwarded-For": f"6.6.6.{i}, 203.0.113.7"}).status_code for i in range(31)]
    assert codes[-1] == 429


def test_preview_and_voice_have_server_wide_caps(monkeypatch):
    assert ratelimit._preview_daily.limit > 0 and ratelimit._voice_daily.limit > 0


def test_idle_keys_are_dropped():
    now = [0.0]
    lim = RateLimiter(2, 10, clock=lambda: now[0])
    for i in range(50):
        lim.hit(f"k{i}")
    now[0] = 11
    lim.hit("fresh")
    assert len(lim._hits) == 1
