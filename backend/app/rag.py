"""RAG (seção 4.3 do plano) com a API do Claude.

Recuperação: BM25 local sobre os documentos em app/knowledge/ (por padrão o
próprio plano de arquitetura), dividido por seções.
Geração: se ANTHROPIC_API_KEY estiver definida, os trechos (e, quando
informada, a recomendação calculada para uma célula) vão para o Claude; senão
a resposta é extrativa (os trechos mais relevantes).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

KB = Path(os.environ.get("HIDRO_KNOWLEDGE", Path(__file__).parent / "knowledge"))
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
STOP = set("a o e de da do das dos em no na nos nas um uma para por com que se ou ao à as os é".split())
SYSTEM = (
    "You are the Wherewise assistant, a prototype that recommends a borehole or river pumping for irrigation "
    "in the Democratic Republic of the Congo (DRC). Reply in the language of the user's question (English by "
    "default), in at most three short paragraphs, using only the context provided: excerpts from the technical "
    "plan (written in Portuguese) and, when present, the figures computed for a map cell. Cite the plan sections "
    "in square brackets. If the context does not answer the question, say so. Remind the user that the "
    "recommendation is preliminary and that test drilling and a pumping test are required."
)
log = logging.getLogger("hidro.rag")


def _norm(t: str) -> list[str]:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return [w for w in re.findall(r"[a-z0-9_]+", t) if w not in STOP and len(w) > 1]


@lru_cache
def chunks() -> list[dict]:
    out = []
    for f in sorted(KB.glob("*.md")):
        cur, buf = f.stem, []
        for line in f.read_text().splitlines():
            if line.startswith("#"):
                if buf:
                    out.append({"doc": f.name, "section": cur, "text": "\n".join(buf).strip()})
                cur, buf = line.lstrip("# ").strip(), []
            else:
                buf.append(line)
        if buf:
            out.append({"doc": f.name, "section": cur, "text": "\n".join(buf).strip()})
    out = [c for c in out if c["text"]]
    for c in out:
        c["tokens"] = _norm(c["section"] + " " + c["text"])
    return out


def search(q: str, k: int = 3) -> list[dict]:
    docs = chunks()
    N = len(docs) or 1
    avg = sum(len(d["tokens"]) for d in docs) / N
    df = Counter(t for d in docs for t in set(d["tokens"]))
    qt = _norm(q)
    scored = []
    for d in docs:
        tf = Counter(d["tokens"])
        s = 0.0
        for t in qt:
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d["tokens"]) / avg))
        if s > 0:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    return [{"doc": d["doc"], "section": d["section"], "score": round(s, 3), "text": d["text"][:1500]}
            for s, d in scored[:k]]


def status() -> str:
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "extrativo"


@lru_cache
def _client():
    import anthropic
    return anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente


def _ask_claude(question: str, hits: list[dict], cell_ctx: dict | None) -> str:
    parts = [f"[{h['section']}]\n{h['text']}" for h in hits]
    if cell_ctx:
        parts.append("[Cell selected on the map]\n" + json.dumps(cell_ctx, ensure_ascii=False))
    resp = _client().beta.messages.create(
        model=MODEL,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{"role": "user", "content": "Context:\n\n" + "\n\n".join(parts) + f"\n\nQuestion: {question}"}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("the model refused the question")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def answer(question: str, k: int = 3, cell_ctx: dict | None = None) -> dict:
    hits = search(question + (" " + cell_ctx.get("zona", "") if cell_ctx else ""), k)
    if status() != "claude":
        return {"mode": "extrativo", "answer": hits[0]["text"] if hits else "Nothing found in the knowledge base.",
                "sources": hits}
    try:
        return {"mode": "claude", "model": MODEL, "answer": _ask_claude(question, hits, cell_ctx), "sources": hits}
    except Exception as e:  # cai para o modo extrativo sem derrubar a API
        log.warning("falha no Claude: %s", e)
        return {"mode": "extrativo", "answer": hits[0]["text"] if hits else "Nothing found in the knowledge base.",
                "sources": hits, "error": str(e)}
