"""
AI-generated-content RISK signal. Two independent signals are combined:

1. PATTERN SIGNAL (this file, pure Python, zero LLM calls) - matches
   against app/data/ai_writing_signals.py. Deterministic, free, fast,
   fully explainable (every hit is a literal string/regex you can read).

2. LLM STYLE-JUDGMENT SIGNAL (produced upstream by
   extraction/ai_style_judge.py, an ISOLATED LLM call that sees only the
   resume text and is told to judge writing style, not truth or content -
   see AI_STYLE_JUDGE_SYSTEM). This exists because a fixed phrase list can
   never cover every way AI-generated text can read as generic; the model
   catches patterns a wordlist can't. This file never calls the LLM itself
   - it only accepts the judgment as already-produced DATA and combines it
   deterministically with the pattern signal (worse-of-the-two-signals wins).

IMPORTANT HONESTY NOTE (surfaced in the output, not just this comment):
this produces a bounded, explainable RISK score with the specific
flagged phrases/snippets shown - never a binary "AI-written: yes/no"
claim. Treat this as "worth a second look" signal, not a verdict.
"""
from app.data.ai_writing_signals import AI_WRITING_SIGNAL_CATEGORIES, compile_patterns

_COMPILED = compile_patterns()

_LEVEL_RANK = {"low": 0, "moderate": 1, "high": 2}
_LLM_LEVEL_TO_FRACTION = {"low": 1.0, "moderate": 0.5, "high": 0.15}


def _pattern_signal(raw_resume_text: str) -> dict:
    text = raw_resume_text
    flags = []
    total_hits = 0
    total_weighted_hits = 0.0
    distinct_categories_hit = 0

    for key, cat in AI_WRITING_SIGNAL_CATEGORIES.items():
        patterns = _COMPILED[key]
        hits = []
        if cat["is_regex"]:
            for pat in patterns:
                hits.extend(m.group(0) for m in pat.finditer(text))
        else:
            lowered = text.lower()
            for p in patterns:
                if p in lowered:
                    hits.append(p)

        if hits:
            distinct_categories_hit += 1
            total_hits += len(hits)
            weighted = len(hits) * cat["weight"]
            total_weighted_hits += weighted
            flags.append({
                "category": key,
                "label": cat["label"],
                "hit_count": len(hits),
                "examples": hits[:6],
                "weight": cat["weight"],
            })

    word_count = max(len(text.split()), 1)
    # Normalized-by-length signal: good for judging a whole long document.
    density_per_500_words = (total_weighted_hits / word_count) * 500

    # Absolute signal: good for catching a short, deliberately AI-flavored
    # passage inside an otherwise-normal, longer document, where the
    # density signal alone would get diluted away to near-zero. We take
    # the WORSE (more severe) of the two below rather than only trusting
    # density, which is the bug this replaces.
    if total_hits == 0:
        abs_level = "low"
    elif total_hits <= 2 and distinct_categories_hit <= 1:
        abs_level = "low"
    elif total_hits <= 5 or distinct_categories_hit <= 2:
        abs_level = "moderate"
    else:
        abs_level = "high"

    if density_per_500_words < 1.0:
        density_level = "low"
    elif density_per_500_words < 3.0:
        density_level = "moderate"
    else:
        density_level = "high"

    risk_level = abs_level if _LEVEL_RANK[abs_level] >= _LEVEL_RANK[density_level] else density_level
    score_fraction = max(0.0, 1.0 - min(total_weighted_hits / 6.0, 1.0))

    return {
        "score_fraction": round(score_fraction, 4),
        "risk_level": risk_level,
        "density_per_500_words": round(density_per_500_words, 2),
        "total_hits": total_hits,
        "distinct_categories_hit": distinct_categories_hit,
        "flags": flags,
    }


def combine_ai_content_risk(raw_resume_text: str, llm_style_judgment: dict | None = None) -> dict:
    """
    llm_style_judgment (if provided) is the .model_dump() of an
    AIStyleJudgment: {overall_likelihood: low/moderate/high,
    flagged_snippets: [{snippet, reason}], reasoning: str}
    """
    pattern = _pattern_signal(raw_resume_text)

    if not llm_style_judgment:
        pattern["llm_judgment_available"] = False
        pattern["caveat"] = (
            "Pattern-based signal only (LLM style-judgment unavailable this run - "
            "check your OPENAI_API_KEY / network). No individual pattern proves AI "
            "authorship; treat as a prompt to look closer, not a verdict."
        )
        return pattern

    llm_level = llm_style_judgment.get("overall_likelihood", "low")
    llm_fraction = _LLM_LEVEL_TO_FRACTION.get(llm_level, 1.0)

    final_level = pattern["risk_level"] if _LEVEL_RANK[pattern["risk_level"]] >= _LEVEL_RANK[llm_level] else llm_level
    final_fraction = min(pattern["score_fraction"], llm_fraction)

    return {
        "score_fraction": round(final_fraction, 4),
        "risk_level": final_level,
        "density_per_500_words": pattern["density_per_500_words"],
        "total_hits": pattern["total_hits"],
        "distinct_categories_hit": pattern["distinct_categories_hit"],
        "flags": pattern["flags"],
        "llm_judgment_available": True,
        "llm_overall_likelihood": llm_level,
        "llm_flagged_snippets": llm_style_judgment.get("flagged_snippets", []),
        "llm_reasoning": llm_style_judgment.get("reasoning", ""),
        "caveat": (
            "Combines a hardcoded phrase/pattern signal with an isolated LLM "
            "writing-style judgment (the worse of the two determines the risk "
            "level shown). Neither signal proves AI authorship on its own; "
            "human writers exhibit some of these habits too. Treat as a prompt "
            "to look closer, not a verdict."
        ),
    }


# Backward-compatible name for anything still importing the old function directly.
def detect_ai_content_risk(raw_resume_text: str) -> dict:
    result = _pattern_signal(raw_resume_text)
    result["caveat"] = (
        "Pattern-based signal only. No individual pattern proves AI authorship; "
        "human writers exhibit some of these habits too. Treat as a prompt to "
        "look closer, not a verdict."
    )
    return result
