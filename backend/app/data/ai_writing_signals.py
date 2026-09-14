"""
Hardcoded AI-generated-writing signal rules.

Source and honesty note: Wikipedia's "Signs of AI writing" page
(en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing, maintained by
WikiProject AI Cleanup) could not be fetched directly during this build,
so the STRUCTURAL categories below (formulaic transitions, negative
parallelism, empty participle clauses, vague attribution, puffery,
formatting tells) were reconstructed from search-result excerpts of that
page. The VOCABULARY list (ai_cliche_vocabulary + resume_specific_cliches)
is a broader, independently compiled set of words/phrases repeatedly cited
across AI-detection writeups and widely observed in ChatGPT/LLM output as
of my training data - not a verbatim copy of any single source. Open the
live Wikipedia page yourself and diff it against this file before treating
either list as authoritative; both are living, maintained-by-observation
lists that will drift out of date.

Wikipedia's own page is explicit that NONE of these signs individually
prove AI authorship - they are descriptive tendencies, not proof. This
module produces a bounded RISK SIGNAL with visible reasoning, never a
pass/fail verdict, and should never be the sole basis for rejecting a
candidate. See ai_content_detector.py for how this combines with an
isolated LLM style-judgment for a second, more semantically aware signal.
"""
import re

# category_key -> {label, weight, patterns: [str], is_regex: bool}
AI_WRITING_SIGNAL_CATEGORIES = {
    "formulaic_transition_phrases": {
        "label": "Formulaic AI-style transition/summary phrases",
        "weight": 1.0,
        "patterns": [
            "in summary", "in conclusion", "overall,", "it is worth noting",
            "it's worth noting", "in today's fast-paced", "in the ever-evolving",
            "in the world of", "plays a crucial role", "plays a vital role",
            "stands as a testament", "serves as a testament", "moreover,",
            "furthermore,", "additionally,", "notably,", "importantly,",
            "essentially,", "fundamentally,", "ultimately,", "as a testament to",
        ],
        "is_regex": False,
    },
    "negative_parallelism": {
        "label": "Negative parallelism ('not X, but Y' / 'It's not just X, it's Y')",
        "weight": 1.2,
        "patterns": [
            r"\bnot (just|only) [a-z ]{2,40}, (it'?s|but) ",
            r"\bisn'?t (just|only) [a-z ]{2,40}, (it'?s|but) ",
        ],
        "is_regex": True,
    },
    "empty_participle_analysis": {
        "label": "Empty trailing '-ing' analysis clauses (e.g. 'ensuring success', 'fostering collaboration')",
        "weight": 0.8,
        "patterns": [
            r",\s(ensuring|highlighting|showcasing|demonstrating|reflecting|underscoring|solidifying|fostering|driving|delivering|enabling)\s[a-z]",
        ],
        "is_regex": True,
    },
    "vague_weasel_attribution": {
        "label": "Vague/weasel attribution with no real source",
        "weight": 0.9,
        "patterns": [
            "industry experts agree", "many believe", "some argue",
            "it is widely believed", "studies show that", "research suggests that",
        ],
        "is_regex": False,
    },
    "ai_cliche_vocabulary": {
        "label": "Generic AI-favored vocabulary/buzzwords",
        "weight": 0.7,
        "patterns": [
            "delve into", "delve deeper", "boast a", "boasts a", "tapestry of",
            "realm of", "navigate the", "navigating the", "foster collaboration",
            "fostering", "harness the power", "harnessing", "leverage", "leveraging",
            "robust and scalable", "seamless", "seamlessly", "dynamic and innovative",
            "cutting-edge", "state-of-the-art", "paramount", "meticulous",
            "meticulously", "unwavering", "showcase", "showcasing", "underscore",
            "underscores", "embark on", "embarking on", "multifaceted", "intricate",
            "profound", "pivotal", "invaluable", "noteworthy", "commendable",
            "unparalleled", "transformative", "holistic approach", "synergy",
            "synergies", "paradigm shift", "game-changer", "game-changing",
            "elevate", "empower", "empowering", "streamline", "streamlining",
            "optimize", "revolutionize", "unlock the potential", "unlock potential",
            "comprehensive understanding", "landscape of", "ever-evolving landscape",
        ],
        "is_regex": False,
    },
    "resume_specific_cliches": {
        "label": "Generic resume-cliche self-description (common LLM-generated filler)",
        "weight": 0.9,
        "patterns": [
            "results-driven", "results-oriented", "proven track record",
            "extensive experience", "detail-oriented professional",
            "detail oriented professional", "excellent communication skills",
            "strong communication skills", "team player", "self-motivated",
            "hard-working professional", "passionate about", "dedicated professional",
            "committed to excellence", "strong ability to", "highly skilled",
            "highly motivated", "driving impactful outcomes", "drive impactful outcomes",
            "deliver high-quality", "delivering high-quality", "cross-functional teams",
            "wide range of skills", "diverse skill set", "solid foundation in",
            "adept at", "proficient in a wide", "thrive in a fast-paced",
        ],
        "is_regex": False,
    },
    "puffery_significance": {
        "label": "Generic puffery about significance/impact with no concrete detail",
        "weight": 0.8,
        "patterns": [
            "revolutionize", "seamlessly integrate", "robust and scalable solution",
            "leveraging synergies", "holistic approach",
        ],
        "is_regex": False,
    },
    "hedge_stacking": {
        "label": "Stacked hedging/boilerplate qualifiers",
        "weight": 0.5,
        "patterns": [
            "it is important to note that", "it should be noted that",
            "it is essential to understand that",
        ],
        "is_regex": False,
    },
    "formatting_tells": {
        "label": "AI-typical formatting (bolded-title bullet lists used as prose substitute)",
        "weight": 0.6,
        "patterns": [
            r"^\s*[\*\-]\s*\*\*[^*]{3,40}\*\*:",  # "- **Scalability:** ..." style bullets
        ],
        "is_regex": True,
    },
    "adjective_triplet_stacking": {
        "label": "Stacked adjective triplets (e.g. 'innovative, scalable, and efficient') - common LLM rhythm",
        "weight": 0.6,
        "patterns": [
            r"\b\w+, \w+,? and \w+ (solutions?|systems?|approach(es)?|outcomes?|results?|technologies|capabilities)\b",
        ],
        "is_regex": True,
    },
}

# Note re: em dashes. Multiple sources (including discussion around the
# Wikipedia page itself) point out that em-dash frequency is a weak,
# model/era-specific signal, not a reliable tell (one cited comparison
# has Mark Twain using em dashes MORE per 1,000 words than GPT-4.1, and
# some open models essentially never use them). Deliberately NOT included
# as a scored signal here - included only as a documented non-signal so
# nobody re-adds it without re-reading this note.
KNOWN_WEAK_OR_REJECTED_SIGNALS = [
    "em_dash_frequency — historically unreliable, do not score on this alone",
]


def compile_patterns():
    compiled = {}
    for key, cat in AI_WRITING_SIGNAL_CATEGORIES.items():
        if cat["is_regex"]:
            compiled[key] = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in cat["patterns"]]
        else:
            compiled[key] = cat["patterns"]
    return compiled
