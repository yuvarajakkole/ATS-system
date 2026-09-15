# Local ATS Decision Engine — Complete Product Documentation

**Version:** 0.2 (post-fixes: company research, AI-content detection, skill transparency, suggestions)
**Scope:** single-user, local-first ATS evaluation tool
**Status:** working codebase, runs locally with an OpenAI API key

---

## 1. What This Product Is

A locally-run Applicant Tracking System (ATS) that scores a candidate's
resume against a pasted job description (JD), the way a real corporate
ATS + a skeptical human reviewer would — but with the scoring logic fully
visible, fully yours, and never a black box.

You give it two things:
- A **job description** (pasted text)
- A **resume** (uploaded as `.pdf` or `.tex`)

Optionally, a **company name**, which triggers a research agent that
builds a profile of that company's values, leadership principles, hiring
process, and products — used to score how well the resume's language and
soft-skill signals align with what that specific company says it wants in
employees.

It returns:
- A score out of 100, broken into 6 weighted categories
- A skill-by-skill breakdown explaining exactly why each point was
  awarded or withheld
- Strengths, weaknesses, and missing must-have keywords
- An AI-generated-content risk assessment
- A company-alignment score (if a company was given)
- A set of concrete, grounded suggestions for how to actually improve

---

## 2. The Problem This Solves

Real ATS platforms are opaque. A candidate gets rejected and never learns
why. Recruiters themselves often don't fully trust or understand their
own ATS's scoring. Two specific failure modes this product was built to
avoid:

1. **"Ask an LLM to score this resume 1–100."** This is unreliable,
   inconsistent between runs, easy to flatter/game, and gives no
   auditable reason for the number. An LLM asked to "score fairly" will
   drift toward generosity, inconsistency, or reward surface polish over
   substance.
2. **Naive keyword matching.** Real ATS systems (and lazy implementations
   of this idea) just check whether JD keywords appear literally in the
   resume text. This rewards keyword-stuffing and penalizes genuinely
   qualified candidates who phrase things differently, or who have
   closely transferable experience in a different but related tool.

The product's answer to both: **separate the "reading comprehension"
problem from the "scoring" problem.** Let an LLM do what LLMs are
actually good at — extracting structured facts from messy natural-language
text, and making nuanced, evidence-based judgments about a single, narrow
question. Let plain, auditable Python do what Python is good at —
consistent, reproducible, re-weightable arithmetic.

---

## 3. Core Idea / Design Philosophy

> **Do not build an "LLM resume scorer." Build a deterministic ATS
> decision engine where LLMs are used mainly as controlled
> information-extraction and evidence-analysis components.**

Every design decision in this product traces back to that sentence.
Concretely:

| Pipeline stage | Who does it | Can it move the final score? |
|---|---|---|
| JD extraction (role, requirements, must/nice-to-have skills) | LLM — isolated, schema-locked | No — produces facts only |
| Resume extraction (experience, projects, skills, dates) | LLM — isolated, schema-locked | No — produces facts only |
| Skill evidence labeling ("is this skill actually demonstrated?") | LLM — isolated, sees only extracted facts | No — produces labels only |
| AI-writing-style judgment | LLM — isolated, resume text only | No — produces a label + flagged snippets only |
| Company profile synthesis | LLM — isolated, sees only gathered research material | No — produces facts only |
| **Scoring math (all 6 categories + overall)** | **Plain Python, hardcoded rubric** | **Yes — this IS the score** |
| Narrative feedback text | LLM — constrained to already-computed facts | No — cannot alter score, strengths, or weaknesses |
| Improvement suggestions | LLM — constrained to already-computed facts | No — advisory only, doesn't touch the score |

**Isolation** is the other load-bearing concept. Every LLM call is a
separate API request with the minimum input it needs and nothing else:

- The JD extractor never sees the resume — it can't "helpfully" shape
  requirements to match a candidate.
- The resume extractor never sees the JD — it can't editorialize about
  fit while extracting facts.
- The evidence analyzer sees structured facts from both, but is never
  told which skills are weighted more heavily, never shown a
  running score, and is explicitly instructed not to soften or round up.
- Every system prompt for every isolated call contains an explicit
  "brutally honest, no sycophancy, be skeptical by default" instruction.

