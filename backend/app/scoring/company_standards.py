"""
Deterministic company-alignment scoring: keyword/theme overlap between the
stored Company Evaluation Profile and the candidate's resume text. This is
intentionally simple (word/phrase overlap, not an LLM judgment) so it stays
fast, free, and auditable for the common case; if you want deeper semantic
matching later, add embeddings here without touching the rest of the engine.

If no company profile is available, this category is excluded from scoring
entirely (see engine.py's weight-redistribution logic) rather than silently
scored as zero - an evaluation shouldn't be punished just because you didn't
provide a company name.
"""
import re


def _normalize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    return set(words)


def score_company_alignment(company_profile: dict, raw_resume_text: str) -> dict:
    resume_words = _normalize(raw_resume_text)

    theme_terms = []
    for field in ("leadership_principles", "soft_skills_emphasized", "culture_signals", "mission_values"):
        for item in company_profile.get(field, []) or []:
            theme_terms.append(item)

    if not theme_terms:
        return {
            "score_fraction": None,
            "note": "Company profile has no usable theme terms; category excluded from scoring.",
            "matched_terms": [],
            "unmatched_terms": [],
        }

    matched, unmatched = [], []
    for term in theme_terms:
        term_words = _normalize(term)
        if term_words and term_words & resume_words:
            matched.append(term)
        else:
            unmatched.append(term)

    fraction = len(matched) / len(theme_terms) if theme_terms else None

    return {
        "score_fraction": round(fraction, 4) if fraction is not None else None,
        "matched_terms": matched,
        "unmatched_terms": unmatched,
        "profile_confidence": company_profile.get("confidence", "low"),
    }
