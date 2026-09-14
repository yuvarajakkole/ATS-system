"""
Turns the deterministic engine's output into readable prose. This call is
downstream of, and constrained by, the scoring engine - it is handed the
already-computed facts and told explicitly not to change them (see
NARRATIVE_SYSTEM). It cannot move the score or invent a strength/weakness.

Optional: if this call fails (e.g. no API key, network issue) the caller
should fall back to the deterministic strengths/weaknesses bullet lists
already computed in engine.py, which are perfectly usable feedback on
their own.
"""
import json
from app.llm_client import get_client
from app.config import settings
from app.extraction.prompts import NARRATIVE_SYSTEM


def generate_narrative(engine_result: dict, jd_role_title: str) -> str:
    client = get_client()
    payload = {
        "role_title": jd_role_title,
        "overall_score": engine_result["overall_score"],
        "category_scores": engine_result["category_scores"],
        "strengths": engine_result["strengths"],
        "weaknesses": engine_result["weaknesses"],
        "missing_keywords": engine_result["missing_keywords"],
        "ai_content_risk_level": engine_result["ai_content_risk"]["risk_level"],
    }
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": NARRATIVE_SYSTEM},
            {"role": "user", "content": "Write direct feedback from this data:\n\n" + json.dumps(payload, indent=2)},
        ],
    )
    return resp.choices[0].message.content.strip()