The practical payoff: **if you disagree with a score, the disagreement is
always one of two things** — "the extraction got a fact wrong" (checkable,
since every raw extraction is returned in the API response) or "the
rubric weighting is wrong" (fixable, since it's a plain Python dict you
own) — never "the model felt like it."

---

## 4. End-to-End Process (Input → Output)

```
 INPUT                          PROCESSING                         OUTPUT
┌─────────────┐
│ JD text      │──┐
│ (pasted)     │  │
└─────────────┘  │          ┌───────────────────┐
                  ├─────────▶│  JD Extractor      │──┐
┌─────────────┐  │          │  (isolated LLM)    │  │
│ Resume file  │  │          └───────────────────┘  │
│ (.pdf/.tex)  │──┼──┐                               │
└─────────────┘  │  │       ┌───────────────────┐   │
                  │  └──────▶│ Resume Extractor   │──┤
┌─────────────┐  │           │ (isolated LLM)     │  │
│ Company name │  │           └───────────────────┘  │
│ (optional)   │──┘                                   ▼
└─────────────┘                              ┌──────────────────┐
      │                                       │ Evidence Analyzer │
      │                                       │  (isolated LLM)   │
      │                                       └─────────┬────────┘
      ▼                                                 │
┌──────────────────┐                                    │
│ Company Research   │                                  │
│ Agent (wiki+search  │                                 │
│ +LLM prior knowledge)│                                │
└─────────┬──────────┘                                  │
          │                                              │
          ▼                                              ▼
   Company Evaluation Profile ──────────────▶  DETERMINISTIC SCORING ENGINE
   (cached in SQLite, versioned)               (pure Python — the only place
                                                 a score is computed)
                                                          │
                              ┌───────────────────────────┼───────────────────────┐
                              ▼                           ▼                       ▼
                     Narrative Generator         Suggestions Generator    AI Style Judge
                     (isolated LLM, phrases       (isolated LLM, turns     (isolated LLM,
                      the fixed facts, cannot      gaps into actionable    resume text only,
                      alter any number)            advice, cannot alter    feeds into the AI-
                                                    the score)              risk category above)
                              │                           │
                              └─────────────┬─────────────┘
                                             ▼
                                     EvaluateResponse
                                (JSON, + persisted to SQLite)
```

### 4.1 Step-by-step

1. **You paste a JD and upload a resume** (`.pdf` or `.tex`). The file is
   parsed server-side (`pdfplumber` for PDF, `pylatexenc` for LaTeX) into
   plain text before anything else happens — the rest of the pipeline
   never knows or cares what format the resume arrived in.
2. **JD Extraction** turns the pasted JD into structured data: role
   title, seniority, must-have skills, nice-to-have skills,
   responsibilities, minimum experience, education requirements, domain
   keywords. Nothing is invented — if a number isn't explicitly stated,
   it's returned as `null`, not guessed.
3. **Resume Extraction** turns the resume text into structured data:
   sections present, verbatim skills-list items, experience entries (with
   bullets), project entries (with bullets and tech used), education,
   certifications, and total years of experience (computed from explicit
   dates when present).
4. **Evidence Analysis** takes both structured extractions and, for every
   skill the JD asks for, labels how well the resume actually demonstrates
   it: `none` / `weak` / `moderate` / `strong`, with a written reason and
   a resume snippet as proof. It also checks for **transferable skills**
   — e.g., if PostgreSQL was required but not present, but the resume
   shows strong MySQL experience, that's flagged as partial (never full)
   credit, with an explanation.
5. **AI Style Judgment** independently reads the resume text and rates
   how likely its *phrasing* (not its truthfulness) reads as
   AI-generated, flagging specific suspicious snippets with reasons.
6. **Company Research** (only if you provided a company name) gathers a
   Wikipedia summary, best-effort web search results, and — always,
   regardless of whether the web material comes through — the LLM's own
   training knowledge about the company, clearly labeled as unverified.
   All of this is synthesized into a structured "Company Evaluation
   Profile": mission/values, leadership principles, hiring process notes,
   culture signals, soft skills emphasized, ethics notes, and key
   products/focus areas. This profile is cached in SQLite and only
   rebuilt after a configurable staleness window (default 30 days).
7. **The Deterministic Scoring Engine** takes everything above as plain
   data and computes 6 category scores, weights them, and produces the
   final 0–100 score — entirely in Python, with zero LLM calls in this
   step. This is the only place a number is decided.
