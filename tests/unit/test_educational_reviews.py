import hashlib

from app.library.educational import REVIEWED, input_digest, verified_review


def test_review_requires_unchanged_input_and_source(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("Reviewed explanation", encoding="utf-8")
    unit = {"unit": "finance-01", "outcomes": ["discounting"]}
    receipt = {
        "status": REVIEWED,
        "input_sha256": input_digest(unit),
        "rationale": "Explanation and worked example were read.",
        "limits": "Bounded coverage, not accreditation.",
        "files": [{"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
    }
    assert verified_review(receipt, unit)
    assert not verified_review(receipt, {**unit, "outcomes": ["new outcome"]})
    assert not verified_review({**receipt, "status": "REVOKED"}, unit)
    assert not verified_review({**receipt, "files": []}, unit)
    source.write_text("Changed explanation", encoding="utf-8")
    assert not verified_review(receipt, unit)
    source.unlink()
    assert not verified_review(receipt, unit)


def test_missing_or_automatic_labels_do_not_certify_coverage():
    assert not verified_review(None, {})
    assert not verified_review({"status": "VERIFIED", "score": 1.0}, {})
