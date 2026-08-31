import re

IMPACT_KEYWORDS = [
    r"\bimpact\b", r"\bbreak\b", r"\bbreaks\b", r"\bwho calls\b",
    r"\bcallers?\b", r"\bcallees?\b", r"\bdepends? on\b", r"\bwhat happens if\b",
]

FLOW_KEYWORDS = [
    r"\bflow\b", r"\barchitecture\b", r"\bstructure\b", r"\boverview\b",
]


def classify_intent(question: str) -> str:
    """
    Returns one of "impact", "flow", or "semantic" based on
    simple keyword matching, per the plan's §7 routing table.
    """
    q = question.lower()

    for pattern in IMPACT_KEYWORDS:
        if re.search(pattern, q):
            return "impact"

    for pattern in FLOW_KEYWORDS:
        if re.search(pattern, q):
            return "flow"

    return "semantic"