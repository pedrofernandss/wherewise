"""Validação das recomendações contra os pontos de água do WPdx (veja VALIDACAO.md).

O WPdx registra onde existem poços (e se funcionam), não onde poços falharam, e é enviesado para onde há
gente. Por isso a métrica principal é a AUC dentro da área levantada (células a até 50 km de algum ponto
WPdx): a chance de uma célula com poço real ter P_poço maior que uma célula sem poço (0,5 = sem sinal).
Também é calculada uma AUC estratificada por população (WorldPop).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .model import Params, evaluate

WELL_CLASSES = ("poco_alto", "poco_viavel")
N_POP_BINS = 5
CAVEATS = [
    "WPdx records where boreholes exist, not where drilling failed: it can confirm, not refute, borehole viability.",
    "Points are concentrated where people live and where surveys happened (mostly the Kivus and Kinshasa; none in the Cuvette Centrale), so the main AUC only compares cells within 50 km of a surveyed point; a WorldPop-stratified AUC is also reported.",
    "Most DRC records are tapstands of borehole-fed networks (GRET, 2014); they mark supply points, not the borehole itself.",
    "Drinking-water boreholes need far less yield than irrigation; existence of a borehole is a weak test of irrigation viability.",
]


@lru_cache
def wpdx(data_dir: str) -> dict:
    p = Path(data_dir) / "wpdx_cells.json"
    return json.loads(p.read_text()) if p.exists() else {"cells": {}, "surveyed": {}}


def _auc(pos: list[float], neg: list[float]) -> tuple[float, int]:
    """AUC (Mann-Whitney) e número de pares comparados."""
    if not pos or not neg:
        return 0.5, 0
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(allv):  # postos médios para empates
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (i + 1 + j) / 2
        rank_sum += r * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    n1, n0 = len(pos), len(neg)
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0), n1 * n0


def _pop_bins(cells: list[dict]) -> dict[int, int]:
    vals = sorted(c.get("pop_wp") or 0 for c in cells)
    cuts = [vals[int(len(vals) * k / N_POP_BINS)] for k in range(1, N_POP_BINS)]
    return {c["id"]: sum((c.get("pop_wp") or 0) >= x for x in cuts) for c in cells}


def metrics(cells: list[dict], params: dict, version: int, wp: dict, surveyed: set) -> dict:
    p = Params.from_dict(params | {"model_version": version})
    res = {c["id"]: evaluate(c, p) for c in cells}
    has_well = {c["id"]: wp.get(str(c["id"]), [0, 0, 0])[1] > 0 for c in cells}
    pw = [res[i]["P_poco"] for i, w in has_well.items() if w]
    pn = [res[i]["P_poco"] for i, w in has_well.items() if not w]
    share = lambda ids: sum(res[i]["cls"] in WELL_CLASSES for i in ids) / len(ids) if ids else None
    well_ids = [i for i, w in has_well.items() if w]

    sv = [i for i in res if i in surveyed]
    auc_surveyed = _auc([res[i]["P_poco"] for i in sv if has_well[i]],
                        [res[i]["P_poco"] for i in sv if not has_well[i]])[0] if sv else None

    strat = None
    if all(c.get("pop_wp") is not None for c in cells):
        bins = _pop_bins(cells)
        num = pairs = 0
        for b in range(N_POP_BINS):
            pos = [res[i]["P_poco"] for i in res if bins[i] == b and has_well[i]]
            neg = [res[i]["P_poco"] for i in res if bins[i] == b and not has_well[i]]
            a, n = _auc(pos, neg)
            num += a * n
            pairs += n
        strat = num / pairs if pairs else None

    func = {}
    for lo, hi, key in ((0, 0.3, "<0.30"), (0.3, 0.5, "0.30-0.50"), (0.5, 1.01, ">=0.50")):
        n = f = 0
        for i in well_ids:
            if lo <= res[i]["P_poco"] < hi:
                n += wp[str(i)][1]
                f += wp[str(i)][2]
        func[key] = {"wells": n, "functional_pct": round(100 * f / n, 1) if n else None}

    return {
        "model_version": version,
        "cells_with_wells": len(well_ids),
        "borehole_rec_share_with_wells": share(well_ids),
        "borehole_rec_share_all": share(list(res)),
        "mean_P_with_wells": sum(pw) / len(pw) if pw else None,
        "mean_P_without_wells": sum(pn) / len(pn) if pn else None,
        "auc": _auc(pw, pn)[0],
        "auc_surveyed": auc_surveyed,
        "auc_pop_stratified": strat,
        "functional_by_P": func,
    }


def validate(cells: list[dict], params: dict, res: str, data_dir: str) -> dict:
    w = wpdx(data_dir)
    wp, surveyed = w["cells"].get(res, {}), set(w.get("surveyed", {}).get(res, []))
    wells = sum(v[1] for v in wp.values())
    return {
        "res": res, "n_cells": len(cells), "n_wells": wells,
        "n_wells_functional": sum(v[2] for v in wp.values()),
        "cells_with_any_point": len(wp), "cells_surveyed": len(surveyed), "survey_km": w.get("survey_km"),
        "versions": {f"v{v}": metrics(cells, params, v, wp, surveyed) for v in (1, 2)},
        "caveats": CAVEATS,
    }
