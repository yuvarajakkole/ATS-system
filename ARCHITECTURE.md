# Architecture

## Request flow: POST /api/evaluate

```
                    ┌─────────────────┐        ┌─────────────────┐
   JD text  ───────►│  JD Extractor   │        │ Resume Extractor│◄────── Resume file (.pdf/.tex)
   (pasted)         │  (isolated LLM) │        │  (isolated LLM) │        → text via
                    └────────┬────────┘        └────────┬────────┘        file_text_extractor.py
                             │  JDExtraction              │  ResumeExtraction
                             │  (structured facts)         │  (structured facts)
                             └───────────┬─────────────────┘
                                         ▼
                              ┌────────────────────┐
                              │  Evidence Analyzer   │   sees both extractions
                              │  (isolated LLM)      │   as DATA, not raw text;
                              └──────────┬───────────┘   labels evidence_strength
                                         │  EvidenceAnalysis   per skill (none/weak/
                                         │                     moderate/strong)
                                         ▼
                    ┌───────────────────────────────────────┐
                    │        DETERMINISTIC SCORING ENGINE     │   <- pure Python,
                    │  skill_matcher | structure_scorer |     │      zero LLM calls.
                    │  ai_content_detector | company_standards│      Combines pattern-
                    │            -> engine.py combines all    │      based AI-risk with
                    └───────────────────┬─────────────────────┘      the LLM style-judge
                                         │  category_scores, overall_score,        below (worse-of-two).
                                         │  strengths[], weaknesses[], skill_breakdown[]
                                         ▼
                    ┌───────────────────┬───────────────────────┐
                    │ Narrative Generator│ Suggestions Generator  │   both constrained:
                    │  (isolated LLM)    │  (isolated LLM)        │   given the finished
                    │  phrases the facts │  turns weaknesses/gaps │   facts, cannot alter
                    │  above; can't alter│  + company profile into│   any score/fact.
                    │  any number        │  actionable advice     │   Both fall back to a
                    └─────────┬──────────┴───────────┬────────────┘   deterministic bullet
                              └────────────┬───────────┘                list if the call fails.
                                           ▼
                                  EvaluateResponse
                                  (+ persisted to SQLite)

Also feeding the engine (isolated, upstream, not shown above for space):
AI Style Judge - given ONLY the resume text, rates writing-style
AI-likelihood (low/moderate/high) with flagged snippets + reasoning. This
is combined deterministically with the hardcoded pattern signal inside
ai_content_detector.py's combine_ai_content_risk() - the worse of the two
signals determines the final risk level shown.
```

## Why isolation, concretely

Each LLM call above is a separate API request with its own system prompt
and only the minimum input it needs:

- The JD extractor never sees the resume. It cannot "extract" a
  requirement to conveniently match what the candidate has.
- The resume extractor never sees the JD. It cannot editorialize about fit.
- The evidence analyzer sees structured facts from both, but is never told
  the JD's must-have/nice-to-have weighting or shown any score — it only
  labels evidence strength per skill against a fixed rubric in its system
  prompt (`EVIDENCE_ANALYST_SYSTEM`).
- The narrative generator is downstream of the *finished* deterministic
  result. It is handed the exact strengths/weaknesses/score and told, in
  its system prompt, that it may not add, remove, or soften any of them —
  it is a phrasing layer, not a second opinion.

This means: if you disagree with a score, the disagreement is always
either "the extraction got a fact wrong" (checkable — every raw
extraction is returned in the API response and shown in the UI's debug
panel) or "the rubric weighting is wrong" (fixable — it's a Python dict
you own, in `data/scoring_weights.py`), never "the model felt like it."

## Company Research Agent flow

```
company_name
     │
     ├──► Wikipedia REST summary API (no key)
     ├──► DuckDuckGo web search x3 queries (no key) ──► fetch top 3 pages
     │
     ▼
raw gathered text (search snippets + fetched page text + wiki summary)
     │
     ▼
Company Profile Synthesizer (ONE isolated, schema-locked LLM call)
     │   forbidden from inventing anything not present in the gathered text;
     │   sets confidence: low/medium/high honestly based on source quality
     ▼
CompanyProfile row (versioned, SQLite) ──► reused by future evaluations
     until COMPANY_PROFILE_MAX_AGE_DAYS elapses, then auto-refreshed
```

This is a bounded pipeline (search → fetch → synthesize), not a freely
autonomous agent loop, so a profile that gets cached and reused across many
future evaluations is built by a predictable, auditable process. The tool
functions in `agents/search_tools.py` are already isolated as
plain callables if you later want to wire them into a real OpenAI
tool-calling loop instead.

## Data model

- `Company` / `CompanyProfile` — versioned company research, many profiles
  per company over time (nothing is overwritten, so you can see what
  changed).
- `Evaluation` — one row per scoring run: stores both raw texts, every
  intermediate extraction, and the final scored result. This is the
  substrate for "candidate history" if you extend the system to compare a
  candidate's resume across multiple drafts/roles.

## Where to extend

- **More resume formats (.docx, plain .txt)**: add another branch to
  `extract_resume_text_from_upload()` in
  `backend/app/extraction/file_text_extractor.py` — everything downstream
  already just takes a plain-text string, regardless of source format.
- **Deeper company-alignment matching**: `scoring/company_standards.py`
  currently does word-overlap; swap in embeddings-based similarity without
  touching anything else in the engine.
- **True autonomous research agent**: replace the linear pipeline in
  `agents/company_research_agent.py` with an OpenAI tool-calling loop over
  the same `search_tools.py` functions.
- **Retune the rubric**: everything scoring-related is one file,
  `data/scoring_weights.py` — change weights, curves, or the action-verb
  list without touching any other code.
