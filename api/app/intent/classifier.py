"""Rules-first intent classification; the fast LLM only resolves the gray zone."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from app.corpus.query_parser import parse_query
from app.llm.client import complete_json

Intent = Literal["fee_question", "fund_fact", "how_to_process", "advice_request",
                 "performance_request", "account_issue", "out_of_scope"]
INTENTS: tuple[str, ...] = Intent.__args__  # type: ignore[attr-defined]


class IntentResult(BaseModel):
    intent: Intent
    scheme_ids: list[str]
    fact_key: str | None
    language: Literal["en", "hi", "hinglish"]
    confidence: Literal["rule", "llm", "default"]


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile(r"(?i)\b(?:" + "|".join(parts) + r")\b")


_ADVICE = _rx(r"should i", r"shall i", r"is (?:it|this|the \w+(?: \w+)?(?: fund)?) (?:good|safe|worth|right|better)",
              r"good to (?:invest|buy)", r"worth (?:it|investing)", r"which (?:fund|scheme) (?:is|should)",
              r"recommend", r"better (?:fund|option|to)", r"buy", r"sell", r"switch (?:to|from)",
              r"lena chahiye", r"le lu", r"lu kya", r"kharid\w*", r"bech\w*", r"accha hai", r"sahi hai",
              r"invest karu", r"stay invested", r"exit now")
_ADVICE_MORE = _rx(r"good idea", r"is (?:it|this) worth", r"worth it", r"best (?:\w+ )?(?:funds?|schemes?|banks?|cards?|fds?|loans?|plans?|investments?|options?)", r"what should i (?:buy|invest|do)",
                   r"where (?:should|can) i (?:invest|put)", r"suggest\w*")
_OFF_TOPIC = _rx(r"bank (?:account|rate)s?", r"savings? account", r"current account", r"fixed deposits?", r"fds?",
                 r"(?:personal|home|car|gold|education|business) loans?", r"loans?", r"emi", r"credit cards?",
                 r"debit cards?", r"insurance", r"income tax return", r"itr", r"tax filing", r"interest rates?",
                 r"stocks?", r"shares", r"crypto\w*", r"bitcoin", r"upi", r"neft", r"imps")
# Words that make a bank/UPI/ITR mention a mutual-fund question ("redemption not credited to my bank account").
_MF_CONTEXT = _rx(r"sip", r"redemptions?", r"redeem\w*", r"units?", r"mutual funds?", r"folio", r"nav", r"statements?",
                  r"capital gains?", r"elss", r"amc", r"kyc", r"mandate", r"autopay")
_PERF = _rx(r"returns?", r"cagr", r"xirr", r"performance", r"how much (?:will|did|can) (?:i|it) (?:earn|make|get|grow|gain)",
            r"kitna return", r"profit", r"nav (?:prediction|forecast|tomorrow|target)", r"outperform\w*", r"beat the market")
_ACCOUNT = _rx(r"not credited", r"debited", r"refund", r"stuck", r"failed", r"pending since",
               r"my (?:order|sip|money|units|payment|redemption|kyc)\w* (?:is|was|has|hasn'?t|not|didn'?t|got)",
               r"mera (?:paisa|sip|account|order)", r"paisa (?:nahi|nhi|not)", r"kyc (?:rejected|failed|pending)", r"not received", r"didn'?t receive")
_FEE = _rx(r"exit[\s-]?load", r"expense ratio", r"ter", r"charges?", r"fees?", r"stamp duty", r"brokerage", r"commission",
           r"redemption load", r"kitna (?:charge|kat\w*)", r"kya charge")
_HOWTO = _rx(r"how (?:do|to|can|long|does)", r"can i (?:pay|use|set up|start|stop|change|link)", r"kaise", r"steps?", r"process", r"procedure", r"redeem", r"withdraw\w*",
             r"start (?:a |an )?sip", r"stop (?:my |a )?sip", r"cancel (?:my |a )?sip", r"kyc", r"nominee", r"statement")
_HOWTO_TXN = _rx(r"how (?:do|to|can|should) (?:i |we |one )?(?:buy|sell|redeem|invest|purchase|switch)",
                 r"(?:buy|sell|redeem|invest) kaise",
                 r"(?:process|procedure|steps?|way) (?:to|for) (?:buy|sell|redeem|invest|purchase|switch)\w*",
                 r"can i (?:buy|sell|redeem|switch|withdraw|purchase)")
_FACT_KEYS_FEE = {"exit_load", "expense_ratio"}
_HINGLISH = _rx(r"kya", r"hai", r"kaise", r"kitna", r"mera", r"mujhe", r"nahi", r"nhi", r"karu", r"kare", r"paisa", r"ka", r"ki", r"ke", r"chahiye")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def detect_language(text: str) -> str:
    if _DEVANAGARI.search(text):
        return "hi"
    return "hinglish" if len(_HINGLISH.findall(text)) >= 2 else "en"


_LLM_SYSTEM = (
    "Classify a mutual-fund support question into exactly one intent. Return JSON {\"intent\": ...}. "
    f"Allowed: {list(INTENTS)}. advice_request = asks whether to buy/sell/hold/switch or if a fund is good. "
    "performance_request = asks for returns, CAGR, NAV forecasts. account_issue = a problem with the user's own "
    "order, money, SIP or KYC. fee_question = exit load, expense ratio, charges. fund_fact = minimum SIP, benchmark, "
    "riskometer, objective, fund manager. how_to_process = how to do something on the platform. Otherwise out_of_scope. "
    "The text may be Hindi or Hinglish. Tokens like [PAN] are redacted PII."
)


async def classify_intent(redacted_text: str) -> IntentResult:
    text = redacted_text.strip()
    hints = parse_query(text)
    base = dict(scheme_ids=list(hints.scheme_ids), fact_key=hints.fact_key, language=detect_language(text))

    def mk(intent: str, conf: str = "rule") -> IntentResult:
        return IntentResult(intent=intent, confidence=conf, **base)

    # other products first: "can I buy bitcoin on Groww?" is out of scope, not a how-to (eval run 1, n05)
    if _OFF_TOPIC.search(text) and not hints.scheme_ids and not _MF_CONTEXT.search(text):
        return mk("out_of_scope")   # banking, loans, cards, stocks, crypto…: not something this desk answers
    if _HOWTO_TXN.search(text) and not re.search(r"(?i)\bshould i\b", text):
        return mk("how_to_process")
    if _ADVICE.search(text) or _ADVICE_MORE.search(text):
        return mk("advice_request")
    if _PERF.search(text):
        return mk("performance_request")
    if _ACCOUNT.search(text):
        return mk("account_issue")
    if _FEE.search(text) or hints.fact_key in _FACT_KEYS_FEE:
        return mk("fee_question")
    if _HOWTO.search(text):
        return mk("how_to_process")
    if hints.fact_key:
        return mk("fund_fact")
    data = await complete_json(_LLM_SYSTEM, text, fast=True)
    if data and data.get("intent") in INTENTS:
        return mk(data["intent"], "llm")
    if hints.scheme_ids:   # names an HDFC fund: in scope even when the LLM is unavailable
        return mk("fund_fact", "default")
    return mk("out_of_scope", "default")
