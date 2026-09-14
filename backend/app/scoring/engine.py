"""
THE deterministic decision engine. This is the only place a final score
is computed - every function here is plain Python arithmetic over
already-extracted structured data (including LLM-produced labels/
judgments that are passed in as plain dicts/objects). No LLM call happens
in this file.

Per the project's core constraint: LLMs extract and label evidence
upstream; this file judges.
"""
from app.schemas import JDExtraction, ResumeExtraction, EvidenceAnalysis
from app.data.scoring_weights import CATEGORY_WEIGHTS, EXPERIENCE_CURVE, UNKNOWN_EXPERIENCE_DEFAULT_FRACTION
from app.scoring.skill_matcher import score_skill_coverage, score_skill_defense, build_skill_breakdown
from app.scoring.structure_scorer import score_structure
from app.scoring.ai_content_detector import combine_ai_content_risk
from app.scoring.company_standards import score_company_alignment


def _experience_fraction(candidate_years: float | None, required_years: float | None) -> tuple[float, str]:
    if required_years is None or required_years == 0:
        return 1.0, "JD did not state a minimum experience requirement; category not penalized."
    if candidate_years is None:
        return (
            UNKNOWN_EXPERIENCE_DEFAULT_FRACTION,
            f"Could not determine total years of experience from explicit dates in the resume "
            f"(JD requires {required_years}y). Scored at a middling default rather than penalized "
            f"heavily - add clearer Month/Year dates to your experience entries so this can be "
            f"computed precisely.",
        )

    ratio = candidate_years / required_years
    if ratio < 0.5:
        return EXPERIENCE_CURVE["under_0.5x"], f"{candidate_years}y vs {required_years}y required - substantially under."
    if ratio < 0.75:
        return EXPERIENCE_CURVE["under_0.75x"], f"{candidate_years}y vs {required_years}y required - under."
    if ratio < 1.0:
        return EXPERIENCE_CURVE["under_1.0x"], f"{candidate_years}y vs {required_years}y required - close but under."
    if ratio <= 1.5:
        return EXPERIENCE_CURVE["meets_1.0x"], f"{candidate_years}y vs {required_years}y required - meets requirement."
    return EXPERIENCE_CURVE["over_1.5x"], f"{candidate_years}y vs {required_years}y required - significantly overqualified on paper."


def run_scoring_engine(
    jd: JDExtraction,
    resume: ResumeExtraction,
    evidence: EvidenceAnalysis,
    raw_resume_text: str,
    company_profile: dict | None = None,
    ai_style_judgment: dict | None = None,
) -> dict:
    coverage = score_skill_coverage(jd, evidence)
    defense = score_skill_defense(jd, evidence)
    structure = score_structure(resume, raw_resume_text)
    ai_risk = combine_ai_content_risk(raw_resume_text, ai_style_judgment)
    skill_breakdown = build_skill_breakdown(jd, evidence)

    exp_fraction, exp_note = _experience_fraction(
        resume.total_experience_years_stated_or_inferable, jd.min_experience_years
    )

    company_alignment = None
    if company_profile:
        company_alignment = score_company_alignment(company_profile, raw_resume_text)

    # Build the active weight set, redistributing company_alignment's
    # weight proportionally if there's no usable company profile, so an
    # evaluation without a company name isn't unfairly capped below 100.
    weights = dict(CATEGORY_WEIGHTS)
    company_fraction = company_alignment["score_fraction"] if company_alignment else None
    if company_fraction is None:
        removed = weights.pop("company_alignment")
        total_remaining = sum(weights.values())
        weights = {k: v + (v / total_remaining) * removed for k, v in weights.items()}

    fractions = {
        "skill_coverage": coverage["score_fraction"],
        "skill_defense": defense["score_fraction"],
        "experience_relevance": exp_fraction,
        "resume_structure": structure["score_fraction"],
        "ai_content_risk": ai_risk["score_fraction"],
    }
    if company_fraction is not None:
        fractions["company_alignment"] = company_fraction

    category_scores = {
        cat: {
            "weight": round(weights[cat], 2),
            "fraction": fractions[cat],
            "points": round(weights[cat] * fractions[cat], 2),
        }
        for cat in weights
    }
    overall_score = round(sum(c["points"] for c in category_scores.values()))

    strengths, weaknesses = _derive_strengths_weaknesses(
        coverage, defense, structure, ai_risk, exp_fraction, exp_note, company_alignment
    )

    return {
        "overall_score": overall_score,
        "category_scores": category_scores,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "missing_keywords": coverage["missing_must_have_skills"],
        "skill_breakdown": skill_breakdown,
        "ai_content_risk": ai_risk,
        "company_alignment": company_alignment,
        "detail": {
            "skill_coverage": coverage,
            "skill_defense": defense,
            "structure": structure,
            "experience_note": exp_note,
        },
    }


