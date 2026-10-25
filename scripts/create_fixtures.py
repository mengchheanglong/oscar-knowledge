"""Rebuild original CC0 synthetic fixtures. Never downloads university content."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ITEMS = [
    (
        "pricing",
        "Marketing",
        "Pricing experiments",
        "Subscription pricing uses customer willingness to pay, segment needs and contribution margin. Rentify can test a basic and premium subscription with clear limits. Measure conversion, retention and support costs before expanding a pricing experiment.",
    ),
    (
        "strategy",
        "Strategy",
        "Competitive positioning",
        "Competitive positioning defines a target customer and a distinct value proposition. A defensible advantage needs activities that rivals cannot easily copy. Compare alternatives and switching costs before selecting a niche.",
    ),
    (
        "entrepreneurship",
        "Entrepreneurship",
        "Network effects",
        "Network effects arise when the value to each customer increases as participation grows. A marketplace startup must solve the cold start problem on both sides. Track activation and repeat transactions instead of counting registrations alone.",
    ),
    (
        "economics",
        "Economics",
        "Elasticity and demand",
        "Price elasticity measures the percentage change in demand divided by the percentage change in price. Demand experiments help distinguish elastic segments from inelastic segments. Opportunity cost includes the best alternative use of scarce resources.",
    ),
    (
        "finance",
        "Corporate Finance",
        "Cash runway and valuation",
        "Cash runway equals available cash divided by net monthly cash burn. Discounted cash flow values future cash flows using a discount rate that reflects risk. Contribution margin is revenue less variable costs; acquisition spending should be assessed against customer lifetime value.",
    ),
    (
        "decisions",
        "Decision Science",
        "Experiments and uncertainty",
        "Decision trees compare alternatives under uncertain outcomes using probabilities and expected values. Sensitivity analysis checks whether a decision changes under plausible inputs. A controlled experiment needs a baseline and a clearly measured outcome.",
    ),
]
QUERIES = [
    ("pricing", "subscription pricing"),
    ("pricing", "willingness to pay"),
    ("pricing", "conversion retention support costs"),
    ("strategy", "competitive positioning"),
    ("strategy", "defensible advantage"),
    ("strategy", "switching costs"),
    ("entrepreneurship", "network effects"),
    ("entrepreneurship", "cold start"),
    ("entrepreneurship", "marketplace transactions"),
    ("economics", "price elasticity"),
    ("economics", "elastic demand"),
    ("economics", "opportunity cost"),
    ("finance", "cash runway"),
    ("finance", "discounted cash flow"),
    ("finance", "contribution margin"),
    ("decisions", "decision trees"),
    ("decisions", "sensitivity analysis"),
    ("decisions", "controlled experiment"),
    ("pricing", "Rentify premium subscription"),
    ("finance", "customer lifetime value"),
]
COURSES = [
    ("15.390", "New Enterprises", "spring-2013", "Entrepreneurship"),
    ("15.902", "Strategic Management I", "fall-2006", "Strategy"),
    ("15.810", "Marketing Management", "fall-2010", "Marketing"),
    ("15.431", "Entrepreneurial Finance", "spring-2011", "Corporate Finance"),
    ("15.060", "Data, Models, and Decisions", "fall-2014", "Decision Science"),
    ("15.010", "Economic Analysis for Business Decisions", "fall-2004", "Economics"),
    ("15.311", "Organizational Processes", "fall-2003", "Organizations"),
    ("15.387", "Entrepreneurial Sales", "spring-2015", "Sales"),
]


def main():
    (ROOT / "fixtures").mkdir(exist_ok=True)
    (ROOT / "manifests").mkdir(exist_ok=True)
    entries = []
    for key, subject, title, text in ITEMS:
        (ROOT / f"fixtures/{key}.md").write_text(f"# {title}\n\n{text}\n", encoding="utf-8")
        entries.append(
            dict(
                collection="mba-business",
                institution="OSCAR synthetic fixtures (not MIT)",
                course_code="DEMO-" + key.upper(),
                course_title=title,
                subject=subject,
                course_page="https://example.org/oscar-demo/" + key,
                local_file=key + ".md",
                license="CC0-1.0",
                license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                approved=True,
                notes="Original synthetic demonstration text dedicated to CC0. Not an actual university source.",
            )
        )
    (ROOT / "fixtures/demo.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": entries}, sort_keys=False), encoding="utf-8"
    )
    questions = [
        {"query": q, "source_keys": [f"https://example.org/oscar-demo/{key}#{key}.md"]}
        for key, q in QUERIES
    ]
    (ROOT / "fixtures/eval_questions.json").write_text(
        json.dumps(
            {"version": 1, "name": "synthetic-business-v1", "questions": questions}, indent=2
        ),
        encoding="utf-8",
    )
    entries = []
    for code, title, term, subject in COURSES:
        slug = (
            code.replace(".", "-")
            + "-"
            + title.lower().replace(",", "").replace(" ", "-")
            + "-"
            + term
        )
        entries.append(
            dict(
                collection="mba-business",
                institution="MIT",
                course_code=code,
                course_title=title,
                subject=subject,
                course_page="https://ocw.mit.edu/courses/" + slug + "/",
                download_url={
                    "15.390": "https://ocw.mit.edu/courses/15-390-new-enterprises-spring-2013/5ebade7cc7014ae6958bd5c48e3ff670_MIT15_390S13_lec01.pdf",
                    "15.902": "https://ocw.mit.edu/courses/15-902-strategic-management-i-fall-2006/92d72792ae5e336ac5e6f11a3af4a399_bud_aggmet.pdf",
                    "15.810": "https://ocw.mit.edu/courses/15-810-marketing-management-fall-2010/49e7dcea0276228cc640de924be6c213_MIT15_810F10_lec01.pdf",
                }.get(code),
                title={
                    "15.390": "New Enterprises — Lecture 1",
                    "15.902": "Strategic Management I — Bud AggMet",
                    "15.810": "Marketing Management — Lecture 1",
                }.get(code),
                license="CC-BY-NC-SA-4.0 (resource exceptions require review)",
                license_url="https://ocw.mit.edu/pages/privacy-and-terms-of-use/",
                approved=False,
                notes="Official course page verified 2026-10-25. Review individual resources and intended use before approval. No ZIP URL inferred.",
                ingestion_status="DISCOVERED",
            )
        )
    (ROOT / "manifests/mba_mit.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": entries}, sort_keys=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
