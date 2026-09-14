from app.llm_client import structured_call
from app.schemas import JDExtraction
from app.extraction.prompts import JD_EXTRACTOR_SYSTEM


def extract_jd(jd_text: str) -> JDExtraction:
    """Isolated call: sees ONLY the job description text."""
    return structured_call(
        system_prompt=JD_EXTRACTOR_SYSTEM,
        user_prompt=f"Job description:\n\n{jd_text}",
        response_model=JDExtraction,
        schema_name="jd_extraction",
    )
