from fastapi.testclient import TestClient

from app import rotas_chat
from app.main import app

client = TestClient(app)


def test_chat_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/chat", json={"message": "Qual a lei da água na RDC?", "history": []})
    assert r.status_code == 200
    assert r.json()["mode"] == "sem_ia" and r.json()["sources"] == []


def test_chat_validation():
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "oi", "history": [{"role": "system", "content": "x"}]}
                       ).status_code == 422


def test_lookup_map_watsa():
    text = rotas_chat.lookup_map("Watsa")
    assert "Watsa" in text and "cell" in text.lower()
    assert any(k in text.lower() for k in ("borehole", "river", "inconclusive", "recommended"))
    assert rotas_chat.lookup_map("").startswith("Need a")
    assert "No city" in rotas_chat.lookup_map("Atlantis")


def test_bing_search_parsing(monkeypatch):
    seen = {}

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"webPages": {"value": [
                {"name": "Loi relative à l'eau", "url": "https://exemplo.cd/loi-eau", "snippet": "Loi n° 15/026"}]}}

    def fake_get(url, params, headers, timeout):
        seen.update(url=url, params=params, headers=headers)
        return Resp()

    monkeypatch.setattr(rotas_chat, "BING_SUBSCRIPTION_KEY", "k")
    monkeypatch.setattr(rotas_chat.httpx, "get", fake_get)
    hits = rotas_chat.bing_search("código da água RDC")
    assert hits == [{"title": "Loi relative à l'eau", "url": "https://exemplo.cd/loi-eau", "snippet": "Loi n° 15/026"}]
    assert seen["headers"]["Ocp-Apim-Subscription-Key"] == "k"
    assert seen["params"]["q"] == "código da água RDC"
