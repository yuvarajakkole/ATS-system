# Local ATS Decision Engine

A locally-run ATS that scores a resume against a pasted job description
using a **deterministic scoring engine**, with LLMs used only for
constrained information extraction and evidence-labeling — never as the
thing that produces the final score.

## What this is (and isn't)

- It IS: a rules-based scoring engine (Python, fully readable in
  `backend/app/scoring/`) fed by structured data that an LLM extracted
  from raw text under a strict JSON schema.
- It is NOT: "ask GPT to score this resume 1-100." No prompt anywhere
  produces a number. Every point in the final score traces back to a
  formula in `backend/app/data/scoring_weights.py` and
  `backend/app/scoring/engine.py`.

## Setup (5 minutes)

**Requirements:** Python 3.11+, an OpenAI API key.

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# open .env and paste your OPENAI_API_KEY in

uvicorn app.main:app --reload --port 8000
```

Then open `frontend/index.html` directly in your browser (no build step,
no server needed for the frontend — it's one static file that calls the
backend over `fetch`). If the backend is on a different host/port, change
the "Backend URL" field in the UI.

First run creates `backend/ats_system.db` (SQLite) automatically.

## Verify before you trust it

Per the "don't fill gaps with confident guesses" principle this project
was built under, a few things you should check yourself rather than take
on faith, because they can go stale:

- **`OPENAI_MODEL` in `.env`** — defaults to a placeholder. Check OpenAI's
  current model list and pricing before choosing one; model availability
  changes.
- **Structured Outputs syntax in `app/llm_client.py`** — built against
  OpenAI's `response_format={"type": "json_schema", ...}` API as of early
  2026 training knowledge. Diff against OpenAI's current API reference
  before relying on it in anything important.
- **`app/data/ai_writing_signals.py`** — the AI-writing signal categories
  were reconstructed from search excerpts of Wikipedia's "Signs of AI
  writing" page (it couldn't be fetched directly in this build session),
  not the live page itself. Open the real page and compare before trusting
  it fully — it's explicitly a living document.
- **DuckDuckGo scraping in `app/agents/search_tools.py`** — unofficial,
  no SLA, can break if DuckDuckGo changes their HTML. Fine for personal
  use; swap in SerpAPI/Google CSE (stubs already there, just add the key
  to `.env`) if you want something sturdier.

## Changelog — fixes from initial version

**Company research always showed "low confidence."** Root cause: if the
free web scrape (DuckDuckGo + Wikipedia) came back empty — which happens
often, since DuckDuckGo's unofficial HTML endpoint has no SLA and
regularly rate-limits/blocks automated requests — the code fell back to a
hardcoded empty profile *without ever calling the LLM at all*. Fixed by
always gathering the LLM's own training knowledge about the company as an
additional source (clearly labeled and honestly caveated as unverified/
possibly outdated), so the synthesizer has real material to work with even
when scraping fails. Also hardened the DuckDuckGo scraper itself (fixed a
brittle regex, added a Wikipedia search fallback for name mismatches) as a
best-effort improvement — but reliability no longer *depends* on that
scrape succeeding.

**AI-content-risk detector showed "LOW (0/500 words)" on obviously
AI-flavored text.** Two bugs: (1) the pattern library was missing most
common resume-specific AI clichés ("results-driven professional," "proven
track record," "detail-oriented team player," etc.) — expanded
significantly; (2) the density math normalized hits across the *whole*
document's word count, which silently diluted a short, deliberately
AI-flavored passage inside an otherwise-normal resume down to ~0. Fixed by
combining a length-normalized density signal with an absolute hit-count
signal (worse of the two wins), and by adding a second, independent
signal: an isolated LLM call that judges writing style directly (catches
things a fixed wordlist never will). Both signals and their specific
flagged phrases are now shown in the response.

**Scoring felt like pure keyword matching and didn't explain itself.**
The evidence analyzer now also checks for genuinely adjacent/transferable
skills (e.g. Vue.js experience when React was required) and gives
partial — never full — credit, instead of scoring a missing exact-match
skill as zero regardless of clearly transferable experience. Every
evaluation now returns a full `skill_breakdown` array: per skill, its
evidence strength, the specific reasoning, the resume snippet that
justified it, and (if applicable) the transfer-credit explanation — so a
low score is always traceable to a specific, readable reason rather than
an opaque number. Also fixed: resumes with explicit dates weren't always
getting an experience-years calculation (extractor was too quick to
return null); the extractor is now instructed to do the arithmetic when
dates are present, and the "unknown years" default penalty was softened
and is now always explained in the response rather than applied silently.

**New: "How to improve" suggestions section.** Every evaluation now
returns `suggestions` — skills to strengthen or add, project ideas
grounded in the JD and (if a company was given) that company's actual
products/focus areas, soft-skill alignment tips grounded in the company's
stated leadership principles/culture, and concrete resume-writing fixes.
Falls back to a deterministic bullet list built from the same underlying
facts if the LLM call fails, so it's never empty.

## Running tests / evals

```bash
cd backend
pytest tests/                     # deterministic logic only, no API key needed
python -m app.evals.run_evals     # needs OPENAI_API_KEY, tests extraction + evidence quality
```

## Project layout

```
backend/app/
  extraction/      isolated LLM calls: JD extraction, resume extraction,
                   evidence analysis, company-profile synthesis, narrative
  scoring/         deterministic engine — the only place a score is computed
  agents/          company research agent (web search + Wikipedia -> profile)
  data/            hardcoded rubric weights + AI-writing signal rules
  evals/           lightweight eval harness
frontend/
  index.html       single-file UI, no build step
```

See `PRD.md` for product framing and `ARCHITECTURE.md` for the full data-flow
diagram and the reasoning behind each design decision.

## Known limitations (read this before treating a score as gospel)

- Job description is pasted text; resume is uploaded as a **.pdf or .tex
  file** (parsed server-side with `pdfplumber` / `pylatexenc` — see
  `backend/app/extraction/file_text_extractor.py`). A scanned/image-only
  PDF with no text layer will be rejected with a clear error rather than
  silently producing an empty resume — this tool doesn't do OCR.
- The AI-content-risk score is a bounded pattern-density signal, not a
  proof of anything — see the caveat returned in every response's
  `ai_content_risk.caveat` field, and don't use it as a hard filter.
- Company profiles are only as good as what's publicly findable about a
  company. A well-known company will get a richer profile than a small
  one; a thin profile intentionally lowers its own `confidence` field
  rather than pretending to know more than it does.
- This scores *fit to a JD as extracted*, not overall candidate quality —
  a great engineer whose resume doesn't use the JD's specific vocabulary
  will score lower here, same as with a real ATS.