8. **Narrative Generation** and **Suggestions Generation** are two final,
   constrained LLM calls that turn the finished, fixed facts into
   readable prose feedback and actionable advice, respectively. Neither
   can change a score, invent a new weakness, or invent a new skill gap
   — they only rephrase/act on what the engine already decided.
9. Everything is returned as one JSON response and persisted to SQLite
   for later reference.

---

## 5. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Backend framework | **FastAPI** (Python) | async-friendly, automatic OpenAPI docs, clean request validation |
| LLM | **OpenAI API** (`openai` Python SDK), model configurable via env var | user-supplied API key; Structured Outputs (JSON-schema-constrained responses) used for every extraction call |
| Data validation / schemas | **Pydantic v2** | doubles as both API request/response validation AND the literal JSON-schema contract sent to the LLM |
| Database | **SQLite** via **SQLAlchemy** | zero-setup local persistence; swappable to Postgres via one connection-string change |
| PDF parsing | **pdfplumber** | reliable text extraction, handles most real-world resume PDFs |
| LaTeX parsing | **pylatexenc** (`LatexNodes2Text`) | converts `.tex` source to plain text without needing a full LaTeX compile |
| Web research (no API key needed) | **Wikipedia REST API** + **DuckDuckGo HTML search** (best-effort scrape) | free, no-signup company research; pluggable slot for SerpAPI/Google CSE if you add a key |
| HTTP client | **httpx** | used for all outbound research requests |
| Frontend | **Single-file HTML/CSS/vanilla JS** | zero build step — open the file in a browser, no npm/webpack needed |
| Testing | **pytest** | pure-logic unit tests that need zero API key or network access |
| Eval harness | Custom lightweight Python harness (`app/evals/`) | schema-conformance + regression checks for extraction and detection quality |

**Why no heavier framework (LangChain, LlamaIndex, etc.)?** The
LLM-call surface here is intentionally small and each call has one clear
job with a locked-down schema — a raw `openai` client call is more
transparent and easier to audit than routing it through an abstraction
layer, which matters a lot for a system whose entire value proposition is
"you can see exactly what happened and why."

---

## 6. AI Concepts Used (and Why Each One)

