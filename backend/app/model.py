"""Modelo de recomendação (seção 3 do plano de arquitetura).

Funções puras sobre as covariáveis de uma célula. A mesma lógica existe em
frontend/model.js (para a demo estática); tests/test_parity.py garante que as
duas dão o mesmo resultado.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

RHO, G = 1000.0, 9.81
M_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# --- GPI: fatores e matriz AHP (escala de Saaty) -----------------------------
GPI_FACTORS = ["lito", "perm", "rech", "slope", "dd", "dens", "lu"]
GPI_LABELS = {
    "lito": "favourable lithology / aquifer",
    "perm": "soil permeability",
    "rech": "recharge",
    "slope": "gentle slope",
    "dd": "proximity to drainage",
    "dens": "drainage density",
    "lu": "vegetation cover",
}
#            lito perm rech slope dd  dens lu
AHP_MATRIX = [
    [1,   2,   3,   4,   4,   5,   6],
    [1/2, 1,   2,   3,   3,   4,   5],
    [1/3, 1/2, 1,   2,   2,   3,   4],
    [1/4, 1/3, 1/2, 1,   1,   2,   3],
    [1/4, 1/3, 1/2, 1,   1,   2,   3],
    [1/5, 1/4, 1/3, 1/2, 1/2, 1,   2],
    [1/6, 1/5, 1/4, 1/3, 1/3, 1/2, 1],
]
RANDOM_INDEX = {1: 0, 2: 0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45}


def ahp_weights(matrix=AHP_MATRIX, iters=100):
    """Autovetor principal por iteração de potência + razão de consistência."""
    n = len(matrix)
    w = [1.0 / n] * n
    for _ in range(iters):
        v = [sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
        s = sum(v)
        w = [x / s for x in v]
    aw = [sum(matrix[i][j] * w[j] for j in range(n)) for i in range(n)]
    lam = sum(aw[i] / w[i] for i in range(n)) / n
    ci = (lam - n) / (n - 1)
    cr = ci / RANDOM_INDEX[n]
    return w, lam, cr


@dataclass
class Params:
    model_version: int = 1          # 1 = covariáveis sintéticas; 2 = dados reais (BGS, GLOBGM, CHIRPS, SoilGrids)
    horizon_months: int = 12        # 6, 12 ou customizado
    start_month: int = 6            # 1..12 (junho = início da estação seca no sul da RDC)
    area_ha: float = 5.0            # área irrigada
    irrigation_mm_day: float = 5.0  # lâmina de pico
    hours_per_day: float = 8.0      # horas de bombeamento por dia
    # poço
    WTD_max: float = 60.0
    R_ref: float = 200.0
    h_sat: float = 8.0
    drawdown: float = 5.0
    C_fixo: float = 1200.0
    c_perf: float = 70.0
    c_revest: float = 35.0
    C_bomba: float = 1500.0
    C_inst: float = 1200.0
    c_mob_km: float = 15.0          # mobilização da sonda por km fora da estrada
    max_wells: int = 20
    # rio
    Dz_max: float = 100.0
    D_max_km: float = 15.0
    env_flow_frac: float = 0.10     # fração máxima captável da vazão (vazão ecológica)
    C_bomba_rio: float = 2500.0
    C_captacao: float = 1500.0
    hazen_C: float = 140.0
    pipe_v: float = 1.0             # velocidade de projeto (m/s)
    h_s: float = 3.0
    h_d: float = 10.0
    # energia
    eta: float = 0.55
    c_energia: float = 0.22         # USD/kWh (diesel/solar equivalente, fora da rede)
    # pesos do IR
    w1: float = 0.30  # A_sub
    w2: float = 0.25  # 1 - A_sup
    w3: float = 0.25  # E_custo
    w4: float = 0.10  # R_clima
    w5: float = 0.10  # A_acesso

    @classmethod
    def from_dict(cls, d: dict | None) -> "Params":
        p = cls()
        for k, v in (d or {}).items():
            if hasattr(p, k) and v is not None:
                setattr(p, k, type(getattr(p, k))(v))
        p.horizon_months = max(1, min(60, p.horizon_months))
        p.start_month = max(1, min(12, p.start_month))
        return p

    def to_dict(self):
        return asdict(self)


GPI_W, AHP_LAMBDA, AHP_CR = ahp_weights()


def clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def window(p: Params):
    """Meses (0..11) cobertos pelo horizonte, com repetição se > 12."""
    return [(p.start_month - 1 + k) % 12 for k in range(p.horizon_months)]


def effective(c: dict, p: Params) -> dict:
    """Modelo v2: troca as covariáveis sintéticas pelas reais quando a célula as tiver."""
    if p.model_version != 2:
        return c
    e = dict(c)
    if c.get("P_m_chirps"):
        e["P_m"], e["P"] = c["P_m_chirps"], c["P_chirps"]
    if c.get("bgs_yield_Ls") is not None:
        e["yield_Ls"], e["lito"] = c["bgs_yield_Ls"], c["bgs_fav"]
    if c.get("sand") is not None:
        e["So"] = clip(0.15 + 0.009 * c["sand"] - 0.006 * c["clay"], 0.1, 0.95)
    return e


def wtd(c: dict) -> float:
    """Regressão da seção 3.2 (coeficientes β ilustrativos, sem poços de calibração)."""
    v = (c["WTD0"] + 0.22 * c["HAND"] + 0.8 * c["S"] + 8.0 * c["C"] + 0.9 * c["D_d_km"]
         - 0.006 * (c["P"] - 1600) + 0.01 * (c["ET"] - 1250) - 6.0 * (c["NDVI"] - 0.6))
    return clip(v, 1.5, 150.0)


def gpi_factors(c: dict, R: float) -> dict:
    return {
        "lito": c["lito"],
        "perm": c["So"],
        "rech": clip(R / 400.0),
        "slope": clip(1 - c["S"] / 15.0),
        "dd": math.exp(-c["D_d_km"] / 5.0),
        "dens": clip(c["dens"] / 0.3),
        "lu": c["NDVI"],
    }


def pipe(q: float, L_m: float, p: Params):
    d = max(0.05, math.sqrt(4 * q / (math.pi * p.pipe_v)))
    hf = 10.67 * L_m * q ** 1.852 / (p.hazen_C ** 1.852 * d ** 4.87) if q > 0 else 0.0
    return d, hf


def river_option(src: dict, c: dict, q_dem: float, months: list, p: Params, hours: float):
    """Avalia uma fonte superficial (grande rio ou drenagem do DEM)."""
    D_m = src["d_km"] * 1000
    dz = c["E_low"] - src["z"]
    k = src.get("regime", 0.9)
    pm = c["P_m"]
    pmean = sum(pm) / 12
    q_m = [max(0.05, 1 + k * (pm[(m - 1) % 12] / pmean - 1)) * src["q"] for m in range(12)]
    q_win = sum(q_m[m] for m in months) / len(months)
    q_avail = p.env_flow_frac * q_win
    A_sup = (min(1.0, q_avail / q_dem) * clip(1 - max(dz, 0) / p.Dz_max)
             * clip(1 - src["d_km"] / p.D_max_km))
    R_clima = sum(1 for m in months if p.env_flow_frac * q_m[m] >= q_dem) / len(months)
    d, hf = pipe(q_dem, D_m, p)
    H_t = max(dz, 0) + hf + p.h_s + p.h_d
    kw = RHO * G * q_dem * H_t / p.eta / 1000
    C_op = kw * hours * p.c_energia
    C_cap = p.C_bomba_rio + p.C_captacao + D_m * (8 + 150 * d)
    return {
        "name": src.get("name") or "local drainage (DEM)", "D_km": src["d_km"], "Q_rio": round(src["q"], 2),
        "Q_disp": round(q_avail, 4), "dz": round(dz, 1), "H_t": round(H_t, 1), "pipe_d_mm": round(d * 1000),
        "A_sup": A_sup, "R_clima": R_clima, "C_bombeamento": C_op,
        "C_bombeamento_ano": C_op * 12 / len(months), "C_capex": C_cap, "C_total": C_cap + C_op,
    }


def evaluate(c: dict, p: Params) -> dict:
    c = effective(c, p)
    months = window(p)
    hpd = p.hours_per_day
    q_dem = p.area_ha * p.irrigation_mm_day * 10 / (hpd * 3600)  # m³/s durante a operação
    need = [clip(1 - c["P_m"][m] / max(c["PET_m"][m], 1), 0.15, 1.0) for m in range(12)]
    hours = sum(M_DAYS[m] * hpd * need[m] for m in months)

    # --- águas subterrâneas -------------------------------------------------
    alpha = 0.15 + 0.20 * c["So"]
    R = alpha * c["P"]
    W = clip(c["wtd_g_p25"], 1.5, 150.0) if p.model_version == 2 and c.get("wtd_g_p25") is not None else wtd(c)
    fx = gpi_factors(c, R)
    GPI = sum(GPI_W[i] * fx[f] for i, f in enumerate(GPI_FACTORS))
    P_poco = clip(GPI * (1 - W / p.WTD_max) * min(1.0, R / p.R_ref))
    H = W + p.h_sat
    q_well = c["yield_Ls"] / 1000
    n_wells = min(p.max_wells, max(1, math.ceil(q_dem / q_well)))
    yield_ok = n_wells * q_well >= q_dem
    unit = p.C_fixo + (p.c_perf + p.c_revest) * H + p.C_bomba + p.C_inst
    C_poco_capex = n_wells * unit + p.c_mob_km * c["D_road_km"]
    H_t_w = W + p.drawdown + p.h_d
    C_poco_op = RHO * G * q_dem * H_t_w / p.eta / 1000 * hours * p.c_energia
    C_poco_total = C_poco_capex + C_poco_op
    A_sub = P_poco * (1.0 if yield_ok else 0.6)
    pm = c["P_m"]
    R_clima_poco = clip(0.6 + 0.4 * (sum(pm[m] for m in months) / len(months)) / (sum(pm) / 12))

    # --- águas superficiais (melhor de: grande rio / drenagem do DEM) --------
    opts = [river_option(c["major"], c, q_dem, months, p, hours),
            river_option(c["stream"], c, q_dem, months, p, hours)]
    rio = max(opts, key=lambda o: (o["A_sup"], -o["C_total"]))
    A_sup = rio["A_sup"]

    # --- índice de recomendação --------------------------------------------
    E_custo = rio["C_total"] / (C_poco_total + rio["C_total"])
    R_clima = 0.5 + 0.5 * (R_clima_poco - rio["R_clima"])
    A_acesso = 0.7 * math.exp(-c["D_road_km"] / 25) + 0.3 * math.exp(-c["D_town_km"] / 60)
    comp = {"A_sub": A_sub, "A_sup_inv": 1 - A_sup, "E_custo": E_custo, "R_clima": R_clima, "A_acesso": A_acesso}
    ws = [p.w1, p.w2, p.w3, p.w4, p.w5]
    wsum = sum(ws) or 1.0
    IR = sum(w * v for w, v in zip(ws, comp.values())) / wsum

    # --- classe (seção 5.1) ------------------------------------------------
    if max(A_sub, A_sup) < 0.12:
        cls = "nao_recomendado"
    elif abs(IR - 0.5) < 0.03:
        cls = "inconclusivo"
    elif IR > 0.5:
        cls = "poco_alto" if P_poco >= 0.45 else "poco_viavel"
    else:
        cls = "rio"
    rec = "poco" if IR > 0.5 else "rio"

    # --- fatores explicativos ----------------------------------------------
    if rec == "poco":
        cand = {GPI_LABELS[f]: fx[f] for f in ("lito", "perm", "slope", "dd", "rech")}
        cand["shallow water table" if W < p.WTD_max / 2 else "deep water table"] = 1 - W / p.WTD_max
    else:
        cand = {
            "river flow": min(1.0, rio["Q_disp"] / q_dem),
            "river-to-field lift": clip(1 - max(rio["dz"], 0) / p.Dz_max),
            "distance to river": clip(1 - rio["D_km"] / p.D_max_km),
            "cost versus well": 1 - E_custo,
        }
    pos = max(cand, key=cand.get)
    neg = min(cand, key=cand.get)

    conf = clip(0.35 + 0.4 * math.exp(-c["D_station_km"] / 120) + 0.5 * abs(IR - 0.5))

    return {
        "id": c["id"], "cls": cls, "rec": rec, "IR": IR,
        "P_poco": P_poco, "GPI": GPI, "WTD": W, "H": H, "R": R, "AI": c["P"] / c["PET"],
        "n_pocos": n_wells, "vazao_poco_Ls": c["yield_Ls"], "vazao_ok": yield_ok,
        "C_poco": C_poco_capex, "C_poco_op": C_poco_op, "C_poco_total": C_poco_total,
        "A_sub": A_sub, "A_sup": A_sup, "R_clima_poco": R_clima_poco, "R_clima_rio": rio["R_clima"],
        "E_custo": E_custo, "A_acesso": A_acesso, "componentes": comp,
        "rio": rio, "fatores_gpi": fx, "fator_pos": pos, "fator_neg": neg,
        "confianca": conf, "Q_demanda": q_dem, "horas_op": hours, "turfeira": c["peat"],
    }


def summarize(cells: list[dict], results: list[dict]) -> list[dict]:
    """Agrega resultados por província (uma célula pode tocar mais de um)."""
    by = {}
    for c, r in zip(cells, results):
        for d in c["depts"]:
            s = by.setdefault(d, {"dept": d, "n": 0, "classes": {}, "p_sum": 0.0, "p_n": 0,
                                  "ir_sum": 0.0, "c_poco": [], "c_rio": []})
            s["n"] += 1
            s["classes"][r["cls"]] = s["classes"].get(r["cls"], 0) + 1
            s["ir_sum"] += r["IR"]
            if r["rec"] == "poco":
                s["p_sum"] += r["P_poco"]
                s["p_n"] += 1
                s["c_poco"].append(r["C_poco_total"])
            else:
                s["c_rio"].append(r["rio"]["C_total"])
    out = []
    for s in by.values():
        dom = max(s["classes"], key=s["classes"].get)
        med = lambda a: sorted(a)[len(a) // 2] if a else None  # noqa: E731
        out.append({
            "dept": s["dept"], "n_celulas": s["n"], "classes": s["classes"], "classe_dominante": dom,
            "pct_poco": round(100 * s["p_n"] / s["n"]),
            "P_poco_media": round(s["p_sum"] / s["p_n"], 4) if s["p_n"] else None,
            "IR_medio": round(s["ir_sum"] / s["n"], 4),
            "C_poco_mediano": med(s["c_poco"]), "C_rio_mediano": med(s["c_rio"]),
        })
    return sorted(out, key=lambda x: x["dept"])
