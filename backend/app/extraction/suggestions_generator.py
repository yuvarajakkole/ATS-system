"""
Generates the "how to actually improve" section. This is intentionally
downstream of, and constrained by, the deterministic engine result and
(if available) the Company Evaluation Profile - it is handed facts and
told to turn them into forward-looking action, not to invent new facts
about the candidate or the company (see SUGGESTIONS_SYSTEM).

If this call fails (no API key, network issue), the caller should fall
back to build_fallback_suggestions() below, which is a purely
deterministic bullet-formatting of the same underlying facts - less
polished, but never empty and never wrong.
"""
import json
from app.llm_client import structured_call
from app.schemas import ImprovementSuggestions, JDExtraction
from app.extraction.prompts import SUGGESTIONS_SYSTEM


def generate_suggestions(
    engine_result: dict,
    jd: JDExtraction,
    company_profile: dict | None,
) -> ImprovementSuggestions:
    payload = {
        "role_title": jd.role_title,
        "seniority_level": jd.seniority_level,
        "responsibilities": jd.responsibilities,
        "must_have_skills": jd.must_have_skills,
        "nice_to_have_skills": jd.nice_to_have_skills,
        "missing_must_have_skills": engine_result["missing_keywords"],
        "weak_or_undefended_skills": engine_result["detail"]["skill_coverage"].get("listed_but_undefended_must_have_skills", []),
        "structure_gaps": {
            "missing_sections": engine_result["detail"]["structure"]["missing_sections"],
            "quantification_rate": engine_result["detail"]["structure"]["quantification_rate"],
            "action_verb_start_rate": engine_result["detail"]["structure"]["action_verb_start_rate"],
        },
        "ai_content_risk_level": engine_result["ai_content_risk"]["risk_level"],
        "company_profile": company_profile,  # may be None
    }
    return structured_call(
        system_prompt=SUGGESTIONS_SYSTEM,
        user_prompt="Generate improvement suggestions from this data:\n\n" + json.dumps(payload, indent=2, default=str),
        response_model=ImprovementSuggestions,
        schema_name="improvement_suggestions",
        temperature=0.2,
    )


def build_fallback_suggestions(engine_result: dict, jd: JDExtraction, company_profile: dict | None) -> dict:
    """Pure-Python fallback used only if the LLM call above fails."""
    skills = engine_result["missing_keywords"] + engine_result["detail"]["skill_coverage"].get("listed_but_undefended_must_have_skills", [])
    skills_to_strengthen = [f"Strengthen or add demonstrable experience with: {s}" for s in dict.fromkeys(skills)]

    resume_fixes = []
    struct = engine_result["detail"]["structure"]
    if struct["missing_sections"]:
        resume_fixes.append("Add missing section(s): " + ", ".join(struct["missing_sections"]))
    if struct["quantification_rate"] < 0.4:
        resume_fixes.append("Add measurable outcomes/numbers to more bullets (current quantification rate is low).")
    if struct["action_verb_start_rate"] < 0.5:
        resume_fixes.append("Start more bullets with a strong action verb (built, led, reduced, designed...).")

    soft_tips = []
    if company_profile:
        for p in (company_profile.get("leadership_principles") or [])[:5]:
            soft_tips.append(f"Where true, show evidence of '{p}' in a bullet, not just claim it.")

    return {
        "skills_to_strengthen_or_add": skills_to_strengthen or ["No major skill gaps flagged - focus on structure and evidence depth."],
        "project_ideas": [],
        "soft_skill_alignment_tips": soft_tips,
        "resume_writing_fixes": resume_fixes or ["No major structural issues flagged."],
        "summary_advice": (
            "Auto-generated fallback (LLM suggestions call failed this run). "
            "See skills_to_strengthen_or_add and resume_writing_fixes above."
        ),
    }
