"""Explicação em linguagem natural (inglês) de uma recomendação (sem LLM, por template)."""
from __future__ import annotations

from .model import Params

CLS_TXT = {
    "poco_alto": "borehole highly recommended",
    "poco_viavel": "borehole viable",
    "rio": "river pumping recommended",
    "inconclusivo": "inconclusive, needs a field study",
    "nao_recomendado": "neither option is recommended",
}
ZONE_TXT = {
    "costeira": "Moanda coastal sedimentary basin",
    "kongo_central": "Kongo Central (crystalline Mayombe and Schisto-calcaire limestones, possible karst)",
    "rift": "Albertine/Kivu rift (volcanic and fractured rocks, high variability)",
    "cuvette": "Cuvette Centrale sedimentary basin (shallow water table)",
    "kalahari": "Kalahari/Batéké plateaus (thick sands, deep water table on the crests)",
    "kasai": "Kasai craton (crystalline basement)",
    "katanga": "Katanga (metasediments and dolomites, possible karst)",
    "embasamento": "crystalline basement of the north and east",
}


def usd(x: float) -> str:
    return f"USD {x:,.0f}"


def explain(c: dict, r: dict, p: Params) -> str:
    rio = r["rio"]
    parts = [
        f"Cell in {c['dept']} ({c['lat']:.2f}, {c['lon']:.2f}). Domain: {ZONE_TXT.get(c['zone'], c['zone'])}.",
        f"Result: {CLS_TXT[r['cls']]} (IR = {r['IR']:.2f}; above 0.5 favours a borehole).",
        f"Borehole: {100 * r['P_poco']:.0f}% success probability, water table estimated at {r['WTD']:.0f} m, "
        f"{r['H']:.0f} m drilling, {r['n_pocos']} borehole(s) for {p.area_ha:g} ha, "
        f"cost over a {p.horizon_months}-month horizon {usd(r['C_poco_total'])}.",
        f"River: best intake on {rio['name']} at {rio['D_km']:.1f} km, {max(rio['dz'], 0):.0f} m lift, "
        f"suitability {r['A_sup']:.2f}, cost over the horizon {usd(rio['C_total'])}.",
        f"Main factor in favour: {r['fator_pos']}. Main limitation: {r['fator_neg']}.",
    ]
    if r["turfeira"]:
        parts.append("Warning: Cuvette Centrale peatland area, environmentally sensitive; "
                     "drainage and drilling require careful permitting.")
    if not r["vazao_ok"]:
        parts.append("The typical borehole yield in this domain does not meet demand even with the maximum number of boreholes.")
    parts.append("Preliminary recommendation: test drilling and a pumping test are required before construction.")
    return " ".join(parts)
