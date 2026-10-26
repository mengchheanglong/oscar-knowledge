"""Bind explicit private source-review decisions to unchanged sources and activities.

Never generates review judgments. Requires all 176 + 43 recorded decisions.
"""

import hashlib
import json
import re
import runpy
import sqlite3
from pathlib import Path

from app.library.educational import REVIEWED, input_digest

ROOT = Path("D:/AI/OSCAR/Knowledge/Catalog")
CORPUS = Path("D:/AI/OSCAR/mba-corpus/2026-10-25")
OUTPUT = ROOT / "reports/quality-review/2026-10-26/corrected/source-review"


def main():
    hashes = {}

    def proof(path):
        path = Path(path)
        key = str(path)
        if key not in hashes:
            sha = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    sha.update(block)
            hashes[key] = sha.hexdigest()
        return {"path": key, "sha256": hashes[key]}

    def read(name):
        return json.loads((OUTPUT / name).read_text(encoding="utf-8"))

    units = read("CURRICULUM_REVIEW_DECISIONS.json")["units"]
    social = read("SOCIAL_REVIEW_DECISIONS.json")["readings"]
    assert len(units) == 176 and len(social) == 43, "MISSING_MANUAL_DECISIONS"
    packet = {u["unit_id"]: u for u in read("CURRICULUM_REVIEW_PACKET.json")["units"]}
    roadmap = json.loads((ROOT / "social-roadmap-coverage.json").read_text(encoding="utf-8"))
    program = CORPUS / "major-expansion/capstone_calculators.py"
    cases, checks = runpy.run_path(str(program))["solve"]()
    # JSON object keys are strings (the newsvendor model uses integer quantities).
    cases = json.loads(json.dumps(cases))
    saved = json.loads(
        program.with_name("capstone-worked-results.json").read_text(encoding="utf-8")
    )
    assert cases == saved, "WORKED_RESULTS_CHANGED"
    db_path = CORPUS / "MBA_MAJORS_SEARCH.sqlite3"
    db = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    manifest = {
        "scope": "Bounded self-study coverage, not publication-wide factual certification",
        "mba": {},
        "social": {},
    }
    references = ["# Reviewed MBA reading map", "", manifest["scope"], ""]
    for uid, review in units.items():
        assert review["status"] == REVIEWED and review["rationale"].strip()
        major = packet[uid]["major_id"]
        number = int(uid.rsplit("-", 1)[1])
        unit = CORPUS / "tracks" / major / "units" / f"unit-{number:02}.md"
        capstone = unit.parent.parent / "CAPSTONE.md"
        text = unit.read_text(encoding="utf-8")
        captext = capstone.read_text(encoding="utf-8")
        assert all(h in text for h in ["## Outcomes", "## Activity", "## Assessment rubric"])
        assert all(
            any(alias.lower() in text.lower() for alias in c.split("|")) for c in review["concepts"]
        )
        assert "at least two plausible actions" in text
        assert str(capstone).replace("\\", "/") in text
        assert sum(int(n) for n in re.findall(r"\|\s*(\d+)\s*\|", text)) == 100
        assert sum(int(n) for n in re.findall(r"\|\s*(\d+)\s*\|", captext)) == 100
        worked = re.search(r"```json\s*(.*?)\s*```", captext, re.S)
        assert worked and json.loads(worked[1]) == cases[major]["worked_results"]
        assert cases[major]["scenario"] in captext
        files = [
            proof(unit),
            proof(capstone),
            proof(program),
            proof(db_path),
            proof(OUTPUT / "CURRICULUM_REVIEW_DECISIONS.json"),
        ]
        refs = []
        for evidence in review["evidence"]:
            body = db.execute(
                "SELECT body FROM passages WHERE rowid=?", (evidence["rowid"],)
            ).fetchone()[0]
            assert hashlib.sha256(body.encode()).hexdigest() == evidence["passage_sha256"]
            bound = proof(evidence["path"])
            assert bound["sha256"] == evidence["source_file_sha256"]
            files.append(bound)
            refs.append(
                f"{evidence['title']} | {evidence['path']} | page {evidence['page']} | passage {evidence['rowid']}"
            )
        entry = {
            **review,
            "input_sha256": input_digest(
                {
                    "unit_id": uid,
                    "unit_path": str(unit.resolve()),
                    "unit_sha256": proof(unit)["sha256"],
                }
            ),
            "files": files,
            "reading_references": "; ".join(refs),
            "assessment_review": "Reviewed common four-part activity: concept distinctions/citations, capstone application, two alternatives, assumptions/evaluation; 100-point self-study rubric. Essays not independently graded.",
            "prerequisites": "Self-study sequence assumes basic business literacy and arithmetic; advanced quantitative work additionally requires probability, calculus and linear algebra. Not a certified admission/prerequisite assessment.",
            "worked_example_review": f"Read {major} fictional capstone scenario/model; reproduced saved numerical results and all {checks['checks_passed']} program assertions across 22 majors. No empirical/causal result implied.",
        }
        manifest["mba"][uid] = entry
        references.extend(
            [
                f"## {uid}: {review['unit_title']}",
                "",
                review["rationale"],
                "",
                *[f"- {r}" for r in refs],
                "",
            ]
        )
    db.close()
    for item in roadmap["readings"]:
        review = social[item["reading"]]
        assert review["status"] == REVIEWED and review["rationale"].strip()
        source = proof(review["source_path"])
        assert source["sha256"] == review["source_sha256"]
        manifest["social"][item["reading"]] = {
            **review,
            "input_sha256": input_digest(item),
            "files": [
                source,
                proof(OUTPUT / "SOCIAL_REVIEW_DECISIONS.json"),
                proof(OUTPUT / "SOCIAL_REVIEW_PACKET.json"),
            ],
        }
    (OUTPUT / "EDUCATIONAL_REVIEW_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT / "REVIEWED_MBA_READING_MAP.md").write_text("\n".join(references), encoding="utf-8")
    (OUTPUT / "CAPSTONE_RECHECK.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "mba": len(units),
                "social": len(social),
                "capstones": len(cases),
                "checks": checks["checks_passed"],
            }
        )
    )


if __name__ == "__main__":
    main()
