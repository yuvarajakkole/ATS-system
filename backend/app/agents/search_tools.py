"""
No-API-key-required research tools for the Company Research Agent, plus a
pluggable slot for paid providers if you add API keys later.

Honesty note: DuckDuckGo's HTML endpoint (html.duckduckgo.com) is an
unofficial, scrape-based integration with no SLA - it can rate-limit,
block, or silently return nothing for automated requests, and its markup
can change at any time. Treat it as best-effort corroboration, never as
the sole source the company research agent depends on (see
company_research_agent.py - the LLM's own prior knowledge is now always
gathered too, specifically so a blocked/broken scrape doesn't leave the
agent with nothing at all).
"""
import re
import httpx
from urllib.parse import quote, unquote, urlparse, parse_qs
from app.config import settings

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def wikipedia_summary(company_name: str) -> dict | None:
    """
    Uses Wikipedia's official REST summary API - no key required. Tries the
    exact name first, then falls back to Wikipedia's search API to resolve
    a better-matching page title (company names rarely match Wikipedia
    titles exactly - e.g. "Acme" vs "Acme Corporation" vs "Acme (company)").
    """
    direct = _wikipedia_summary_for_title(company_name)
    if direct:
        return direct

    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": company_name, "format": "json", "srlimit": 3},
            headers=HEADERS, timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
    except httpx.HTTPError:
        return None

    for r in results:
        summary = _wikipedia_summary_for_title(r.get("title", ""))
        if summary:
            return summary
    return None


def _wikipedia_summary_for_title(title: str) -> dict | None:
    if not title:
        return None
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("type") == "disambiguation":
            return None
        extract = data.get("extract")
        if not extract:
            return None
        return {
            "title": data.get("title"),
            "extract": extract,
            "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
        }
    except httpx.HTTPError:
        return None


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Default: DuckDuckGo HTML search, no key required (best-effort, see
    module docstring). If SERPAPI_API_KEY is set, prefer that instead -
    it's a real supported API and more reliable.
    """
    if settings.SERPAPI_API_KEY:
        return _serpapi_search(query, max_results)
    return _duckduckgo_search(query, max_results)


def _resolve_ddg_redirect(href: str) -> str:
    """DuckDuckGo's html endpoint often wraps outbound links as
    //duckduckgo.com/l/?uddg=<url-encoded-target>&rut=... - unwrap that so
    we get the real target URL instead of a DDG redirect link."""
    if "uddg=" in href:
        try:
            parsed = urlparse(href if href.startswith("http") else "https:" + href)
            qs = parse_qs(parsed.query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        except Exception:
            pass
    return href


def _duckduckgo_search(query: str, max_results: int) -> list[dict]:
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []

    # Dependency-free HTML scrape (no bs4 requirement). Attribute order in
    # DDG's markup isn't guaranteed, so match the <a ...>...</a> tag first
    # and pull href/class out of its attributes separately, rather than
    # requiring a fixed attribute order (the earlier version's bug).
    results = []
    anchor_pattern = re.compile(r'<a\s+([^>]*class="result__a"[^>]*)>(.*?)</a>', re.DOTALL)
    href_pattern = re.compile(r'href="([^"]+)"')
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
    strip_tags = lambda s: re.sub(r"<[^>]+>", "", s).strip()

    anchors = anchor_pattern.findall(resp.text)
    snippets = snippet_pattern.findall(resp.text)
    for i, (attrs, title_html) in enumerate(anchors[:max_results]):
        href_match = href_pattern.search(attrs)
        if not href_match:
            continue
        href = _resolve_ddg_redirect(href_match.group(1))
        snippet = strip_tags(snippets[i]) if i < len(snippets) else ""
        results.append({"url": href, "title": strip_tags(title_html), "snippet": snippet})
    return results


def _serpapi_search(query: str, max_results: int) -> list[dict]:
    try:
        resp = httpx.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": settings.SERPAPI_API_KEY, "num": max_results},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError:
        return []
    results = []
    for r in data.get("organic_results", [])[:max_results]:
        results.append({"url": r.get("link"), "title": r.get("title"), "snippet": r.get("snippet", "")})
    return results


def fetch_page_text(url: str, max_chars: int = 4000) -> str:
    """Best-effort raw text fetch for a source page, truncated for prompt budget."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError:
        return ""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", resp.text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]
