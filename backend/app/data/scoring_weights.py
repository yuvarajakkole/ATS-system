"""
The entire scoring rubric lives here, as plain numbers, on purpose:
this is the "isolated, deterministic, auditable" part of the system.
Nothing in here is produced by an LLM. Change these to match how YOU
actually want to weight a resume - they're opinionated starting points,
not a scientifically validated formula.
"""

# Top-level category weights must sum to 100.
CATEGORY_WEIGHTS = {
    "skill_coverage": 35,      # must-have / nice-to-have skill coverage, weighted by evidence strength
    "skill_defense": 15,       # penalty-oriented: skills listed but not defended anywhere
    "experience_relevance": 15,  # years of experience vs JD requirement
    "resume_structure": 15,    # sections present, bullet hygiene, quantification, action verbs
    "ai_content_risk": 10,     # inverse of AI-writing-signal density (lower risk = higher score)
    "company_alignment": 10,   # overlap with the Company Evaluation Profile, if available
}

EVIDENCE_STRENGTH_POINTS = {
    "none": 0.0,
    "weak": 0.35,
    "moderate": 0.7,
    "strong": 1.0,
}

# Applied when the exact skill is absent (evidence_strength="none") but the
# evidence analyst found a genuinely adjacent/transferable skill instead
# (SkillEvidence.related_skill_transfer=True). Deliberately less than
# "moderate" credit for the real skill - it's a signal of fast ramp-up
# potential, not proof of the actual required skill.
TRANSFER_CREDIT_POINTS = 0.45

MUST_HAVE_VS_NICE_TO_HAVE_RATIO = {
    "must_have": 0.75,   # 75% of skill_coverage score comes from must-have skills
    "nice_to_have": 0.25,
}

EXPERIENCE_CURVE = {
    # ratio of (candidate_years / required_years) -> score fraction (0-1)
    # under-experienced is penalized harder than being somewhat over-experienced
    "under_0.5x": 0.15,
    "under_0.75x": 0.45,
    "under_1.0x": 0.75,
    "meets_1.0x": 1.0,
    "over_1.5x": 0.9,   # mild penalty for significant overqualification (JD-fit signal, not a judgment of worth)
}

# Used only when the resume extractor could not compute total experience
# years from explicit dates (returned null) AND the JD states a minimum.
# This is a middling, not punitive, default - the point is to avoid
# silently crushing a resume's score just because dates weren't in a
# format the extractor could parse; the engine also surfaces this
# explicitly in the response so it's never a silent penalty.
UNKNOWN_EXPERIENCE_DEFAULT_FRACTION = 0.55

STRUCTURE_CHECKS_WEIGHTS = {
    "required_sections_present": 0.30,   # contact, experience, education, skills at minimum
    "action_verb_start_rate": 0.20,      # bullets starting with a strong verb
    "quantification_rate": 0.25,         # bullets containing a number/metric
    "consistent_date_formatting": 0.10,
    "bullet_length_sanity": 0.15,        # not empty, not walls of text

    # each sub-weight above is fraction of resume_structure category
}

ACTION_VERBS = {
    "led", "built", "designed", "developed", "implemented", "architected",
    "optimized", "reduced", "increased", "improved", "launched", "shipped",
    "automated", "created", "deployed", "migrated", "refactored", "scaled",
    "analyzed", "mentored", "managed", "drove", "delivered", "engineered",
    "trained", "researched", "authored", "integrated", "debugged", "owned",
    "spearheaded", "streamlined", "established", "initiated", "resolved",
}

REQUIRED_SECTIONS_MIN = {"experience", "education", "skills"}
