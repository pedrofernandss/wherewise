"""Garante que frontend/model.js e app/model.py produzem os mesmos números."""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from app.main import cells
from app.model import Params, evaluate, summarize

ROOT = Path(__file__).resolve().parents[2]
KEYS = ["IR", "P_poco", "GPI", "WTD", "A_sup", "E_custo", "C_poco_total", "confianca"]

JS = """
const M = require(process.argv[1]);
const inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = inp.cases.map(cs => {
  const p = M.params(cs.params);
  const res = inp.cells.map(c => M.evaluate(c, p));
  return {res: res.map(r => ({cls: r.cls, fator_pos: r.fator_pos, fator_neg: r.fator_neg, rio: r.rio.name,
    IR: r.IR, P_poco: r.P_poco, GPI: r.GPI, WTD: r.WTD, A_sup: r.A_sup, E_custo: r.E_custo,
    C_poco_total: r.C_poco_total, confianca: r.confianca, C_rio: r.rio.C_total})),
    sum: M.summarize(inp.cells, res)};
});
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node não instalado")
def test_js_python_parity():
    rng = random.Random(1)
    cases = [{}, {"horizon_months": 6, "start_month": 1}, {"horizon_months": 30, "area_ha": 40, "c_energia": 0.4},
             {"model_version": 2}, {"model_version": 2, "horizon_months": 6, "area_ha": 30}]
    for _ in range(3):
        cases.append({"horizon_months": rng.randint(1, 24), "start_month": rng.randint(1, 12),
                      "area_ha": rng.uniform(1, 50), "w1": rng.random(), "w3": rng.random(), "D_max_km": rng.uniform(3, 30)})
    cs = cells()
    proc = subprocess.run(["node", "-e", JS, str(ROOT / "frontend" / "model.js")],
                          input=json.dumps({"cells": cs, "cases": [{"params": c} for c in cases]}),
                          capture_output=True, text=True, check=True)
    js = json.loads(proc.stdout)
    for case, out in zip(cases, js):
        p = Params.from_dict(case)
        py = [evaluate(c, p) for c in cs]
        for a, b in zip(py, out["res"]):
            assert a["cls"] == b["cls"] and a["fator_pos"] == b["fator_pos"] and a["fator_neg"] == b["fator_neg"]
            assert a["rio"]["name"] == b["rio"]
            for k in KEYS:
                assert a[k] == pytest.approx(b[k], rel=1e-9, abs=1e-9), k
            assert a["rio"]["C_total"] == pytest.approx(b["C_rio"], rel=1e-9)
        s_py = summarize(cs, py)
        assert [s["classe_dominante"] for s in s_py] == [s["classe_dominante"] for s in out["sum"]]
