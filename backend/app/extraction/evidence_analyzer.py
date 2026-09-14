import json
from app.llm_client import structured_call
from app.schemas import EvidenceAnalysis, JDExtraction, ResumeExtraction
from app.extraction.prompts import EVIDENCE_ANALYST_SYSTEM


def analyze_evidence(jd: JDExtraction, resume: ResumeExtraction) -> EvidenceAnalysis:
    """
    For every must-have + nice-to-have skill in the JD, check whether the
    resume actually defends it (see EVIDENCE_ANALYST_SYSTEM for the
    strength rubric). This call sees structured facts only — not the raw
    JD/resume text framing, not any prior score, not which skills are
    "must-have" vs "nice-to-have" weighting in the final score (that
    weighting lives only in the deterministic engine).
    """
    all_skills = list(dict.fromkeys(jd.must_have_skills + jd.nice_to_have_skills))
    payload = {
        "skills_to_check": all_skills,
        "resume_skills_section": resume.skills_section_items,
        "resume_experience_bullets": [
            {"company": e.company, "title": e.title, "bullets": e.bullets}
            for e in resume.experience
        ],
        "resume_project_bullets": [
            {"name": p.name, "bullets": p.description_bullets, "tech_used": p.tech_used}
            for p in resume.projects
        ],
    }
    return structured_call(
        system_prompt=EVIDENCE_ANALYST_SYSTEM,
        user_prompt=(
            "Evaluate evidence for each skill in skills_to_check against the "
            "resume content below. Return one entry per skill.\n\n"
            + json.dumps(payload, indent=2)
        ),
        response_model=EvidenceAnalysis,
        schema_name="evidence_analysis",
    )