### 6.1 Structured Outputs (JSON-schema-constrained generation)
Every extraction/labeling call uses OpenAI's `response_format={"type":
"json_schema", ...}` mode, generated directly from Pydantic models
(`llm_client.py`). This means the model is *structurally incapable* of
returning anything other than the exact shape you defined — no
free-text rambling, no missing fields, no "sure, here's the JSON:"
preamble to strip out. This is the main technical lever against
hallucinated or malformed extraction.

### 6.2 Isolation / minimal-context prompting
Each call receives only the exact inputs it needs, never the full
conversation history or unrelated context. This is a deliberate anti-bias
measure: the JD extractor can't skew requirements toward a candidate it
hasn't seen; the resume extractor can't invent qualifications the JD
implies; the evidence analyzer isn't told what score would be
"convenient." Isolation is enforced structurally (separate API calls with
scoped prompts), not just requested via instruction.

### 6.3 Temperature-zero, rubric-locked judgment calls
Extraction and evidence-labeling calls run at `temperature=0.0` — this
isn't about "creativity," it's about **consistency**: the same
resume/JD pair should produce (near-)identical extractions run to run.
The evidence analyst's rubric (what counts as `none`/`weak`/`moderate`/
`strong`) is spelled out explicitly in the system prompt with concrete
examples, rather than left to the model's judgment of "how good is this,"
specifically so the label is reproducible and defensible.

### 6.4 Anti-sycophancy system prompting
Every system prompt in this product explicitly instructs the model not
to be encouraging, not to round up, not to soften a weak finding. This
matters because LLMs have a well-documented tendency toward
agreeableness/flattery when evaluating someone's work — left unchecked,
this would systematically inflate every score.

### 6.5 Multi-signal combination (defense in depth)
The AI-content-risk score is deliberately **not** a single signal. It
combines (a) a hardcoded, fully-explainable pattern/phrase detector with
(b) an independent LLM style judgment — and takes the *more severe* of
the two. This is a standard defense-in-depth idea applied to LLM output:
a fixed wordlist alone would miss anything not on the list; an LLM alone
would be an unauditable black box. Together, each covers the other's
blind spot, and every hit from both signals is shown to the user with the
specific text that triggered it.

### 6.6 Transferable/adjacent-skill reasoning
Rather than binary exact-keyword-match-or-nothing, the evidence analyzer
is explicitly permitted (and instructed to be conservative about) crediting
genuinely adjacent skills — but the scoring math in Python only ever gives
this **partial** credit, fixed at a lower value than the real skill would
earn. This is a case of the LLM contributing nuanced judgment while the
deterministic layer keeps that judgment from ever fully substituting for
the real requirement.

### 6.7 Grounded synthesis over free generation
The company research synthesizer and the suggestions generator are both
explicitly forbidden from inventing content not present in their given
input material. The company synthesizer sets its own `confidence` field
honestly (low/medium/high) based on how much real material it had. The
suggestions generator must ground project ideas in the company's actual
stated products, not generic advice — and returns an empty list rather
than padding with platitudes when it has nothing specific to say.

---

## 7. Evals Concepts

"Evals" here means: **a repeatable way to check that the
extraction/labeling/detection logic is behaving correctly**, independent
of any one-off manual test.

### 7.1 Two tiers of testing

**Tier 1 — pure-logic unit tests (`backend/tests/`, run via `pytest`).**
No API key or network needed. These test the deterministic Python layer
directly with hand-constructed inputs:
- Does a missing must-have skill actually get flagged?
- Does an undefended (listed-but-unproven) skill get flagged by the
  defense check specifically?
- Does genuinely AI-flavored text score higher risk density than plain,
  specific writing — and does empty input not crash anything?
- Does transferable-skill credit land strictly between "no credit" and
  "full credit"?

**Tier 2 — LLM-call evals (`backend/app/evals/`, run via `python -m
app.evals.run_evals`).** Needs an API key. These check the
*LLM-dependent* parts of the pipeline against hand-authored cases:
- JD extraction schema-conformance (did it return a valid role title and
  a non-empty must-have skill list from a clear sample JD?)
- Skill-defense judgment on two clear-cut synthetic resumes — one where
  skills are only listed (should be flagged undefended), one where the
  same skills are backed by concrete project bullets (should pass).
- AI-content-risk pattern detection on a deliberately formulaic paragraph
  versus a deliberately plain, specific one.

### 7.2 Why this two-tier split matters
The deterministic scoring math (the actual point of the "decision engine"
design) can be tested exhaustively, quickly, and for free — it's just
Python, so `pytest` covers it like any other codebase. The LLM-dependent
steps can't be tested with the same certainty (model output isn't
perfectly deterministic even at temperature 0, and costs money/time per
run), so they get a smaller, targeted regression suite aimed at "does this
obviously-right case still come out obviously right after I changed a
prompt" rather than exhaustive coverage.

### 7.3 What's intentionally NOT included
No integration with a named third-party eval platform (promptfoo,
DeepEval, OpenAI Evals) — the harness here is a lightweight,
dependency-free starting point. If you want heavier tooling, those are
reasonable next steps, but their current setup/APIs should be verified
directly rather than assumed, since eval tooling in this space moves fast.

---

## 8. The Scoring Rubric (Full Detail)

All of this lives in one file, `backend/app/data/scoring_weights.py` —
by design, so it's auditable and yours to retune.

### 8.1 Category weights (sum to 100)

| Category | Weight | What it measures |
|---|---|---|
| Skill coverage | 35 | Weighted average of evidence strength across must-have (75% weight within this category) and nice-to-have (25%) skills |
| Skill defense | 15 | Penalizes skills listed in a skills section with zero supporting evidence elsewhere in the resume |
| Experience relevance | 15 | Candidate's computed years of experience vs. the JD's stated minimum, on a curve that penalizes under-experience harder than mild over-qualification |
| Resume structure | 15 | Required sections present, action-verb usage rate, quantification rate, date-format consistency, bullet-length sanity |
| AI content risk | 10 | Inverse of the combined pattern+LLM AI-writing-style risk signal |
| Company alignment | 10 | Keyword/theme overlap between the resume and the company's stated values/leadership principles/culture signals (excluded and its weight redistributed if no company name was given) |

### 8.2 Evidence-strength → points mapping

| Evidence strength | Points |
|---|---|
| none | 0.0 |
| weak (listed only, no support) | 0.35 |
| moderate (mentioned in a bullet, shallow) | 0.7 |
| strong (concrete, specific, interview-defensible) | 1.0 |
| transferable/adjacent skill found instead | 0.45 (fixed, never higher regardless of how strong the adjacent skill's own evidence is) |

### 8.3 Experience curve

| Ratio (candidate years / required years) | Score fraction |
|---|---|
| < 0.5x | 0.15 |
| < 0.75x | 0.45 |
| < 1.0x | 0.75 |
| meets 1.0x–1.5x | 1.0 |
| > 1.5x (significantly overqualified) | 0.9 |
| unknown (dates not parseable) | 0.55 default, always explained in the response, never a silent penalty |

---

## 9. Input / Output Contract

### 9.1 `POST /api/evaluate` — the main endpoint

**Input** (multipart form, not JSON — because a file is involved):

| Field | Type | Required | Notes |
|---|---|---|---|
| `jd_text` | form string | yes | full pasted job description |
| `resume_file` | file upload | yes | `.pdf` or `.tex` only |
| `company_name` | form string | no | triggers company research/caching |
| `force_company_refresh` | form bool | no | bypasses the cached profile |

**Output** (JSON):

```json
{
  "evaluation_id": 42,
  "resume_filename": "jane_doe_resume.pdf",
  "overall_score": 71,
  "category_scores": {
    "skill_coverage": {"weight": 35.0, "fraction": 0.82, "points": 28.7},
    "skill_defense":  {"weight": 15.0, "fraction": 0.6,  "points": 9.0},
    "...": "..."
  },
  "strengths": ["Strong, well-evidenced coverage of the role's must-have skills.", "..."],
  "weaknesses": ["Must-have skills only listed, with no supporting detail: Kubernetes", "..."],
  "missing_keywords": ["Terraform"],
  "skill_breakdown": [
    {
      "skill": "PostgreSQL",
      "requirement_type": "must_have",
      "evidence_strength": "none",
      "related_skill_transfer": true,
      "transfer_explanation": "Strong MySQL experience shown; closely adjacent relational DB skill.",
      "reasoning": "PostgreSQL is not mentioned anywhere in the resume...",
      "points_awarded": 0.45
    }
  ],
  "ai_content_risk": {
    "risk_level": "low",
    "density_per_500_words": 0.4,
    "flags": ["..."],
    "llm_overall_likelihood": "low",
    "llm_flagged_snippets": ["..."],
    "caveat": "Combines a hardcoded phrase/pattern signal with an isolated LLM writing-style judgment..."
  },
  "company_alignment": {"score_fraction": 0.6, "matched_terms": ["..."], "unmatched_terms": ["..."]},
  "suggestions": {
    "skills_to_strengthen_or_add": ["..."],
    "project_ideas": ["..."],
    "soft_skill_alignment_tips": ["..."],
    "resume_writing_fixes": ["..."],
    "summary_advice": "..."
  },
  "verdict_text": "...",
  "jd_extraction": {"...": "full structured JD data"},
  "resume_extraction": {"...": "full structured resume data"},
  "evidence_analysis": {"...": "full per-skill evidence data"}
}
```

### 9.2 Other endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness check, returns configured model name |
| `POST /api/companies/research` | explicitly trigger/refresh a company profile |
| `GET /api/companies/{company_name}` | read a cached company profile |
| `GET /api/evaluations/{id}` | read back a past evaluation from SQLite |

---

## 10. Errors — What Can Go Wrong, and How It's Handled

| Failure | Where | Behavior |
|---|---|---|
| Missing/invalid OpenAI API key | any LLM call | Raises a clear `RuntimeError` at the point of use (`llm_client.py`), not a silent empty result |
| Uploaded file isn't `.pdf`/`.tex` | `file_text_extractor.py` | Rejected with `422` and a specific message naming the filename and accepted types |
| PDF has no extractable text (scanned/image-only) | `file_text_extractor.py` | Rejected with `422` and an explicit explanation — this tool does not do OCR — rather than silently scoring an empty resume |
| `.tex` file fails to parse | `file_text_extractor.py` | Rejected with `422` and the parser's error message |
| File larger than 8MB | `file_text_extractor.py` | Rejected before any parsing is attempted |
| Web search / Wikipedia fetch fails (network, blocked scrape) | `agents/search_tools.py` | Fails silently *for that one source* (returns empty), but does not abort company research — see next row |
| **All** company research sources fail (web AND LLM prior-knowledge call) | `company_research_agent.py` | Only then falls back to an explicit empty profile with `confidence: "low"` — this is now the genuinely-rare case, not the default outcome |
| Narrative generation call fails | `main.py` | Caught, `verdict_text` is `null` in the response — the deterministic `strengths`/`weaknesses` lists remain fully usable without it |
| Suggestions generation call fails | `main.py` | Caught, falls back to a deterministic bullet-list built from the same underlying facts (`build_fallback_suggestions`) — never empty, never blocks the response |
| AI style judgment call fails | `main.py` | Caught, `ai_content_risk` falls back to the pattern-only signal with `llm_judgment_available: false` explicitly shown |
| Malformed/non-schema-conforming LLM output | `llm_client.py` | Raises rather than guessing — a failed extraction surfaces as an error, not a quietly wrong score |

**Design principle behind all of the above:** distinguish between
*optional enrichment* (company research corroboration, narrative prose,
suggestions, AI style judgment) — which degrade gracefully to a
still-useful fallback if they fail — and *core inputs* (the JD text, the
resume file, the extraction/evidence calls that the score itself depends
on) — which fail loudly and specifically, because a wrong or silently-empty
core result is worse than an error message.

---

## 11. Known Limitations (Honest Accounting)

- **Resume input is `.pdf`/`.tex` only** — no `.docx` support yet
  (straightforward to add: one more branch in
  `file_text_extractor.py`, everything downstream already just takes
  plain text).
- **AI-content-risk is a bounded signal, not proof.** Both the pattern
  list and the LLM judgment can be wrong in either direction; the
  response always includes an explicit caveat about this and shows its
  work (flagged phrases/snippets) rather than issuing a bare verdict.
- **DuckDuckGo scraping has no SLA** and can break or get blocked at any
  time — it's now a best-effort corroboration source, not something the
  system depends on, but it's still worth knowing it's fundamentally
  unofficial.
- **Company profile quality depends on public findability.** A
  well-known company will get a richer profile than an obscure one; a
  thin profile is supposed to self-report lower confidence rather than
  pretend to know more than it does.
- **This scores fit to the JD as extracted**, not overall candidate
  quality in the abstract — a great engineer whose resume doesn't share
  vocabulary with the JD will score lower here, same as with a real ATS.
  The transferable-skill logic and the suggestions section exist
  specifically to soften this without pretending the gap doesn't exist.
- **Single-user, local tool** — no auth, no multi-tenant support, SQLite
  rather than a production database. This is intentional for the stated
  use case (personal job-search tool), not an oversight.

---

## 12. How This Helps You (Practically)

- **You see exactly why a score is what it is** — every category is
  traceable to a specific weight × fraction, every skill has a written
  reason and a resume snippet backing it up, and nothing is a black-box
  "the AI said so."
- **You can retune it** — the entire rubric is one Python file. Think
  skill coverage should matter more than structure? Change one number.
  Think the AI-content-risk category shouldn't count toward the score at
  all? Set its weight to 0 (the engine auto-redistributes the rest).
- **You get a second opinion that won't just flatter you** — every prompt
  in this system is explicitly instructed to be skeptical and not round
  up, which is the opposite of what happens when you casually ask a
  general-purpose chat assistant "how's my resume?"
- **You get company-specific prep**, not just role-specific — if you
  provide a company name, the suggestions are grounded in what that
  company actually says it values and actually builds, not generic
  "be a team player" advice.
- **It runs entirely on your machine** with your own API key — your
  resume and target companies aren't sent anywhere except to OpenAI (for
  the extraction/judgment calls) and to the public web/Wikipedia (for
  company research lookups you explicitly trigger).

---

## 13. Where to Extend Next (Natural Next Steps)

- Add `.docx` resume support (one function in `file_text_extractor.py`).
- Swap the company-alignment word-overlap matcher for embeddings-based
  semantic similarity (`scoring/company_standards.py`) without touching
  anything else.
- Replace the linear company-research pipeline with a true OpenAI
  tool-calling agent loop over the same isolated search tools
  (`agents/search_tools.py`), if you want the model deciding what to
  search next rather than a fixed query sequence.
- Wire in a heavier eval framework (promptfoo/DeepEval/OpenAI Evals) once
  you've confirmed which fits your workflow.
- Add a "resume version history" comparison view using the already-stored
  `Evaluation` rows — compare how your score changes as you iterate.
