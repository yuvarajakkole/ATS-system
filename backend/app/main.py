"""
FastAPI app. Single evaluation endpoint runs the full pipeline:

  JD text  ----------------> [isolated LLM] JD extraction
  Resume text --------------> [isolated LLM] Resume extraction
  (JD extraction + Resume extraction) -> [isolated LLM] Evidence analysis
  (all of the above, as DATA) -> [deterministic Python] Scoring engine
  (engine output, as DATA) -> [isolated LLM, constrained] Narrative text

Company profile (if a company_name is given) is fetched from cache or
built fresh by the research agent, then fed into the deterministic engine
as data too - never as a "please be nice because it's a big company"
instruction.
"""
import datetime as dt
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app import models
from app.schemas import EvaluateResponse, CompanyResearchRequest
from app.config import settings

from app.extraction.jd_extractor import extract_jd
from app.extraction.resume_extractor import extract_resume
from app.extraction.evidence_analyzer import analyze_evidence
from app.extraction.narrative_generator import generate_narrative
from app.extraction.file_text_extractor import extract_resume_text_from_upload, ExtractionError
from app.extraction.ai_style_judge import judge_ai_writing_style
from app.extraction.suggestions_generator import generate_suggestions, build_fallback_suggestions
from app.scoring.engine import run_scoring_engine
from app.agents.company_research_agent import build_company_profile

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Local ATS Decision Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local single-user tool; tighten if you expose this beyond localhost
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def frontend():
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "model": settings.OPENAI_MODEL}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _get_or_build_company_profile(db: Session, company_name: str, force_refresh: bool = False) -> dict | None:
    if not company_name:
        return None
    norm = _normalize(company_name)
    company = db.query(models.Company).filter_by(normalized_name=norm).first()

    needs_build = force_refresh or company is None
    if company and not force_refresh:
        latest = company.profiles[0] if company.profiles else None
        if latest:
            age_days = (dt.datetime.utcnow() - latest.created_at).days
            needs_build = age_days > settings.COMPANY_PROFILE_MAX_AGE_DAYS
        else:
            needs_build = True

    if not needs_build:
        latest = company.profiles[0]
        return {
            "mission_values": latest.mission_values,
            "leadership_principles": latest.leadership_principles,
            "hiring_process_notes": latest.hiring_process_notes,
            "culture_signals": latest.culture_signals,
            "soft_skills_emphasized": latest.soft_skills_emphasized,
            "ethics_notes": latest.ethics_notes,
            "key_products_or_focus_areas": latest.key_products_or_focus_areas,
            "confidence": latest.confidence,
            "sources": latest.sources,
        }

    profile_data = build_company_profile(company_name)

    if company is None:
        company = models.Company(name=company_name, normalized_name=norm)
        db.add(company)
        db.commit()
        db.refresh(company)

    row = models.CompanyProfile(
        company_id=company.id,
        mission_values=profile_data["mission_values"],
        leadership_principles=profile_data["leadership_principles"],
        hiring_process_notes=profile_data["hiring_process_notes"],
        culture_signals=profile_data["culture_signals"],
        soft_skills_emphasized=profile_data["soft_skills_emphasized"],
        ethics_notes=profile_data["ethics_notes"],
        key_products_or_focus_areas=profile_data.get("key_products_or_focus_areas", []),
        sources=profile_data["sources"],
        confidence=profile_data["confidence"],
    )
    db.add(row)
    db.commit()
    return profile_data


@app.post("/api/companies/research")
def research_company(req: CompanyResearchRequest, db: Session = Depends(get_db)):
    profile = _get_or_build_company_profile(db, req.company_name, force_refresh=req.force_refresh)
    return {"company_name": req.company_name, "profile": profile}


