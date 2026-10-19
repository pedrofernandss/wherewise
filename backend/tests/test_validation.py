from fastapi.testclient import TestClient

from app.main import app, cells
from app.model import Params, evaluate

client = TestClient(app)


def test_model_v2_uses_real_data():
    c = next(c for c in cells() if c.get("bgs_yield_Ls") and c.get("wtd_g_p25"))
    r1 = evaluate(c, Params.from_dict({}))
    r2 = evaluate(c, Params.from_dict({"model_version": 2}))
    assert r2["vazao_poco_Ls"] == c["bgs_yield_Ls"] and r1["vazao_poco_Ls"] == c["yield_Ls"]
    assert r2["WTD"] == max(1.5, min(150.0, c["wtd_g_p25"]))
    no_data = {k: v for k, v in c.items() if k not in ("bgs_yield_Ls", "wtd_g_p25", "P_m_chirps", "sand")}
    assert evaluate(no_data, Params.from_dict({"model_version": 2}))["P_poco"] == r1["P_poco"]  # sem dados reais, v2 = v1


def test_validation_endpoint():
    v = client.post("/api/validation", json={"params": {}}).json()
    assert v["n_wells"] > 5000 and v["cells_surveyed"] > 0
    for k in ("v1", "v2"):
        m = v["versions"][k]
        assert 0 <= m["auc_surveyed"] <= 1 and 0 <= m["borehole_rec_share_with_wells"] <= 1
    assert client.post("/api/validation?res=0.2", json={"params": {}}).json()["res"] == "0.2"


def test_waterpoints_layer():
    d = client.get("/api/layers/waterpoints").json()
    assert len(d["points"]) > 7000 and d["fields"][:4] == ["lon", "lat", "well", "status"]
