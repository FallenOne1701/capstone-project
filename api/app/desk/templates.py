REFUSAL_LINK = "https://groww.in/p/mutual-funds"

ADVICE_REFUSAL = (
    "We share facts only and can't advise on buying, selling or holding any fund. "
    "Each scheme's official facts are on its Groww page."
)
PERFORMANCE_REFUSAL = (
    "We can't share past or projected figures for any fund. "
    "Please refer to the scheme's official page on Groww for its published information."
)
ACCOUNT_REPLY = (
    "We can't see or change individual accounts from here. "
    "Please raise this through Help & Support in the Groww app so the team can check your account."
)


def not_covered_reply(searched: list[str]) -> str:
    where = ", ".join(searched[:6]) if searched else "our HDFC scheme pages"
    return f"Our official sources don't cover this question. Searched: {where}."


def covered_reply(fact: str, citation: str, last_checked: str) -> str:
    fact = fact.strip().rstrip(".") + "."
    return f"{fact} Source: {citation} Last checked: {last_checked}."
