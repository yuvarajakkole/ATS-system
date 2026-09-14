"""
Deterministic resume structure/formatting/writing-quality scoring.
Pure regex/heuristic analysis over the raw resume text + the extracted
structure. No LLM involved anywhere in this file.
"""
import re
from app.schemas import ResumeExtraction
from app.data.scoring_weights import (
    STRUCTURE_CHECKS_WEIGHTS, ACTION_VERBS, REQUIRED_SECTIONS_MIN,
)

NUMBER_PATTERN = re.compile(r"\d")
DATE_PATTERNS = [
    re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}/\d{4}\b"),
    re.compile(r"\b\d{4}\s*-\s*(\d{4}|Present|Current)\b", re.IGNORECASE),
]


def _first_word(bullet: str) -> str:
    stripped = bullet.strip().lstrip("•-*▪◦ ").strip()
    match = re.match(r"[A-Za-z]+", stripped)
    return match.group(0).lower() if match else ""


def score_structure(resume: ResumeExtraction, raw_resume_text: str) -> dict:
    all_bullets = []
    for exp in resume.experience:
        all_bullets.extend(exp.bullets)
    for proj in resume.projects:
        all_bullets.extend(proj.description_bullets)

    # 1. required sections present
    sections = {s.lower() for s in resume.sections_present}
    missing_sections = REQUIRED_SECTIONS_MIN - sections
    sections_score = 1.0 - (len(missing_sections) / len(REQUIRED_SECTIONS_MIN))

    # 2. action verb start rate
    if all_bullets:
        verb_hits = sum(1 for b in all_bullets if _first_word(b) in ACTION_VERBS)
        action_verb_score = verb_hits / len(all_bullets)
    else:
        action_verb_score = 0.0

    # 3. quantification rate (bullets containing a digit / %/ metric)
    if all_bullets:
        quant_hits = sum(1 for b in all_bullets if NUMBER_PATTERN.search(b))
        quant_score = quant_hits / len(all_bullets)
    else:
        quant_score = 0.0

    # 4. consistent date formatting - check the raw text uses one dominant pattern
    date_format_hits = [len(p.findall(raw_resume_text)) for p in DATE_PATTERNS]
    total_date_hits = sum(date_format_hits)
    if total_date_hits == 0:
        date_consistency_score = 0.5  # can't tell; neutral, not punished hard
    else:
        dominant = max(date_format_hits)
        date_consistency_score = dominant / total_date_hits

    # 5. bullet length sanity: not empty, not a wall of text (rough char bounds)
    if all_bullets:
        sane = sum(1 for b in all_bullets if 25 <= len(b.strip()) <= 220)
        bullet_sanity_score = sane / len(all_bullets)
    else:
        bullet_sanity_score = 0.0

    weighted = (
        sections_score * STRUCTURE_CHECKS_WEIGHTS["required_sections_present"]
        + action_verb_score * STRUCTURE_CHECKS_WEIGHTS["action_verb_start_rate"]
        + quant_score * STRUCTURE_CHECKS_WEIGHTS["quantification_rate"]
        + date_consistency_score * STRUCTURE_CHECKS_WEIGHTS["consistent_date_formatting"]
        + bullet_sanity_score * STRUCTURE_CHECKS_WEIGHTS["bullet_length_sanity"]
    )

    return {
        "score_fraction": round(weighted, 4),
        "missing_sections": sorted(missing_sections),
        "action_verb_start_rate": round(action_verb_score, 3),
        "quantification_rate": round(quant_score, 3),
        "date_consistency": round(date_consistency_score, 3),
        "bullet_length_sanity": round(bullet_sanity_score, 3),
        "total_bullets_analyzed": len(all_bullets),
    }
