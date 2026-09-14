import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas import JDExtraction, EvidenceAnalysis, SkillEvidence
from app.scoring.skill_matcher import score_skill_coverage, score_skill_defense


def _jd():
    return JDExtraction(
        role_title="Backend Engineer", seniority_level="mid", min_experience_years=3,
        must_have_skills=["Python", "PostgreSQL", "Docker"], nice_to_have_skills=["Kubernetes"],
        responsibilities=[], education_requirements=[], domain_keywords=[],
    )


def _evidence(strengths: dict, listed: set[str], found_elsewhere: set[str]):
    return EvidenceAnalysis(skill_evidence=[
        SkillEvidence(
            skill=skill, mentioned_in_skills_section=skill in listed,
            evidence_found_elsewhere=skill in found_elsewhere,
            evidence_strength=strength, reasoning="test",
        )
        for skill, strength in strengths.items()
    ])


def test_missing_must_have_skill_is_flagged():
    jd = _jd()
    evidence = _evidence(
        {"Python": "strong", "PostgreSQL": "none", "Docker": "weak", "Kubernetes": "none"},
        listed={"Python", "Docker"}, found_elsewhere={"Python"},
    )
    coverage = score_skill_coverage(jd, evidence)
    assert "PostgreSQL" in coverage["missing_must_have_skills"]
    assert coverage["must_have_avg"] < 1.0


def test_undefended_listed_skill_is_flagged_by_defense_check():
    jd = _jd()
    evidence = _evidence(
        {"Python": "strong", "PostgreSQL": "weak", "Docker": "weak", "Kubernetes": "none"},
        listed={"Python", "PostgreSQL", "Docker"}, found_elsewhere={"Python"},
    )
    defense = score_skill_defense(jd, evidence)
    assert "PostgreSQL" in defense["undefended_skills"]
    assert "Docker" in defense["undefended_skills"]
    assert "Python" not in defense["undefended_skills"]


def test_related_skill_transfer_gives_partial_credit_not_full_credit():
    """A missing exact skill with a genuinely adjacent/transferable skill
    found instead should score better than a flatly-missing skill, but
    still worse than actually having the required skill."""
    jd = _jd()

    evidence_no_transfer = EvidenceAnalysis(skill_evidence=[
        SkillEvidence(skill="Python", mentioned_in_skills_section=True, evidence_found_elsewhere=True, evidence_strength="strong", reasoning="t"),
        SkillEvidence(skill="PostgreSQL", mentioned_in_skills_section=False, evidence_found_elsewhere=False, evidence_strength="none", reasoning="t"),
        SkillEvidence(skill="Docker", mentioned_in_skills_section=False, evidence_found_elsewhere=False, evidence_strength="none", reasoning="t"),
        SkillEvidence(skill="Kubernetes", mentioned_in_skills_section=False, evidence_found_elsewhere=False, evidence_strength="none", reasoning="t"),
    ])
    evidence_with_transfer = EvidenceAnalysis(skill_evidence=[
        SkillEvidence(skill="Python", mentioned_in_skills_section=True, evidence_found_elsewhere=True, evidence_strength="strong", reasoning="t"),
        SkillEvidence(
            skill="PostgreSQL", mentioned_in_skills_section=False, evidence_found_elsewhere=False,
            evidence_strength="none", related_skill_transfer=True,
            transfer_explanation="Resume shows strong MySQL experience, a closely adjacent relational DB.",
            reasoning="t",
        ),
        SkillEvidence(skill="Docker", mentioned_in_skills_section=False, evidence_found_elsewhere=False, evidence_strength="none", reasoning="t"),
        SkillEvidence(skill="Kubernetes", mentioned_in_skills_section=False, evidence_found_elsewhere=False, evidence_strength="none", reasoning="t"),
    ])

    cov_no_transfer = score_skill_coverage(jd, evidence_no_transfer)
    cov_with_transfer = score_skill_coverage(jd, evidence_with_transfer)

    assert cov_with_transfer["score_fraction"] > cov_no_transfer["score_fraction"]
    assert cov_with_transfer["score_fraction"] < 1.0  # never full credit for a substitute
    assert "PostgreSQL" not in cov_with_transfer["missing_must_have_skills"]
    assert cov_with_transfer["transfer_credited_must_have_skills"][0]["skill"] == "PostgreSQL"
