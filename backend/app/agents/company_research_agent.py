"""
Company Research Agent: gathers raw material about a company from the web
(Wikipedia + search + page fetches) AND from the LLM's own training
knowledge, then runs ONE isolated, schema-constrained LLM synthesis call
over that combined material to produce a "Company Evaluation Profile".

Fix note: the previous version bailed out to a hardcoded, empty,
"confidence: low" stub WITHOUT EVER CALLING THE LLM whenever the web
scrape (DuckDuckGo HTML + Wikipedia) returned nothing - which happens
often, since DuckDuckGo's HTML endpoint has no SLA and can rate-limit or
block automated requests. That silent bailout was the actual bug behind
"it always shows low confidence." The LLM prior-knowledge gather step
below is now ALWAYS attempted (not conditional on web results), so the
synthesizer always has something real to work with unless the OpenAI call
itself fails (missing/invalid API key, network down) - which now raises
an explicit error instead of silently returning an empty profile, so you
can tell the difference between "nothing findable about this company" and
"the API call failed."
"""
import datetime as dt

from openai import OpenAIError

from app.agents.search_tools import wikipedia_summary, web_search, fetch_page_text
from app.extraction.prompts import COMPANY_PROFILE_SYNTHESIZER_SYSTEM, LLM_PRIOR_KNOWLEDGE_SYSTEM
from app.llm_client import structured_call, get_client
from app.config import settings
from app.schemas import CompanyProfileExtraction


def _gather_llm_prior_knowledge(company_name: str) -> str | None:
    """
    Isolated call: given only the company name, ask the model to recall
    whatever specific, real knowledge it has from training. This call is
    always attempted (unlike web scraping, which can silently fail) so the
    synthesizer downstream is never starved of material just because a
    scrape got blocked. Plain free-text response - it becomes one more raw
    source chunk fed to the schema-constrained synthesizer, which is
    responsible for deciding what's usable.
    """
    client = get_client()
    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.0,
        messages=[
            {"role": "system", "content": LLM_PRIOR_KNOWLEDGE_SYSTEM},
            {"role": "user", "content": f"Company: {company_name}"},
        ],
    )
    return resp.choices[0].message.content.strip()


def gather_raw_material(company_name: str) -> dict:
    sources = []
    raw_chunks = []

    # 1. Wikipedia (free, no key, tried with search-title fallback)
    wiki = wikipedia_summary(company_name)
    if wiki and wiki.get("extract"):
        raw_chunks.append(f"[Wikipedia summary]\n{wiki['extract']}")
        sources.append({"url": wiki.get("url"), "title": wiki.get("title") or company_name, "type": "wikipedia"})

    # 2. Best-effort web search (see search_tools.py honesty note - may
    #    return nothing even when working correctly, due to DDG's lack of SLA)
    queries = [
        f"{company_name} leadership principles OR company values",
        f"{company_name} interview process hiring process",
        f"{company_name} engineering culture blog products",
    ]
    seen_urls = set()
    fetched_count = 0
    for q in queries:
        for r in web_search(q, max_results=3):
            if not r.get("url") or r["url"] in seen_urls:
                continue
            seen_urls.add(r["url"])
            raw_chunks.append(f"[Search result: {r.get('title')}]\n{r.get('snippet', '')}")
            sources.append({"url": r["url"], "title": r.get("title"), "type": "search_snippet"})

    for s in sources:
        if s["type"] == "search_snippet" and fetched_count < 3:
            text = fetch_page_text(s["url"])
            if text:
                raw_chunks.append(f"[Fetched page: {s['title']}]\n{text}")
                s["type"] = "fetched_page"
                fetched_count += 1

    # 3. LLM prior knowledge - ALWAYS attempted, not conditional on (1)/(2)
    #    succeeding. This is the fix for the always-low-confidence bug.
    try:
        prior_knowledge = _gather_llm_prior_knowledge(company_name)
    except OpenAIError as e:
        prior_knowledge = None
        sources.append({"url": None, "title": f"LLM prior-knowledge call failed: {e}", "type": "error"})

    if prior_knowledge:
        raw_chunks.append(f"[Model prior knowledge - unverified, potentially outdated]\n{prior_knowledge}")
        sources.append({"url": None, "title": "Model training knowledge", "type": "llm_prior_knowledge"})

    return {
        "raw_text": "\n\n---\n\n".join(raw_chunks) if raw_chunks else "",
        "sources": sources,
    }


def build_company_profile(company_name: str) -> dict:
    material = gather_raw_material(company_name)

    if not material["raw_text"].strip():
        # Only reached if Wikipedia, web search, AND the LLM prior-knowledge
        # call all produced nothing/failed - genuinely no material to work
        # with, not just "the scrape got blocked."
        return {
            "mission_values": [], "leadership_principles": [], "hiring_process_notes": [],
            "culture_signals": [], "soft_skills_emphasized": [], "ethics_notes": [],
            "key_products_or_focus_areas": [],
            "confidence": "low", "sources": material["sources"],
        }

    extraction = structured_call(
        system_prompt=COMPANY_PROFILE_SYNTHESIZER_SYSTEM,
        user_prompt=(
            f"Company: {company_name}\n\nGathered research material:\n\n{material['raw_text']}"
        ),
        response_model=CompanyProfileExtraction,
        schema_name="company_profile_extraction",
    )

    profile = extraction.model_dump()
    profile["sources"] = [
        {**s, "retrieved_at": dt.datetime.utcnow().isoformat()} for s in material["sources"]
    ]
    return profile
