"""Historical query definitions and local signing helper; scoring uses reviewed qrels."""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any

import httpx


CATALOG_DIR = Path("D:/AI/OSCAR/Knowledge/Catalog")
OUTPUT_DIR = CATALOG_DIR / "reports/quality-review/2026-10-26"
APPROVAL_FILE = CATALOG_DIR / "private-use-approval.json"

BENCHMARK_QUERIES = [
    # 22 MBA Majors
    {
        "id": "mba-01-accounting",
        "category": "mba_major",
        "sub_category": "accounting",
        "query": "How are noncurrent liabilities and lease obligations reported on balance sheets?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["liability", "balance sheet", "lease", "obligation"],
        "unanswerable": False,
    },
    {
        "id": "mba-02-ai-business",
        "category": "mba_major",
        "sub_category": "ai-business",
        "query": "What are the core governance risks and biases in enterprise generative AI deployment?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["governance", "bias", "risk", "deployment"],
        "unanswerable": False,
    },
    {
        "id": "mba-03-business-analytics",
        "category": "mba_major",
        "sub_category": "business-analytics",
        "query": "How does prescriptive linear programming optimization establish shadow prices for capacity constraints?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["linear programming", "optimization", "constraint", "shadow price"],
        "unanswerable": False,
    },
    {
        "id": "mba-04-economics-policy",
        "category": "mba_major",
        "sub_category": "economics-policy",
        "query": "How do price caps and subsidy floors distort market equilibrium and generate deadweight loss?",
        "expected_collections": ["mba-majors", "social-systems"],
        "gold_keywords": ["equilibrium", "deadweight loss", "subsidy", "price"],
        "unanswerable": False,
    },
    {
        "id": "mba-05-energy-environment",
        "category": "mba_major",
        "sub_category": "energy-environment",
        "query": "What are the regulatory mechanisms of electricity spot markets and capacity payments?",
        "expected_collections": ["mba-majors"],
        "gold_keywords": ["electricity", "regulation", "capacity", "market"],
        "unanswerable": False,
    },
    {
        "id": "mba-06-entrepreneurship",
        "category": "mba_major",
        "sub_category": "entrepreneurship",
        "query": "How should early-stage venture founders evaluate customer feedback and iterate MVP prototypes?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["customer", "founder", "prototype", "feedback"],
        "unanswerable": False,
    },
    {
        "id": "mba-07-finance",
        "category": "mba_major",
        "sub_category": "finance",
        "query": "How is weighted average cost of capital (WACC) calculated with debt tax shields?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["WACC", "cost of capital", "tax shield", "debt"],
        "unanswerable": False,
    },
    {
        "id": "mba-08-healthcare",
        "category": "mba_major",
        "sub_category": "healthcare",
        "query": "How do value-based healthcare payment models differ from fee-for-service reimbursement?",
        "expected_collections": ["mba-majors"],
        "gold_keywords": ["fee-for-service", "value-based", "reimbursement", "healthcare"],
        "unanswerable": False,
    },
    {
        "id": "mba-09-impact-sustainable",
        "category": "mba_major",
        "sub_category": "impact-sustainable",
        "query": "What metrics distinguish carbon abatement additionality from baseline ESG disclosures?",
        "expected_collections": ["mba-majors"],
        "gold_keywords": ["carbon", "abatement", "ESG", "sustainability"],
        "unanswerable": False,
    },
    {
        "id": "mba-10-individualized",
        "category": "mba_major",
        "sub_category": "individualized",
        "query": "How do cross-disciplinary organizational interventions integrate systems dynamics and economic incentives?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["systems", "organization", "incentive", "dynamics"],
        "unanswerable": False,
    },
    {
        "id": "mba-11-leading-differences",
        "category": "mba_major",
        "sub_category": "leading-differences",
        "query": "How does organizational culture mitigate psychological barriers to inclusive leadership?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["culture", "leadership", "organization", "inclusive"],
        "unanswerable": False,
    },
    {
        "id": "mba-12-management",
        "category": "mba_major",
        "sub_category": "management",
        "query": "What formal organizational structures balance decentralized decision authority with executive control?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["structure", "authority", "control", "decentralized"],
        "unanswerable": False,
    },
    {
        "id": "mba-13-marketing",
        "category": "mba_major",
        "sub_category": "marketing",
        "query": "How do customer lifetime value (CLV) and customer acquisition cost (CAC) determine marketing mix allocation?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["lifetime value", "acquisition cost", "marketing", "allocation"],
        "unanswerable": False,
    },
    {
        "id": "mba-14-marketing-operations",
        "category": "mba_major",
        "sub_category": "marketing-operations",
        "query": "How does product line variety affect supply chain lead times and inventory holding costs?",
        "expected_collections": ["mba-majors"],
        "gold_keywords": ["inventory", "lead time", "variety", "supply chain"],
        "unanswerable": False,
    },
    {
        "id": "mba-15-multinational",
        "category": "mba_major",
        "sub_category": "multinational",
        "query": "How do foreign exchange translation exposures affect multinational capital budgeting?",
        "expected_collections": ["mba-majors"],
        "gold_keywords": ["foreign exchange", "multinational", "exposure", "currency"],
        "unanswerable": False,
    },
    {
        "id": "mba-16-operations-information",
        "category": "mba_major",
        "sub_category": "operations-information-decisions",
        "query": "How does the bullwhip effect propagate upstream demand variance in supply chains?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["bullwhip", "demand", "variance", "supply chain"],
        "unanswerable": False,
    },
    {
        "id": "mba-17-organizational-eff",
        "category": "mba_major",
        "sub_category": "organizational-effectiveness",
        "query": "What mechanisms resolve agency dilemmas and align executive incentives with shareholder value?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["agency", "incentive", "executive", "shareholder"],
        "unanswerable": False,
    },
    {
        "id": "mba-18-quantitative-finance",
        "category": "mba_major",
        "sub_category": "quantitative-finance",
        "query": "How does the Black-Scholes formula compute European call option prices with dividend yields?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["Black-Scholes", "option", "call", "volatility"],
        "unanswerable": False,
    },
    {
        "id": "mba-19-real-estate",
        "category": "mba_major",
        "sub_category": "real-estate",
        "query": "How do commercial mortgage debt service coverage ratios (DSCR) limit borrowing capacity?",
        "expected_collections": ["mba-majors"],
        "gold_keywords": ["debt service coverage", "DSCR", "mortgage", "underwriting"],
        "unanswerable": False,
    },
    {
        "id": "mba-20-social-governance",
        "category": "mba_major",
        "sub_category": "social-governance",
        "query": "What legal fiduciary duties govern board oversight of corporate compliance and stakeholder risks?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["fiduciary", "board", "compliance", "stakeholder"],
        "unanswerable": False,
    },
    {
        "id": "mba-21-statistics-data-science",
        "category": "mba_major",
        "sub_category": "statistics-data-science",
        "query": "How does k-fold cross-validation evaluate out-of-sample error and prevent overfitting in regression models?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["cross-validation", "overfitting", "regression", "error"],
        "unanswerable": False,
    },
    {
        "id": "mba-22-strategic-management",
        "category": "mba_major",
        "sub_category": "strategic-management",
        "query": "How do Porter's five competitive forces determine industry attractiveness and entry barriers?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["Porter", "competitive forces", "barriers", "industry"],
        "unanswerable": False,
    },
    # General Library Categories
    {
        "id": "gen-01-strategy",
        "category": "general_library",
        "sub_category": "strategy",
        "query": "Which leverage points change feedback loops, rules and goals in a system?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["leverage points", "feedback loops", "system", "rules"],
        "unanswerable": False,
    },
    {
        "id": "gen-02-finance",
        "category": "general_library",
        "sub_category": "finance",
        "query": "Why do investors need a margin of safety and room for error in long-term financial planning?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["margin of safety", "room for error", "investor", "planning"],
        "unanswerable": False,
    },
    {
        "id": "gen-03-quantitative",
        "category": "general_library",
        "sub_category": "quantitative",
        "query": "How is conditional probability calculated from joint probability and the conditioning event?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["conditional probability", "joint probability", "conditioning"],
        "unanswerable": False,
    },
    {
        "id": "gen-04-product",
        "category": "general_library",
        "sub_category": "product",
        "query": "Why should founders ask about customers' past behavior rather than hypothetical questions?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["customer", "behavior", "hypothetical", "questions"],
        "unanswerable": False,
    },
    {
        "id": "gen-05-leadership",
        "category": "general_library",
        "sub_category": "leadership",
        "query": "Why can short checklists improve reliability in complex team operations?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["checklist", "reliability", "team", "operations"],
        "unanswerable": False,
    },
    {
        "id": "gen-06-communication",
        "category": "general_library",
        "sub_category": "communication",
        "query": "How do plain words and shorter sentences improve clarity in professional writing?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["words", "sentences", "clarity", "writing"],
        "unanswerable": False,
    },
    {
        "id": "gen-07-society",
        "category": "general_library",
        "sub_category": "society",
        "query": "How does the sociological imagination link personal troubles to public issues?",
        "expected_collections": ["personal-library", "social-systems"],
        "gold_keywords": ["sociological imagination", "troubles", "public issues"],
        "unanswerable": False,
    },
    # OCR / Math / Tables
    {
        "id": "ocr-01-supply-chain-math",
        "category": "ocr_math_table",
        "sub_category": "ocr_passage",
        "query": "What are the structural lessons and information delays identified in the Beer Game debrief?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["Beer Game", "structure", "delays", "information flow"],
        "unanswerable": False,
    },
    {
        "id": "ocr-02-compilation-physics-formula",
        "category": "ocr_math_table",
        "sub_category": "compilation_formula",
        "query": "In physics kinematics, how is constant acceleration related to displacement and time in physical page 110908?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["acceleration", "displacement", "velocity", "time"],
        "unanswerable": False,
    },
    {
        "id": "ocr-03-accounting-table",
        "category": "ocr_math_table",
        "sub_category": "accounting_table",
        "query": "In financial statements, what line items separate operating cash flows from financing cash flows?",
        "expected_collections": ["mba-majors", "personal-library"],
        "gold_keywords": ["operating cash", "financing cash", "cash flow", "activities"],
        "unanswerable": False,
    },
    # Attribution & Compilation Windows
    {
        "id": "attr-01-political-science",
        "category": "attribution",
        "sub_category": "named_compilation",
        "query": "What defines political legitimacy and institutional power in OpenStax Introduction to Political Science physical pages 10421-11059?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["legitimacy", "political", "power", "institution"],
        "unanswerable": False,
    },
    {
        "id": "attr-02-psychology",
        "category": "attribution",
        "sub_category": "named_compilation",
        "query": "How does classical conditioning differ from operant conditioning in OpenStax Psychology physical pages 35189-35971?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["classical conditioning", "operant conditioning", "reinforcement"],
        "unanswerable": False,
    },
    {
        "id": "attr-03-unverified-compilation",
        "category": "attribution",
        "sub_category": "generic_compilation_window",
        "query": "What evidence is presented in Mixed local compilation PDF pages 1 to 1000 regarding source attribution?",
        "expected_collections": ["personal-library"],
        "gold_keywords": ["compilation", "PDF page"],
        "unanswerable": False,
    },
    # Unanswerable / Abstention
    {
        "id": "unans-01-fictional-entity",
        "category": "unanswerable",
        "sub_category": "abstention",
        "query": "What was the Q3 2025 net income of Zephyron Corporation under the Galactic Trade Accord?",
        "expected_collections": ["personal-library", "mba-majors"],
        "gold_keywords": ["Zephyron", "Galactic Trade Accord"],
        "unanswerable": True,
    },
    {
        "id": "unans-02-secret-formula",
        "category": "unanswerable",
        "sub_category": "abstention",
        "query": "What is the secret proprietary recipe for Coca-Cola stored in the Atlanta vault?",
        "expected_collections": ["personal-library", "mba-majors"],
        "gold_keywords": ["Coca-Cola recipe", "secret formula"],
        "unanswerable": True,
    },
]


def execute_signed_request(
    client: httpx.Client,
    body_dict: dict[str, Any],
    secret_key: str,
    service_token: str,
    owner_id: str,
    timeout: float = 8.0,
) -> httpx.Response:
    body_bytes = json.dumps(body_dict, separators=(",", ":")).encode()
    now = int(time.time())
    claims = {
        "aud": "oscar-knowledge-private-v1",
        "sub": owner_id,
        "iat": now,
        "exp": now + 30,
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
    }
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()

    headers = {
        "Authorization": "Bearer " + service_token,
        "Content-Type": "application/json",
        "X-OSCAR-Private-Scope": payload + "." + sig,
    }
    return client.post(
        "http://127.0.0.1:8010/internal/v1/retrieve",
        headers=headers,
        content=body_bytes,
        timeout=timeout,
    )


def main():
    from scripts.evaluate_verified_quality import main as verified_main

    verified_main()


if __name__ == "__main__":
    main()
