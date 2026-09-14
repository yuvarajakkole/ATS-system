"""
DB models.

Company + CompanyProfile store the "Company Evaluation Profile" the
research agent builds, so it only has to be built once per company and
then reused (and periodically refreshed) rather than re-scraped on every
evaluation.

Evaluation stores every scoring run so a candidate's history for a given
JD/company is auditable later (you asked the system to consider "candidate
history" too — this table is what that references over time).
"""
import datetime as dt
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.db import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True, nullable=False)
    normalized_name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    profiles = relationship("CompanyProfile", back_populates="company", order_by="CompanyProfile.created_at.desc()")


class CompanyProfile(Base):
    """
    A versioned snapshot of a company's evaluation profile. Versioned
    (rather than overwritten) because company values/process claims
    genuinely change, and you may want to see what changed and when.
    """
    __tablename__ = "company_profiles"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    mission_values = Column(JSON, default=list)
    leadership_principles = Column(JSON, default=list)
    hiring_process_notes = Column(JSON, default=list)
    culture_signals = Column(JSON, default=list)
    soft_skills_emphasized = Column(JSON, default=list)
    ethics_notes = Column(JSON, default=list)
    key_products_or_focus_areas = Column(JSON, default=list)
    sources = Column(JSON, default=list)  # list of {url, title, retrieved_at, type}
    confidence = Column(String, default="low")  # low/medium/high — set by the agent based on source count/quality

    company = relationship("Company", back_populates="profiles")


class Evaluation(Base):
    """One scoring run: a specific resume against a specific JD (and
    optionally a company profile)."""
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    company_name = Column(String, nullable=True)
    jd_text = Column(Text, nullable=False)
    resume_text = Column(Text, nullable=False)
    resume_filename = Column(String, nullable=True)

    jd_extraction = Column(JSON, nullable=False)
    resume_extraction = Column(JSON, nullable=False)
    evidence_analysis = Column(JSON, nullable=False)

    overall_score = Column(Integer, nullable=False)
    category_scores = Column(JSON, nullable=False)
    strengths = Column(JSON, default=list)
    weaknesses = Column(JSON, default=list)
    missing_keywords = Column(JSON, default=list)
    ai_content_risk = Column(JSON, nullable=False)
    company_alignment = Column(JSON, nullable=True)
    suggestions = Column(JSON, nullable=True)
    verdict_text = Column(Text, nullable=True)
