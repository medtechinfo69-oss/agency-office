"""Competitor & trend scan.

Tries live web search (DuckDuckGo HTML — no API key) and asks the model to
summarise with sources. If the network is unavailable, falls back to the
model's own knowledge with an explicit `live: false` flag (shown in the UI).
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx

from .config import settings
from .provider import provider


async def _ddg_search(query: str, limit: int = 6) -> list[dict]:
    url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(timeout=12, follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0 (agency-office)"}) as client:
        resp = await client.post(url, data={"q": query})
        resp.raise_for_status()
    html = resp.text
    results = []
    for m in re.finditer(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html, re.S):
        href, title, snip = m.group(1), _strip(m.group(2)), _strip(m.group(3))
        if "uddg=" in href:
            mm = re.search(r"uddg=([^&]+)", href)
            if mm:
                from urllib.parse import unquote
                href = unquote(mm.group(1))
        results.append({"title": title, "url": href, "snippet": snip[:300]})
        if len(results) >= limit:
            break
    return results


def _strip(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


async def scan(brief: str, *, query: str = "") -> dict[str, Any]:
    q = query or (re.sub(r"\s+", " ", brief)[:120] + " trends competitors")
    live = False
    results: list[dict] = []
    error = ""
    if settings.trend_search.lower() == "web":
        try:
            results = await _ddg_search(q)
            live = bool(results)
        except Exception as e:
            error = f"web search unavailable ({e.__class__.__name__})"

    system = ("ROLE: Trends analyst. Summarise competitor/trend insights for the brief. "
              "If sources are provided, cite them as [n] and keep a sources list. "
              "If no sources, set sources=[] and demo=true.")
    user = (f"<<<BRIEF>>>{brief}<<<ENDBRIEF>>>\nQUERY: {q}\n"
            + ("SOURCES:\n" + "\n".join(
                f"[{i+1}] {r['title']} — {r['url']}\n    {r['snippet']}"
                for i, r in enumerate(results)) if results else
               "(no live sources — answer from knowledge, flag demo=true)")
            + '\nReturn JSON {"summary": str, "competitors": [{"name","observation","source"}], "sources": [str]}')
    try:
        text = await provider().chat(
            [{"role": "system", "content": "[TASK:trends]\n" + system},
             {"role": "user", "content": user}], json_mode=True, max_tokens=1600)
        import json as _json
        data = _json.loads(_json.dumps(_safe_json(text.text)))
    except Exception as e:
        data = {"summary": f"Trend analysis failed: {e}", "competitors": [], "sources": []}

    data.setdefault("sources", [r["url"] for r in results if r.get("url")])
    data["live"] = live
    data["query"] = q
    if error:
        data["search_error"] = error
    return data


def _safe_json(text: str) -> dict:
    import json
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        return {"summary": text[:500], "competitors": [], "sources": []}
