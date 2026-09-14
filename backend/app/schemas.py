"""
Pydantic schemas. These serve two purposes:
1. API request/response validation (FastAPI).
2. The literal JSON-schema contract handed to the LLM via OpenAI's
   Structured Outputs (response_format=json_schema), so the model is
   constrained to return exactly this shape — this is the main lever
   against hallucinated/free-text extraction.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ---------- JD extraction ----------

class JDSkill(BaseModel):
    name: str
    required: bool = Field(description="True if must-have, False if nice-to-have/preferred")


class JDExtraction(BaseModel):
    company_name: Optional[str] = Field(default=None, description="Only if explicitly stated in the JD text")
    role_title: str
    seniority_level: str = Field(description="one of: intern, junior, mid, senior, lead, staff, principal, unknown")
    min_experience_years: Optional[float] = Field(default=None, description="numeric minimum years of experience if stated, else null")
    must_have_skills: list[str]
    nice_to_have_skills: list[str]
    responsibilities: list[str]
    education_requirements: list[str]
    domain_keywords: list[str] = Field(description="domain/industry terms an aligned resume would naturally use")


# ---------- Resume extraction ----------

class ResumeExperienceEntry(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    bullets: list[str]


class ResumeProjectEntry(BaseModel):
    name: Optional[str] = None
    description_bullets: list[str]
    tech_used: list[str]


class ResumeExtraction(BaseModel):
    candidate_name: Optional[str] = None
    sections_present: list[str] = Field(description="e.g. contact, summary, skills, experience, projects, education, certifications")
    skills_section_items: list[str] = Field(description="raw items listed in a dedicated skills section, verbatim")
    experience: list[ResumeExperienceEntry]
    projects: list[ResumeProjectEntry]
    education: list[str]
    certifications: list[str]
    total_experience_years_stated_or_inferable: Optional[float] = Field(
        default=None, description="only if directly computable from explicit dates; else null — do not guess"
    )


# ---------- Evidence analysis (skill "defense") ----------

class SkillEvidence(BaseModel):
    skill: str
    mentioned_in_skills_section: bool
    evidence_found_elsewhere: bool
    evidence_strength: str = Field(description="one of: none, weak, moderate, strong")
    evidence_snippet: Optional[str] = Field(default=None, description="short quote/paraphrase of the resume text that shows the evidence, or null")
    related_skill_transfer: bool = Field(
        default=False,
        description="True only if the exact skill itself is absent, but the resume shows a widely-recognized, closely adjacent/transferable skill (e.g. Vue.js experience when React was required, MySQL when Postgres was required)."
    )
    transfer_explanation: Optional[str] = Field(
        default=None, description="If related_skill_transfer is True, exactly which adjacent skill was found and why it transfers. Null otherwise."
    )
    reasoning: str


class EvidenceAnalysis(BaseModel):
    skill_evidence: list[SkillEvidence]


# ---------- Company profile extraction ----------

class CompanyProfileExtraction(BaseModel):
    mission_values: list[str]
    leadership_principles: list[str]
    hiring_process_notes: list[str]
    culture_signals: list[str]
    soft_skills_emphasized: list[str]
    ethics_notes: list[str]
    key_products_or_focus_areas: list[str] = Field(
        description="What the company actually builds/sells/works on - product lines, internal platforms, core business areas. Used to ground project suggestions for candidates."
    )
    confidence: str = Field(description="low, medium, or high, based on how much reliable source material was available")


# ---------- AI writing-style judgment (isolated, style only, not scoring) ----------

class FlaggedSnippet(BaseModel):
    snippet: str
    reason: str


class AIStyleJudgment(BaseModel):
    overall_likelihood: str = Field(description="one of: low, moderate, high - likelihood this text's PHRASING reads as AI-generated")
    flagged_snippets: list[FlaggedSnippet]
    reasoning: str


# ---------- Improvement suggestions ----------

class ImprovementSuggestions(BaseModel):
    skills_to_strengthen_or_add: list[str] = Field(description="Specific, JD-grounded skills the candidate is missing or under-evidenced on, with a short why")
    project_ideas: list[str] = Field(description="Concrete project ideas grounded in the role and, if available, the company's actual products/focus areas")
    soft_skill_alignment_tips: list[str] = Field(description="How to demonstrate the company's stated leadership principles/culture traits in the resume, if a company profile was available")
    resume_writing_fixes: list[str] = Field(description="Concrete structure/writing fixes: quantification, action verbs, formatting")
    summary_advice: str = Field(description="2-4 sentences: the single highest-leverage thing to fix to meaningfully move the score")


# ---------- API request/response ----------

class EvaluateRequest(BaseModel):
    """Kept for reference/programmatic JSON use if you want it later.
    The live API endpoint now takes multipart form data (jd_text + a
    resume_file upload) instead of this JSON body - see main.py."""
    jd_text: str
    resume_text: str
    company_name: Optional[str] = None
    force_company_refresh: bool = False


class EvaluateResponse(BaseModel):
    evaluation_id: int
    resume_filename: Optional[str] = None
    overall_score: int
    category_scores: dict
    strengths: list[str]
    weaknesses: list[str]
    missing_keywords: list[str]
    skill_breakdown: list[dict] = Field(default_factory=list, description="Per-skill evidence + reasoning, so score changes are auditable")
    ai_content_risk: dict
    company_alignment: Optional[dict] = None
    suggestions: Optional[dict] = None
    verdict_text: Optional[str] = None
    jd_extraction: dict
    resume_extraction: dict
    evidence_analysis: dict


class CompanyResearchRequest(BaseModel):
    company_name: str
    force_refresh: bool = False
