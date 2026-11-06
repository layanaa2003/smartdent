"""Tests for the summary and suggested next steps written for each X-ray."""
from app.recommendations import NEXT_STEPS, area_of, assess, confidence_band

FINDINGS = [
    {"label": "Caries", "confidence": 0.81, "box": [100, 100, 140, 150], "review": "agree"},
    {"label": "Periapical lesion", "confidence": 0.57, "box": [500, 420, 560, 470], "review": None},
    {"label": "Bone Loss", "confidence": 0.40, "box": [300, 380, 340, 420], "review": "disagree"},
]


def test_area_follows_panoramic_orientation():
    # patient's right is on the left of the image; top half is the upper jaw
    assert area_of([10, 10, 50, 50], 640, 640) == "upper right back teeth"
    assert area_of([590, 600, 630, 630], 640, 640) == "lower left back teeth"
    assert area_of([300, 400, 340, 440], 640, 640) == "lower front teeth"
    assert area_of([10, 10, 50, 50], None, None) is None


def test_confidence_bands():
    assert [confidence_band(c) for c in (0.9, 0.7, 0.5, 0.2)] == ["high", "high", "moderate", "low"]


def test_summary_is_specific_to_the_xray():
    text = assess(FINDINGS, 640, 640, age=34, patient_name="Sara Example")["summary"]
    assert "Sara (34)" in text and "3 findings" in text
    assert "caries in the upper right back teeth (high confidence, 81%), which you agreed with" in text
    assert "which you rejected" in text and "did not mark any impacted teeth" in text
    assert "Suggested first check: the periapical lesion" in text


def test_rejected_findings_have_no_next_steps_and_urgent_comes_first():
    result = assess(FINDINGS, 640, 640)
    assert [s["label"] for s in result["steps"]] == ["Periapical lesion", "Caries"]
    assert result["rejected"] == 1 and result["pending"] == 1
    assert "lower left back teeth" in result["steps"][0]["check"]
    assert all(s["source"] for s in result["steps"])


def test_low_confidence_and_age_notes():
    steps = assess([{"label": "Bone Loss", "confidence": 0.3, "box": [0, 0, 10, 10], "review": None}],
                   640, 640, age=24)["steps"]
    assert steps[0]["low"] and "under 30" in steps[0]["note"]
    teen = assess([{"label": "Impacted tooth", "confidence": 0.9, "box": [0, 0, 10, 10]}], 640, 640, age=12)
    assert "still developing" in teen["steps"][0]["note"]


def test_no_findings():
    result = assess([], 640, 640, patient_name="Omar Example")
    assert result["steps"] == [] and "did not mark any" in result["summary"]


def test_every_condition_has_a_rule():
    from ml import CLASS_NAMES
    assert set(NEXT_STEPS) == set(CLASS_NAMES)
