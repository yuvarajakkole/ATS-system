"""Pure unit tests, no API key / network needed. Run with: pytest"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.scoring.ai_content_detector import detect_ai_content_risk


def test_formulaic_text_flagged_higher_than_plain_text():
    formulaic = (
        "In today's fast-paced world, it is important to note that our cutting-edge, "
        "state-of-the-art solution seamlessly integrates robust and scalable systems, "
        "ensuring success. It's not just software, it's a revolution."
    )
    plain = (
        "I fixed a race condition in the payment retry logic using a Postgres advisory "
        "lock and added an idempotency key to the payments table."
    )
    formulaic_result = detect_ai_content_risk(formulaic)
    plain_result = detect_ai_content_risk(plain)

    assert formulaic_result["density_per_500_words"] > plain_result["density_per_500_words"]
    assert formulaic_result["score_fraction"] < plain_result["score_fraction"]


def test_empty_text_is_low_risk_not_a_crash():
    result = detect_ai_content_risk("")
    assert result["risk_level"] == "low"
