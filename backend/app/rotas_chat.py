"""Chat do assistente hídrico (Web RAG com tool calling no Claude).

POST /api/chat recebe a mensagem e o histórico da conversa; o Claude decide
quando buscar na web e quando ler o mapa local.

Ferramentas:
  - lookup_map: recomendação poço vs rio nas células do protótipo (data/);
  - bing_search (se BING_SUBSCRIPTION_KEY) ou web_search nativa do Claude.
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Literal

import anthropic
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import rag
from .explain import CLS_TXT, explain
from .model import Params, evaluate, summarize

# --- variáveis de ambiente (injete no .env / docker-compose / App Service) ---
BING_SUBSCRIPTION_KEY = os.environ.get("BING_SUBSCRIPTION_KEY", "")
BING_SEARCH_URL = os.environ.get("BING_SEARCH_URL", "https://api.bing.microsoft.com/v7.0/search")

SYSTEM = (
    "You are a water-management assistant for the Democratic Republic of the Congo (DRC). Whenever you are "
    "asked about data, legislation or hydrogeology, use the Bing search tool to find recent information and "
    "cite the source in your answer. Reply in the language of the user's question (English by default), "
    "concisely, and end by listing the URLs you used. "
    "Your name is Mbula (\"rain\" in Lingala); introduce yourself that way only if asked who you are."
    "Act as if you are a real person, not a bot. Use natural language and be friendly."
    "Dont mention the Bing search tool in your answer. Only use it to find information."
    "Dont act like a source of everything. If you don't know the answer, say so."
    "You can access our local database to find information.yehnin.  You are a real person, not a bot. Use natural language and be friendly."
    "Don't waste time mentioning the database. Just use it to find information."
    "Write brief answers. Don't write more than 100 words. "
    "When the user asks how to extract water, drill, pump from a river, or what the map recommends "
    "near a city, village or province, call lookup_map with that place name before answering. "
    "Those figures come from the Wherewise map (local grid), not the web; do not invent web URLs for them. "
    "Use web search only for news, legislation or facts that are not on the map."
)

MAX_HISTORY = 20
MAX_STEPS = 6
log = logging.getLogger("hidro.chat")
router = APIRouter()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatTurn] = []


def bing_search(query: str, count: int = 5) -> list[dict]:
    r = httpx.get(BING_SEARCH_URL, params={"q": query, "count": count, "textDecorations": False},
                  headers={"Ocp-Apim-Subscription-Key": BING_SUBSCRIPTION_KEY}, timeout=10)
    r.raise_for_status()
    return [{"title": v.get("name", ""), "url": v.get("url", ""), "snippet": v.get("snippet", "")}
            for v in r.json().get("webPages", {}).get("value", [])]


DATA = Path(os.environ.get("HIDRO_DATA", Path(__file__).resolve().parent.parent.parent / "data"))


def _fold(s: str) -> str:
    t = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


@lru_cache
def _cities() -> list[dict]:
    p = DATA / "cities.json"
    return json.loads(p.read_text()) if p.exists() else []


def _match_city(place: str) -> dict | None:
    q = _fold(place)
    words = [w for w in re.findall(r"[a-z0-9-]+", q) if len(w) > 2]
    scored = []
    for c in _cities():
        n = _fold(c["name"])
        if n == q:
            scored.append((0, -c.get("pop", 0), c))
        elif q in n or n in q:
            scored.append((1, -c.get("pop", 0), c))
        elif any(w == n or w in n.replace("-", " ").split() for w in words):
            scored.append((2, -c.get("pop", 0), c))
    scored.sort(key=lambda x: (x[0], x[1]))
    return scored[0][2] if scored else None


def _match_dept(place: str, depts: list[str]) -> str | None:
    q = _fold(place)
    words = [w for w in re.findall(r"[a-z0-9-]+", q) if len(w) > 2]
    hits = []
    for d in depts:
        n = _fold(d)
        if n == q:
            hits.append((0, d))
        elif q in n or n in q:
            hits.append((1, d))
        elif any(w in n for w in words if len(w) > 3):
            hits.append((2, d))
    hits.sort()
    return hits[0][1] if hits else None


def _cell_brief(c: dict, label: str) -> str:
    p = Params()
    r = evaluate(c, p)
    head = f"{label}\n{explain(c, r, p)}"
    return head


def _province_brief(dept: str, cs: list[dict]) -> str:
    p = Params()
    sel = [c for c in cs if dept in c["depts"]]
    rs = [evaluate(c, p) for c in sel]
    s = next(x for x in summarize(sel, rs) if x["dept"] == dept)
    dom = CLS_TXT.get(s["classe_dominante"], s["classe_dominante"])
    lines = [
        f"Province {dept}: {s['n_celulas']} cells. Dominant map class: {dom} "
        f"({s['pct_poco']}% of cells favour a borehole).",
    ]
    # a few representative cells (highest |IR-0.5| so the contrast is clear)
    ranked = sorted(zip(sel, rs), key=lambda x: -abs(x[1]["IR"] - 0.5))[:3]
    for c, r in ranked:
        lines.append(f"- Cell {c['id']} near {c['lat']:.2f}, {c['lon']:.2f}: {CLS_TXT[r['cls']]} (IR {r['IR']:.2f}).")
    lines.append("Source: Wherewise local map model. Recommendation is preliminary.")
    return "\n".join(lines)


def lookup_map(place: str) -> str:
    """Recomendação do mapa local para um lugar (cidade, província ou lat,lon)."""
    from .main import cells, check_res, nearest_cell  # import tardio: evita ciclo com main

    place = (place or "").strip()
    if not place:
        return "Need a city, village or province name in the DRC."
    res = check_res(None)
    cs = cells(res)
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$", place)
    if m:
        try:
            c = nearest_cell(float(m[1]), float(m[2]), res)
        except Exception as e:
            return f"No map cell at those coordinates ({e})."
        return _cell_brief(c, f"Map cell {c['id']} at {c['lat']:.2f}, {c['lon']:.2f} ({c['dept']}).")
    city = _match_city(place)
    if city:
        try:
            c = nearest_cell(city["lat"], city["lon"], res)
        except Exception as e:
            return f"Found {city['name']} but it is outside the map grid ({e})."
        return _cell_brief(
            c,
            f"Place: {city['name']} (pop {city.get('pop', '?')}) at {city['lat']:.2f}, {city['lon']:.2f}. "
            f"Nearest map cell {c['id']} in {c['dept']}.",
        )
    depts = sorted({d for c in cs for d in c["depts"]})
    dept = _match_dept(place, depts)
    if dept:
        return _province_brief(dept, cs)
    sample = ", ".join(c["name"] for c in sorted(_cities(), key=lambda x: -x.get("pop", 0))[:8])
    return f"No city or province matched '{place}'. Try a name on the map, e.g. {sample}."


BING_TOOL = {
    "name": "bing_search",
    "description": "Searches the web (Bing) and returns the title, URL and snippet of each result. Use it for "
                   "recent data, climate, hydrogeology and legislation of the Democratic Republic of the Congo (DRC).",
    "strict": True,
    "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "search terms"}},
                     "required": ["query"], "additionalProperties": False},
}
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}
MAP_TOOL = {
    "name": "lookup_map",
    "description": "Reads Wherewise's local map model (borehole vs river pumping) for a DRC city, "
                   "village or province. Use this for extraction, irrigation or aquifer questions about a "
                   "place on the map (e.g. Watsa, Kinshasa, Haut-Uele). This is not a web search.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "City, village or province name in the DRC"},
        },
        "required": ["place"],
        "additionalProperties": False,
    },
}


def _mode() -> str:
    if rag.status() != "claude":
        return "sem_ia"
    return "bing" if BING_SUBSCRIPTION_KEY else "web_search"


def _add_source(sources: dict, url: str, title: str) -> None:
    if url and url not in sources:
        sources[url] = {"title": title or url, "url": url}


def _run_agent(messages: list[dict], tools: list[dict]) -> tuple[str, dict]:
    sources: dict[str, dict] = {}
    for _ in range(MAX_STEPS):
        resp = rag._client().beta.messages.create(
            model=rag.MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM,
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason == "refusal":
            return "I can't help with that question.", sources
        messages.append({"role": "assistant", "content": resp.content})

        for b in resp.content:
            if b.type == "web_search_tool_result" and isinstance(b.content, list):
                for res in b.content:
                    _add_source(sources, res.url, res.title)
            elif b.type == "text":
                for c in b.citations or []:
                    _add_source(sources, getattr(c, "url", ""), getattr(c, "title", ""))

        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text").strip(), sources

        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            try:
                if b.name == "bing_search":
                    hits = bing_search(b.input["query"])
                    for h in hits:
                        _add_source(sources, h["url"], h["title"])
                    text = "\n\n".join(f"{h['title']}\n{h['url']}\n{h['snippet']}" for h in hits) or "No results."
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": text})
                elif b.name == "lookup_map":
                    text = lookup_map(b.input.get("place", ""))
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": text})
            except (httpx.HTTPError, KeyError, ValueError) as e:
                results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                "content": f"search failed: {e}"})
        if not results:
            continue
        messages.append({"role": "user", "content": results})
    return "I couldn't finish the research in time; try rephrasing the question.", sources


@router.post("/api/chat")
def chat(req: ChatRequest):
    mode = _mode()
    if mode == "sem_ia":
        return {"mode": mode, "answer": "The assistant is disabled: set ANTHROPIC_API_KEY on the server.",
                "sources": []}
    messages = [{"role": t.role, "content": t.content} for t in req.history[-MAX_HISTORY:] if t.content.strip()]
    while messages and messages[0]["role"] != "user":  # a conversa precisa começar pelo usuário
        messages.pop(0)
    messages.append({"role": "user", "content": req.message})
    try:
        answer, sources = _run_agent(messages, [MAP_TOOL] + ([BING_TOOL] if mode == "bing" else [WEB_SEARCH_TOOL]))
    except anthropic.APIError as e:
        log.warning("falha no Claude: %s", e)
        return {"mode": mode, "answer": "The assistant is unavailable right now. Please try again.",
                "sources": [], "error": str(e)}
    return {"mode": mode, "model": rag.MODEL, "answer": re.sub(r"\n{3,}", "\n\n", answer),
            "sources": list(sources.values())}