def _derive_strengths_weaknesses(coverage, defense, structure, ai_risk, exp_fraction, exp_note, company_alignment):
    strengths, weaknesses = [], []

    if coverage["must_have_avg"] >= 0.8:
        strengths.append("Strong, well-evidenced coverage of the role's must-have skills.")
    elif coverage["must_have_avg"] < 0.4:
        weaknesses.append("Weak coverage of must-have skills - most are missing or unsupported by evidence.")

    if coverage["missing_must_have_skills"]:
        weaknesses.append(
            "Must-have skills not found anywhere in the resume: "
            + ", ".join(coverage["missing_must_have_skills"])
        )
    if coverage.get("transfer_credited_must_have_skills"):
        names = [t["skill"] for t in coverage["transfer_credited_must_have_skills"]]
        strengths.append(
            "Partial credit given for closely related/transferable experience in place of: "
            + ", ".join(names) + " (see skill_breakdown for details)."
        )
    if coverage["listed_but_undefended_must_have_skills"]:
        weaknesses.append(
            "Must-have skills only listed, with no supporting project/experience detail: "
            + ", ".join(coverage["listed_but_undefended_must_have_skills"])
        )

    if defense["undefended_skills"]:
        weaknesses.append(
            f"{len(defense['undefended_skills'])} skill(s) in the skills section have no evidence "
            "anywhere else in the resume: " + ", ".join(defense["undefended_skills"][:10])
        )
    elif defense.get("total_listed_skills_checked"):
        strengths.append("Every skill listed in the skills section is defended elsewhere in the resume.")

    if structure["missing_sections"]:
        weaknesses.append("Missing expected resume section(s): " + ", ".join(structure["missing_sections"]))
    if structure["quantification_rate"] < 0.25:
        weaknesses.append("Very few bullets include measurable outcomes/numbers.")
    elif structure["quantification_rate"] >= 0.5:
        strengths.append("Good use of quantified, measurable outcomes in bullets.")
    if structure["action_verb_start_rate"] >= 0.6:
        strengths.append("Bullets consistently lead with strong action verbs.")
    elif structure["action_verb_start_rate"] < 0.3:
        weaknesses.append("Many bullets don't open with a strong action verb.")

    if ai_risk["risk_level"] == "high":
        weaknesses.append(
            "High density of generic/formulaic phrasing associated with AI-generated writing - rewrite in your own, specific voice. See ai_content_risk.flags and llm_flagged_snippets for exactly what was flagged."
        )
    elif ai_risk["risk_level"] == "moderate":
        weaknesses.append("Some phrasing patterns commonly associated with AI-generated writing were detected - see ai_content_risk for specifics.")

    if exp_fraction < 0.75:
        weaknesses.append(exp_note)
    if exp_fraction >= 1.0:
        strengths.append("Experience level meets or exceeds the role's stated requirement.")

    if company_alignment and company_alignment.get("score_fraction") is not None:
        if company_alignment["score_fraction"] >= 0.5:
            strengths.append("Resume language overlaps well with this company's stated values/principles.")
        elif company_alignment["score_fraction"] < 0.2:
            weaknesses.append("Little to no overlap between resume language and this company's stated values/principles.")

    return strengths, [w for w in weaknesses if w]
