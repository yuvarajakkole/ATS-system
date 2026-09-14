from app.llm_client import structured_call
from app.schemas import AIStyleJudgment
from app.extraction.prompts import AI_STYLE_JUDGE_SYSTEM


def judge_ai_writing_style(resume_text: str) -> AIStyleJudgment:
    """
    Isolated call: sees ONLY the resume text. Judges phrasing/style
    likelihood of AI generation - not content truth, not qualifications,
    not told anything about scoring. Combined with the hardcoded pattern
    signal in scoring/ai_content_detector.py (deterministic combination,
    not this call).
    """
    return structured_call(
        system_prompt=AI_STYLE_JUDGE_SYSTEM,
        user_prompt=f"Resume text:\n\n{resume_text}",
        response_model=AIStyleJudgment,
        schema_name="ai_style_judgment",
    )
