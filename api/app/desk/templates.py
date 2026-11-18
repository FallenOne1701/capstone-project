REFUSAL_LINK = "https://groww.in/p/mutual-funds"

ADVICE_REFUSAL = (
    "We share facts only and can't advise on buying, selling or holding any fund. "
    "Each scheme's official facts are on its Groww page."
)
PERFORMANCE_REFUSAL = (
    "We can't share past or projected figures for any fund. "
    "Please refer to the scheme's official page on Groww for its published information."
)
OUT_OF_SCOPE_REPLY = (
    "We only answer factual questions about HDFC mutual funds on Groww. "
    "We can't help with banking, loans, cards, insurance or other products, and we never give advice."
)
ACCOUNT_REPLY = (
    "We can't see or change individual accounts from here. "
    "Please raise this through Help & Support in the Groww app so the team can check your account."
)


FALLBACK_GENERIC_NAME = "HDFC mutual funds"
FALLBACK_GENERIC_URL = REFUSAL_LINK


def fallback_reply(scheme_id: str | None) -> tuple[str, str]:
    """Fixed safe reply when the checks block a draft or the desk fails: no facts. Returns (reply, page url for the record)."""
    from app.config import load_schemes
    s = next((x for x in load_schemes()["schemes"] if x["scheme_id"] == scheme_id), None) if scheme_id else None
    name = s["scheme_name"].split(" Fund")[0] if s else FALLBACK_GENERIC_NAME
    url = s["url"] if s else FALLBACK_GENERIC_URL
    # no link in the text: the reviewer allows links only next to a checked fact
    return (f"We couldn't confirm an answer to this from official sources. "
            f"Please see the official {name} page on Groww for its published details."), url


def not_covered_reply(searched: list[str]) -> str:
    where = ", ".join(searched[:6]) if searched else "our HDFC scheme pages"
    return f"Our official sources don't cover this question. Searched: {where}."


def covered_reply(fact: str, citation: str, last_checked: str) -> str:
    fact = fact.strip().rstrip(".") + "."
    return f"{fact} Source: {citation} Last checked: {last_checked}."
