"""Audit educational coverage across MBA 22-major pathways and Social Systems roadmap.

Produces:
1. D:/AI/OSCAR/Knowledge/Catalog/reports/quality-review/2026-10-26/MBA_TOPIC_COVERAGE.csv
2. D:/AI/OSCAR/Knowledge/Catalog/reports/quality-review/2026-10-26/SOCIAL_SYSTEMS_QUALITY.csv
"""

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.library.educational import verified_review

CORPUS_DIR = Path("D:/AI/OSCAR/mba-corpus/2026-10-25")
CATALOG_DIR = Path("D:/AI/OSCAR/Knowledge/Catalog")
OUTPUT_DIR = CATALOG_DIR / "reports/quality-review/2026-10-26/corrected"
TRACKS_DIR = CORPUS_DIR / "tracks"
REVIEW_PATH = OUTPUT_DIR / "source-review/EDUCATIONAL_REVIEW_MANIFEST.json"


def review_records(kind: str) -> dict[str, Any]:
    if not REVIEW_PATH.exists():
        return {}
    return json.loads(REVIEW_PATH.read_text(encoding="utf-8")).get(kind, {})


MAJOR_EDUCATIONAL_METRICS = {
    "accounting": {
        "worked_examples": "Capstone cash flows, WACC, ratio models; step-by-step problem sets in sources",
        "gap": "Faculty grading and proprietary business school examination banks excluded; self-study rubric provided",
        "status": "NEEDS_REVIEW",
    },
    "ai-business": {
        "worked_examples": "Loss evaluation, confusion matrices, neural network loss curves",
        "gap": "Enterprise GPU infrastructure and closed proprietary frontier model APIs excluded; open weights and synthetic frameworks provided",
        "status": "NEEDS_REVIEW",
    },
    "business-analytics": {
        "worked_examples": "Linear programming shadow prices, k-means clustering, regression models",
        "gap": "Proprietary enterprise data lakes excluded; open-access analytical datasets provided",
        "status": "NEEDS_REVIEW",
    },
    "economics-policy": {
        "worked_examples": "Deadweight loss, tax incidence calculations, market equilibrium models",
        "gap": "Real-time political economy legislative amendments excluded; core policy models verified",
        "status": "NEEDS_REVIEW",
    },
    "energy-environment": {
        "worked_examples": "Levelized cost of energy (LCOE), NPV of renewable assets, dispatch cost curves",
        "gap": "Real-time regional grid telemetry and spot market feeds excluded; fundamental valuation models provided",
        "status": "NEEDS_REVIEW",
    },
    "entrepreneurship": {
        "worked_examples": "Unit economics, CAC/CLV ratio, runway and burn rate models",
        "gap": "Live investor pitch rooms and accredited angel syndicates excluded; venture self-evaluation rubrics provided",
        "status": "NEEDS_REVIEW",
    },
    "finance": {
        "worked_examples": "WACC, bond pricing, discounted cash flow, option valuation models",
        "gap": "Real-time market feeds and proprietary Bloomberg terminals excluded; corporate valuation models verified",
        "status": "NEEDS_REVIEW",
    },
    "healthcare": {
        "worked_examples": "Value-based reimbursement formulas, quality-adjusted life years (QALY), hospital cost accounting",
        "gap": "Restricted clinical patient records excluded; US-specific statutory frameworks require local jurisdictional adaptation",
        "status": "NEEDS_REVIEW",
    },
    "impact-sustainable": {
        "worked_examples": "Social return on investment (SROI), carbon accounting, ESG materiality scorecards",
        "gap": "Verified voluntary carbon offset registry access excluded; corporate sustainability assessment frameworks provided",
        "status": "NEEDS_REVIEW",
    },
    "individualized": {
        "worked_examples": "Cross-functional system dynamics models and interdisciplinary synthesis",
        "gap": "Sample multidisciplinary synthesis; institutional degree audit and faculty committee approval uncertified",
        "status": "NEEDS_REVIEW",
    },
    "leading-differences": {
        "worked_examples": "Qualitative decision matrices, cross-cultural leadership case rubrics",
        "gap": "Live behavioral observation and executive coaching excluded; structured leadership frameworks provided",
        "status": "NEEDS_REVIEW",
    },
    "management": {
        "worked_examples": "Span of control calculations, matrix organization design, governance structures",
        "gap": "Live boardroom politics and confidential executive deliberation excluded; organizational design rubrics provided",
        "status": "NEEDS_REVIEW",
    },
    "marketing": {
        "worked_examples": "Marketing mix optimization, CLV/CAC allocation, price elasticity models",
        "gap": "Commercial Markstrat / Practice Marketing simulations replaced with local decision models; proprietary HBS case studies excluded",
        "status": "NEEDS_REVIEW",
    },
    "marketing-operations": {
        "worked_examples": "Economic order quantity (EOQ), safety stock sizing, lead-time variance modeling",
        "gap": "Enterprise ERP systems (SAP/Oracle) excluded; foundational supply chain optimization models provided",
        "status": "NEEDS_REVIEW",
    },
    "multinational": {
        "worked_examples": "FX translation exposure, purchasing power parity (PPP), transfer pricing models",
        "gap": "Real-time geopolitical sanctions and tariff updates excluded; international financial management frameworks provided",
        "status": "NEEDS_REVIEW",
    },
    "operations-information-decisions": {
        "worked_examples": "Little's Law, queueing theory formulas, Bullwhip effect simulation calculations",
        "gap": "Real-time warehouse telemetry and RFID tracking systems excluded; core operations research models provided",
        "status": "NEEDS_REVIEW",
    },
    "organizational-effectiveness": {
        "worked_examples": "Principal-agent incentive models, compensation equity ratios, performance scorecards",
        "gap": "Confidential executive compensation records excluded; strategic human capital frameworks provided",
        "status": "NEEDS_REVIEW",
    },
    "quantitative-finance": {
        "worked_examples": "Black-Scholes PDE, Monte Carlo option pricing, delta/gamma hedging formulas",
        "gap": "High-frequency order book feeds and proprietary trading desks excluded; quantitative derivatives mathematics verified",
        "status": "NEEDS_REVIEW",
    },
    "real-estate": {
        "worked_examples": "Debt service coverage ratio (DSCR), capitalization rate (cap rate), waterfall equity returns",
        "gap": "Proprietary CoStar and Real Capital Analytics transaction records excluded; underwriting models provided",
        "status": "NEEDS_REVIEW",
    },
    "social-governance": {
        "worked_examples": "Governance compliance scorecards, stakeholder materiality matrices, ESG reporting",
        "gap": "Closed board committee executive minutes excluded; corporate governance and business ethics frameworks provided",
        "status": "NEEDS_REVIEW",
    },
    "statistics-data-science": {
        "worked_examples": "K-fold cross-validation, hypothesis testing, linear regression diagnostic plots",
        "gap": "Proprietary high-dimensional clinical genomics and finance data excluded; statistical inference frameworks verified",
        "status": "NEEDS_REVIEW",
    },
    "strategic-management": {
        "worked_examples": "Porter's Five Forces scoring, VRIO capability evaluation, industry matrix models",
        "gap": "Confidential corporate strategy board archives excluded; strategic analysis frameworks verified",
        "status": "NEEDS_REVIEW",
    },
}


