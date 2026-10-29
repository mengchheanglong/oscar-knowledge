"""Versioned starter ontology. Topic similarity never implies author agreement."""

import re

VERSION = "topics-v1"
# slug, label, domain, aliases. Labels/aliases are retrieval hints, not claims.
TOPICS = [
    (
        "customer-discovery",
        "Customer discovery",
        "Business",
        ["customer discovery", "customer interviews", "unmet needs", "customer problem"],
    ),
    (
        "value-proposition",
        "Customer value",
        "Business",
        ["value proposition", "customer value", "customer benefit", "jobs to be done"],
    ),
    (
        "positioning",
        "Positioning",
        "Business",
        ["positioning", "differentiation", "competitive position"],
    ),
    (
        "segmentation",
        "Segmentation",
        "Business",
        ["market segmentation", "customer segment", "beachhead"],
    ),
    (
        "experiments",
        "Experiments and validation",
        "Methods",
        ["hypothesis", "hypotheses", "experiments", "validated learning"],
    ),
    (
        "measurement",
        "Measurement",
        "Methods",
        [
            "actionable metrics",
            "vanity metrics",
            "performance measurement",
            "key performance indicator",
        ],
    ),
    ("pricing", "Pricing", "Business", ["pricing", "willingness to pay", "price discrimination"]),
    (
        "unit-economics",
        "Unit economics",
        "Business",
        ["contribution margin", "unit economics", "customer acquisition cost", "lifetime value"],
    ),
    (
        "networks",
        "Marketplaces and networks",
        "Business",
        ["two-sided market", "marketplace", "network effects", "atomic network"],
    ),
    (
        "growth",
        "Growth and retention",
        "Business",
        ["customer acquisition", "retention", "viral growth", "repeat purchase"],
    ),
    (
        "operations",
        "Operations",
        "Management",
        ["bottleneck", "throughput", "inventory management", "process improvement"],
    ),
    (
        "management",
        "Management and delegation",
        "Management",
        ["delegation", "managerial leverage", "task-relevant maturity", "management by objectives"],
    ),
    (
        "decisions",
        "Decisions",
        "Methods",
        ["decision making", "decision-making", "trade-off", "opportunity cost"],
    ),
    (
        "biases",
        "Cognitive biases",
        "Psychology",
        ["confirmation bias", "cognitive bias", "loss aversion", "availability heuristic"],
    ),
    (
        "systems",
        "Systems and feedback",
        "Systems",
        ["feedback loop", "reinforcing loop", "balancing loop", "systems thinking"],
    ),
    ("incentives", "Incentives", "Society", ["incentives", "principal-agent", "moral hazard"]),
    ("ethics", "Ethics", "Society", ["business ethics", "ethical", "moral responsibility"]),
    (
        "culture",
        "Culture and norms",
        "Society",
        ["organizational culture", "social norms", "collective behavior"],
    ),
    (
        "institutions",
        "Institutions and governance",
        "Society",
        ["institutions", "governance", "rule of law"],
    ),
    ("power", "Power and authority", "Society", ["political power", "authority", "legitimacy"]),
    (
        "markets",
        "Markets and economics",
        "Economics",
        ["supply and demand", "market failure", "externalities"],
    ),
    (
        "finance",
        "Financial statements and cash",
        "Finance",
        ["cash flow", "balance sheet", "income statement"],
    ),
    (
        "risk",
        "Risk and uncertainty",
        "Methods",
        ["risk management", "expected value", "probability distribution"],
    ),
    (
        "statistics",
        "Statistics",
        "Methods",
        ["regression", "statistical significance", "confidence interval"],
    ),
    (
        "mathematics",
        "Mathematics",
        "Science",
        ["linear algebra", "calculus", "differential equation"],
    ),
    (
        "software",
        "Software and algorithms",
        "Engineering",
        ["algorithm", "software engineering", "computational complexity"],
    ),
    (
        "ai",
        "Artificial intelligence",
        "Engineering",
        ["machine learning", "neural network", "artificial intelligence"],
    ),
    (
        "communication",
        "Communication",
        "Communication",
        ["persuasion", "negotiation", "active listening"],
    ),
    ("leadership", "Leadership", "Management", ["leadership", "motivation", "team performance"]),
    (
        "psychology",
        "Learning and cognition",
        "Psychology",
        ["working memory", "cognition", "conditioning", "psychology"],
    ),
    (
        "physics",
        "Physics",
        "Science",
        ["Newtonian mechanics", "quantum mechanics", "electromagnetism", "classical physics"],
    ),
    (
        "engineering",
        "Engineering systems",
        "Engineering",
        ["control system", "thermodynamics", "reliability engineering"],
    ),
]

RELATED = [
    ("customer-discovery", "value-proposition"),
    ("value-proposition", "positioning"),
    ("segmentation", "customer-discovery"),
    ("customer-discovery", "experiments"),
    ("experiments", "measurement"),
    ("measurement", "statistics"),
    ("pricing", "unit-economics"),
    ("pricing", "value-proposition"),
    ("unit-economics", "finance"),
    ("networks", "growth"),
    ("growth", "measurement"),
    ("operations", "management"),
    ("management", "leadership"),
    ("decisions", "biases"),
    ("decisions", "risk"),
    ("risk", "statistics"),
    ("systems", "incentives"),
    ("incentives", "institutions"),
    ("institutions", "power"),
    ("culture", "ethics"),
    ("communication", "psychology"),
    ("ai", "statistics"),
    ("software", "ai"),
    ("engineering", "systems"),
    ("physics", "mathematics"),
]
BY_ID = {t[0]: t for t in TOPICS}
PATTERNS = {
    slug: re.compile(
        r"\b(?:" + "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in aliases) + r")\b", re.I
    )
    for slug, _, _, aliases in TOPICS
}


def mentions(text):
    """Exact source offsets. A mention is not support or endorsement."""
    if len(text.strip()) < 80:
        return []
    first = text[:180].lower()
    if re.match(r"\s*(references|bibliography|table of contents|index)\s*(\n|$)", first):
        return []
    # Fast literal rejection avoids dozens of regex scans over every page.
    # The regex still decides membership and original offsets. Turkish I is
    # special under re.IGNORECASE, so retain the full scan for those characters.
    normalized = " ".join(text.casefold().split())
    full_scan = "İ" in text or "ı" in text
    found = []
    for topic, pattern in PATTERNS.items():
        if not full_scan and not any(alias.casefold() in normalized for alias in BY_ID[topic][3]):
            continue
        match = pattern.search(text)
        if match:
            start, end = max(0, match.start() - 100), min(len(text), match.end() + 140)
            found.append((topic, start, end, text[start:end]))
    return found
