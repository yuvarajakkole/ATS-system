from app.llm_client import structured_call
from app.schemas import ResumeExtraction
from app.extraction.prompts import RESUME_EXTRACTOR_SYSTEM


def extract_resume(resume_text: str) -> ResumeExtraction:
    """Isolated call: sees ONLY the resume text. Never sees the JD."""
    return structured_call(
        system_prompt=RESUME_EXTRACTOR_SYSTEM,
        user_prompt=f"Resume:\n\n{resume_text}",
        response_model=ResumeExtraction,
        schema_name="resume_extraction",
    )
