"""
Deterministic skill coverage + "defense" scoring.
Consumes the LLM's evidence_analysis output as pure DATA (skill name +
evidence_strength enum + transfer-credit labels) - all point math happens
here in plain Python, not inside a prompt.
"""
from app.schemas import JDExtraction, EvidenceAnalysis
from app.data.scoring_weights import (
    EVIDENCE_STRENGTH_POINTS, MUST_HAVE_VS_NICE_TO_HAVE_RATIO, TRANSFER_CREDIT_POINTS,
)


def _skill_points(e) -> float:
    base = EVIDENCE_STRENGTH_POINTS[e.evidence_strength]
    if e.evidence_strength == "none" and e.related_skill_transfer:
        return TRANSFER_CREDIT_POINTS
    return base


def score_skill_coverage(jd: JDExtraction, evidence: EvidenceAnalysis) -> dict:
    ev_by_skill = {e.skill.lower(): e for e in evidence.skill_evidence}

    def avg_points(skills: list[str]) -> float:
        if not skills:
            return 1.0  # no requirement of this type => don't penalize
        total = 0.0
        for s in skills:
            e = ev_by_skill.get(s.lower())
            total += _skill_points(e) if e else 0.0
        return total / len(skills)

    must_avg = avg_points(jd.must_have_skills)
    nice_avg = avg_points(jd.nice_to_have_skills)

    fraction = (
        must_avg * MUST_HAVE_VS_NICE_TO_HAVE_RATIO["must_have"]
        + nice_avg * MUST_HAVE_VS_NICE_TO_HAVE_RATIO["nice_to_have"]
    )

    must_have_lower = {s.lower() for s in jd.must_have_skills}
    missing = [
        e.skill for e in evidence.skill_evidence
        if e.evidence_strength == "none" and not e.related_skill_transfer and e.skill.lower() in must_have_lower
    ]
    transfer_credited = [
        {"skill": e.skill, "via": e.transfer_explanation}
        for e in evidence.skill_evidence
        if e.evidence_strength == "none" and e.related_skill_transfer and e.skill.lower() in must_have_lower
    ]
    weak_but_present = [
        e.skill for e in evidence.skill_evidence
        if e.evidence_strength == "weak" and e.skill.lower() in must_have_lower
    ]

    return {
        "score_fraction": round(fraction, 4),
        "must_have_avg": round(must_avg, 4),
        "nice_to_have_avg": round(nice_avg, 4),
        "missing_must_have_skills": missing,
        "listed_but_undefended_must_have_skills": weak_but_present,
        "transfer_credited_must_have_skills": transfer_credited,
    }


def score_skill_defense(jd: JDExtraction, evidence: EvidenceAnalysis) -> dict:
    """
    Separate from raw coverage: this specifically penalizes the pattern
    you described - "skills mentioned in the skills list must defend
    themselves elsewhere". A skill that's listed but has zero supporting
    evidence anywhere in experience/projects is a red flag distinct from
    "doesn't know the skill at all".
    """
    listed_skills = [e for e in evidence.skill_evidence if e.mentioned_in_skills_section]
    if not listed_skills:
        return {"score_fraction": 1.0, "undefended_skills": [], "note": "No dedicated skills section detected to evaluate."}

    undefended = [e.skill for e in listed_skills if not e.evidence_found_elsewhere]
    defended_fraction = 1 - (len(undefended) / len(listed_skills))

    return {
        "score_fraction": round(defended_fraction, 4),
        "undefended_skills": undefended,
        "total_listed_skills_checked": len(listed_skills),
    }


def build_skill_breakdown(jd: JDExtraction, evidence: EvidenceAnalysis) -> list[dict]:
    """Per-skill audit trail returned to the user so every score is explainable."""
    must_have_lower = {s.lower() for s in jd.must_have_skills}
    breakdown = []
    for e in evidence.skill_evidence:
        breakdown.append({
            "skill": e.skill,
            "requirement_type": "must_have" if e.skill.lower() in must_have_lower else "nice_to_have",
            "evidence_strength": e.evidence_strength,
            "mentioned_in_skills_section": e.mentioned_in_skills_section,
            "evidence_found_elsewhere": e.evidence_found_elsewhere,
            "related_skill_transfer": e.related_skill_transfer,
            "transfer_explanation": e.transfer_explanation,
            "evidence_snippet": e.evidence_snippet,
            "reasoning": e.reasoning,
            "points_awarded": round(_skill_points(e), 2),
        })
    # must-haves first, then by weakest evidence first (most actionable)
    strength_order = {"none": 0, "weak": 1, "moderate": 2, "strong": 3}
    breakdown.sort(key=lambda b: (b["requirement_type"] != "must_have", strength_order[b["evidence_strength"]]))
    return breakdown