@app.get("/api/companies/{company_name}")
def get_company(company_name: str, db: Session = Depends(get_db)):
    norm = _normalize(company_name)
    company = db.query(models.Company).filter_by(normalized_name=norm).first()
    if not company or not company.profiles:
        raise HTTPException(404, "No stored profile for this company yet. POST /api/companies/research first.")
    latest = company.profiles[0]
    return {
        "company_name": company.name,
        "last_updated": latest.created_at.isoformat(),
        "mission_values": latest.mission_values,
        "leadership_principles": latest.leadership_principles,
        "hiring_process_notes": latest.hiring_process_notes,
        "culture_signals": latest.culture_signals,
        "soft_skills_emphasized": latest.soft_skills_emphasized,
        "ethics_notes": latest.ethics_notes,
        "key_products_or_focus_areas": latest.key_products_or_focus_areas,
        "confidence": latest.confidence,
        "sources": latest.sources,
    }


@app.post("/api/evaluate", response_model=EvaluateResponse)
async def evaluate(
    jd_text: str = Form(..., description="Paste the full job description text"),
    company_name: str | None = Form(None),
    force_company_refresh: bool = Form(False),
    resume_file: UploadFile = File(..., description="Resume as .pdf or .tex"),
    db: Session = Depends(get_db),
):
    if not jd_text.strip():
        raise HTTPException(400, "jd_text is required.")
    if not resume_file.filename:
        raise HTTPException(400, "resume_file is required (.pdf or .tex).")

    file_bytes = await resume_file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded resume file is empty.")

    try:
        resume_text = extract_resume_text_from_upload(resume_file.filename, file_bytes)
    except ExtractionError as e:
        raise HTTPException(422, str(e))

    jd = extract_jd(jd_text)
    resume = extract_resume(resume_text)
    evidence = analyze_evidence(jd, resume)

    try:
        ai_style = judge_ai_writing_style(resume_text).model_dump()
    except Exception:
        ai_style = None  # combine_ai_content_risk() falls back to pattern-only signal

    company_profile = None
    if company_name:
        company_profile = _get_or_build_company_profile(db, company_name, force_company_refresh)

    result = run_scoring_engine(jd, resume, evidence, resume_text, company_profile, ai_style)

    try:
        narrative = generate_narrative(result, jd.role_title)
    except Exception:
        narrative = None  # deterministic strengths/weaknesses lists remain fully usable without this

    try:
        suggestions = generate_suggestions(result, jd, company_profile).model_dump()
    except Exception:
        suggestions = build_fallback_suggestions(result, jd, company_profile)

    row = models.Evaluation(
        company_name=company_name,
        jd_text=jd_text,
        resume_text=resume_text,
        resume_filename=resume_file.filename,
        jd_extraction=jd.model_dump(),
        resume_extraction=resume.model_dump(),
        evidence_analysis=evidence.model_dump(),
        overall_score=result["overall_score"],
        category_scores=result["category_scores"],
        strengths=result["strengths"],
        weaknesses=result["weaknesses"],
        missing_keywords=result["missing_keywords"],
        ai_content_risk=result["ai_content_risk"],
        company_alignment=result["company_alignment"],
        suggestions=suggestions,
        verdict_text=narrative,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return EvaluateResponse(
        evaluation_id=row.id,
        resume_filename=resume_file.filename,
        overall_score=result["overall_score"],
        category_scores=result["category_scores"],
        strengths=result["strengths"],
        weaknesses=result["weaknesses"],
        missing_keywords=result["missing_keywords"],
        skill_breakdown=result["skill_breakdown"],
        ai_content_risk=result["ai_content_risk"],
        company_alignment=result["company_alignment"],
        suggestions=suggestions,
        verdict_text=narrative,
        jd_extraction=jd.model_dump(),
        resume_extraction=resume.model_dump(),
        evidence_analysis=evidence.model_dump(),
    )


@app.get("/api/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db)):
    row = db.query(models.Evaluation).get(evaluation_id)
    if not row:
        raise HTTPException(404, "Evaluation not found.")
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "company_name": row.company_name,
        "resume_filename": row.resume_filename,
        "overall_score": row.overall_score,
        "category_scores": row.category_scores,
        "strengths": row.strengths,
        "weaknesses": row.weaknesses,
        "missing_keywords": row.missing_keywords,
        "ai_content_risk": row.ai_content_risk,
        "company_alignment": row.company_alignment,
        "suggestions": row.suggestions,
        "verdict_text": row.verdict_text,
    }
