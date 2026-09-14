# PRD — Local ATS Decision Engine

## Problem

Real ATS platforms are opaque: candidates (and often recruiters) can't see
why a resume scored the way it did. You wanted the opposite — a system you
control, that is brutally honest, shows its work, and treats "the LLM
liked it" as insufficient grounds for a good score.

## Users (v1)

One user: you, evaluating your own resume drafts against real JDs before
applying, and optionally checking how a resume would land at a specific
company given that company's publicly stated values/process.

## Core product decision

> Build a deterministic ATS decision engine where LLMs are used mainly as
> controlled information-extraction and evidence-analysis components.

Everything else in this PRD is downstream of that sentence. Concretely,
it means:

| Stage | Who does it | Can it move the score? |
|---|---|---|
| JD extraction | LLM (isolated, schema-locked) | No — produces facts only |
| Resume extraction | LLM (isolated, schema-locked) | No — produces facts only |
| Skill evidence labeling | LLM (isolated, sees only extracted facts) | No — produces labels only |
| Company profile synthesis | LLM (isolated, sees only gathered web text) | No — produces facts only |
| **Scoring math** | **Plain Python, hardcoded rubric** | **Yes — this IS the score** |
| Narrative feedback text | LLM (constrained to already-computed facts) | No — cannot alter score, strengths, or weaknesses list |

## v1 scope (what's built)

1. Paste a JD + paste a resume → structured extraction of both, isolated
   from each other during extraction.
2. Skill "defense" checking — a skill listed in a skills section only
   counts as weakly evidenced; it must show up with real detail in a
   project/experience bullet to score higher. This directly implements
   your requirement that skills "defend themselves."
3. Deterministic composite score across 6 categories: skill coverage,
   skill defense, experience relevance, resume structure/writing quality,
   AI-content risk, company alignment (weights in
   `backend/app/data/scoring_weights.py`, yours to retune).
4. AI-generated-content risk detector, hardcoded from categories drawn
   from Wikipedia's "Signs of AI writing" page (formulaic transitions,
   negative parallelism, vague weasel attribution, generic puffery, empty
   participle-clause analysis, AI-typical bolded-bullet formatting) — see
   `backend/app/data/ai_writing_signals.py` for the full sourcing note and
   honesty caveats about false-positive risk.
5. Company Research Agent: given a company name, pulls a Wikipedia summary
   + web search snippets + a few fetched pages, and synthesizes a
   structured "Company Evaluation Profile" (mission/values, leadership
   principles, hiring-process notes, culture signals, soft skills
   emphasized, ethics notes) via one schema-locked LLM call. Cached in
   SQLite, versioned, auto-refreshed after a configurable staleness window
   (default 30 days) — because, as you noted, company info changes.
6. Every evaluation is stored (`Evaluation` table) for later reference —
   this is what "candidate history" hooks into if you extend the system
   to compare a candidate's resume drafts over time.
7. A lightweight local eval harness for the extraction/evidence/detection
   logic, runnable on demand.

## Explicitly out of scope for v1 (and why)

- **PDF/DOCX upload & parsing** — a whole reliability surface (layout
  parsing, OCR edge cases) orthogonal to the actual scoring logic you
  asked for. Cut to ship the core engine; the extraction layer doesn't
  care how the text arrived, so this is a clean add-on later
  (`file-reading`-style preprocessing step in front of the same
  `extract_resume()` function).
- **Multi-tenant/auth** — this is a personal local tool.
- **A fully autonomous "agent" that decides what to search next** — the
  company research pipeline is a bounded, inspectable
  search→fetch→synthesize sequence rather than a free-roaming tool-calling
  loop, because a cached profile that gets reused across many future
  evaluations should be built by a predictable process, not something
  that might wander. The tool functions are already isolated
  (`agents/search_tools.py`) if you want to wire up a real
  autonomous loop later.
- **Named third-party eval platform integration** (promptfoo/DeepEval/
  OpenAI Evals) — mentioned as an option in `evals/eval_cases.py` but not
  wired in, since I can't confirm which best fits your workflow or what
  their current setup looks like without you evaluating them directly.

## Success criteria (how you'll know this is working)

- A resume with skills only in a list (no project backing) visibly scores
  lower on `skill_defense` than one with equivalent skills demonstrated in
  project bullets — verified by `tests/test_skill_matcher.py`.
- Obviously formulaic/AI-sounding text scores meaningfully higher risk
  density than plain, specific writing — verified by
  `tests/test_ai_detector.py` and `evals/run_evals.py`.
- Every number in the response is traceable to a specific weight × fraction
  in `category_scores` — nothing is a black-box LLM opinion.