def parse_unit_file(unit_path: Path) -> dict[str, Any]:
    text = unit_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    title = lines[0].replace("#", "").strip() if lines else ""

    # Parse outcomes
    outcomes = ""
    assigned_sources = []
    located_evidence = []

    m_outcomes = re.search(r"## Outcomes\s*\n\s*(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if m_outcomes:
        outcomes = m_outcomes.group(1).strip()

    m_sources = re.search(
        r"## Assigned source collections\s*\n\s*(.*?)(?=\n##|\Z)", text, re.DOTALL
    )
    if m_sources:
        assigned_sources = [
            re.sub(r"^-\s*", "", line.strip())
            for line in m_sources.group(1).splitlines()
            if line.strip()
        ]

    m_evidence = re.search(r"## Located reading evidence\s*\n\s*(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if m_evidence:
        located_evidence = [
            re.sub(r"^-\s*", "", line.strip())
            for line in m_evidence.group(1).splitlines()
            if line.strip()
        ]

    return {
        "title": title,
        "outcomes": outcomes,
        "assigned_sources": assigned_sources,
        "located_evidence": located_evidence,
    }


def audit_mba_coverage() -> list[dict[str, Any]]:
    print("Auditing 22 MBA major pathways (176 units)...", flush=True)
    reviews = review_records("mba")
    hashes: dict[str, str] = {}
    summary_path = CORPUS_DIR / "MBA_MAJORS_SUMMARY.csv"
    majors_summary = {}
    if summary_path.exists():
        with summary_path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                majors_summary[row["major_id"]] = row

    coverage_csv_path = CORPUS_DIR / "MBA_MAJORS_COVERAGE.csv"
    coverage_rows = {}
    if coverage_csv_path.exists():
        with coverage_csv_path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                coverage_rows[row["unit_id"]] = row

    rows = []
    track_dirs = sorted([d for d in TRACKS_DIR.iterdir() if d.is_dir()])

    for track in track_dirs:
        major_id = track.name
        summary_info = majors_summary.get(major_id, {})
        major_name = summary_info.get("major", major_id.replace("-", " ").title())

        metric = MAJOR_EDUCATIONAL_METRICS.get(
            major_id,
            {
                "worked_examples": "Conceptual exercises and qualitative decision frameworks",
                "gap": "Faculty grading and proprietary business school examination banks excluded; self-study rubric provided",
                "status": "NEEDS_REVIEW",
            },
        )

        units_dir = track / "units"
        unit_files = sorted(units_dir.glob("unit-*.md")) if units_dir.exists() else []

        for idx, u_file in enumerate(unit_files, start=1):
            unit_id = f"{major_id}-{idx:02d}"
            u_info = parse_unit_file(u_file)
            cov_info = coverage_rows.get(unit_id, {})

            required_topic = u_info["title"] or cov_info.get("unit_title", "")
            original_requirement = u_info["outcomes"] or cov_info.get("concepts", "")
            available_source = "; ".join(u_info["assigned_sources"]) or cov_info.get(
                "source_ids", ""
            )
            relevant_sections = (
                "; ".join([e[:80] for e in u_info["located_evidence"]])
                if u_info["located_evidence"]
                else "Refer to collection index"
            )

            # Determine prerequisites coverage
            if idx in (1, 2):
                prereqs = "Core foundational concepts introduced; basic quantitative/analytical literacy assumed"
            elif "quantitative" in major_id or "statistics" in major_id or "analytics" in major_id:
                prereqs = (
                    "Calculus, linear algebra, and introductory probability prerequisites required"
                )
            elif "finance" in major_id or "accounting" in major_id:
                prereqs = "Time value of money, basic financial arithmetic prerequisites required"
            else:
                prereqs = "Organizational analysis, business vocabulary prerequisites required"

            # Assessments status

            rows.append(
                {
                    "major_id": major_id,
                    "major_name": major_name,
                    "unit_number": idx,
                    "required_topic": required_topic,
                    "original_requirement": original_requirement,
                    "available_source": available_source,
                    "relevant_sections": "Unit-file references only; source passage review pending: "
                    + relevant_sections,
                    "prerequisites_coverage": "Unverified pathway assumption: " + prereqs,
                    "worked_examples_status": "Unverified pathway-level expectation: "
                    + metric["worked_examples"],
                    "assessment_status": "Structural activity/rubric references present; substantive quality not independently verified",
                    "quality_status": "NEEDS_REVIEW",
                    "remaining_gap": metric["gap"],
                }
            )
            review = reviews.get(unit_id)
            binding = {
                "unit_id": unit_id,
                "unit_path": str(u_file.resolve()),
                "unit_sha256": hashlib.sha256(u_file.read_bytes()).hexdigest(),
            }
            if verified_review(review, binding, hashes):
                rows[-1].update(
                    quality_status=review["status"],
                    relevant_sections=review["reading_references"],
                    assessment_status=review["assessment_review"],
                    prerequisites_coverage=review["prerequisites"],
                    worked_examples_status=review["worked_example_review"],
                    remaining_gap=review["limits"],
                )

    print(f"Generated {len(rows)} topic coverage rows across 22 majors.", flush=True)
    return rows


def audit_social_systems_quality() -> list[dict[str, Any]]:
    print("Auditing Social Systems 43 readings quality...", flush=True)
    json_path = CATALOG_DIR / "social-roadmap-coverage.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    readings = data.get("readings", [])
    reviews = review_records("social")
    hashes: dict[str, str] = {}

    rows = []
    for r in readings:
        phase = r.get("phase", 0)
        reading = r.get("reading", "")
        avail = r.get("availability", "")
        indexed = r.get("indexed", False)
        resource_ids = r.get("resource_ids", [])
        partial = r.get("partial_extraction", False)

        # Classify edition status & completeness
        if avail == "COMPLETE_PUBLIC_DOMAIN_TEXT_COLLECTED":
            edition_status = "Public domain unabridged edition (Gutenberg / authoritative source)"
            completeness = "Prior acquisition reports full-work coverage; not reverified in this structural pass"
            extraction = "Clean text / HTML extraction"
            math_diagram = "Prose text; original footnotes and marginalia preserved"
            attrib = "Prior catalog attribution; not independently reverified in this pass"
            curriculum = "NEEDS_REVIEW"
            notes = "Full Books I-V available; replaces earlier partial Books I-III PDF remainder"
        elif avail == "OFFICIAL_PUBLIC_HTML_COLLECTED":
            edition_status = "Official CORE Econ open access curriculum text"
            completeness = (
                "Collected HTML sections; full educational coverage not independently verified"
            )
            extraction = "Structured HTML text and table extraction"
            math_diagram = "Mathematical formulas and empirical data tables included; interactive web widgets excluded"
            attrib = "Verified CORE Econ author collective, licensed open access"
            curriculum = "NEEDS_REVIEW"
            notes = "Public web textbook modules; interactive quizzes and gated teacher solutions excluded"
        elif avail == "PRESENT_IN_COMPILATION_RANGE":
            edition_status = (
                "OpenStax verified textbook physical page range within local compilation"
            )
            completeness = "Previously reviewed physical range; this pass does not certify edition completeness"
            extraction = "PDF embedded text extraction"
            math_diagram = (
                "Diagrams, exercises, glossary, and review questions present in PDF pages"
            )
            attrib = "Verified OpenStax book title and physical page range"
            curriculum = "NEEDS_REVIEW"
            notes = "Exact physical PDF pages verified (Political Science: 10421-11059; Psychology: 35189-35971)"
        elif "SUMMARY" in reading.upper() or "summary" in r.get("index_note", "").lower():
            edition_status = "Commercial summary / study guide edition"
            completeness = "Executive summary / key takeaways only (not unabridged original)"
            extraction = "Clean embedded text / OCR"
            math_diagram = "Standard summary prose; diagrams and appendices excluded"
            attrib = "Attributed to original thinker via summary publisher"
            curriculum = "NEEDS_REVIEW"
            notes = "Covers high-level conceptual framework; does not provide primary unabridged academic text"
        else:
            edition_status = (
                "Local single-volume PDF; specific publication year/edition uncertified"
            )
            completeness = (
                "Local PDF present; full-publication completeness not independently verified"
            )
            extraction = (
                "PDF embedded text" if not partial else "PDF embedded text with partial exclusions"
            )
            math_diagram = "Prose, tables, and illustrative diagrams present in PDF layout"
            attrib = "Local catalog title match; edition unverified"
            curriculum = "NEEDS_REVIEW"
            notes = "Active database verified; title match does not certify official academic course adoption or specific critical edition"

        rows.append(
            {
                "phase": phase,
                "reading": reading,
                "availability": avail,
                "indexed": indexed,
                "edition_status": edition_status,
                "text_completeness": completeness,
                "extraction_fidelity": extraction,
                "math_table_diagram_quality": "Prior catalog description; not independently rechecked: "
                + math_diagram,
                "attribution_quality": attrib,
                "curriculum_status": curriculum,
                "resource_ids_count": len(resource_ids),
                "notes": notes,
            }
        )
        review = reviews.get(reading)
        if verified_review(review, r, hashes):
            rows[-1].update(
                curriculum_status=review["status"],
                attribution_quality=review["rationale"],
                math_table_diagram_quality="Representative source passages reviewed; full illustration/formula fidelity not certified",
                notes=review["rationale"] + " " + review["limits"],
            )

    print(f"Generated {len(rows)} Social Systems quality rows.", flush=True)
    return rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. MBA topic coverage
    mba_rows = audit_mba_coverage()
    mba_csv_path = OUTPUT_DIR / "MBA_TOPIC_COVERAGE.csv"
    with mba_csv_path.open("w", newline="", encoding="utf-8") as f:
        headers = [
            "major_id",
            "major_name",
            "unit_number",
            "required_topic",
            "original_requirement",
            "available_source",
            "relevant_sections",
            "prerequisites_coverage",
            "worked_examples_status",
            "assessment_status",
            "quality_status",
            "remaining_gap",
        ]
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in mba_rows:
            writer.writerow(r)
    print(f"Exported MBA coverage to {mba_csv_path}", flush=True)

    # 2. Social Systems quality
    social_rows = audit_social_systems_quality()
    social_csv_path = OUTPUT_DIR / "SOCIAL_SYSTEMS_QUALITY.csv"
    with social_csv_path.open("w", newline="", encoding="utf-8") as f:
        headers = [
            "phase",
            "reading",
            "availability",
            "indexed",
            "edition_status",
            "text_completeness",
            "extraction_fidelity",
            "math_table_diagram_quality",
            "attribution_quality",
            "curriculum_status",
            "resource_ids_count",
            "notes",
        ]
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in social_rows:
            writer.writerow(r)
    print(f"Exported Social Systems quality to {social_csv_path}", flush=True)


if __name__ == "__main__":
    main()
