// Porta em JavaScript de backend/app/model.py, usada quando o frontend roda
// sem a API (demo estática). tests/test_parity.py compara as duas versões.
(function (root) {
  "use strict";
  const RHO = 1000, G = 9.81;
  const M_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const GPI_FACTORS = ["lito", "perm", "rech", "slope", "dd", "dens", "lu"];
  const GPI_LABELS = {
    lito: "favourable lithology / aquifer", perm: "soil permeability", rech: "recharge",
    slope: "gentle slope", dd: "proximity to drainage", dens: "drainage density",
    lu: "vegetation cover",
  };
  const AHP_MATRIX = [
    [1, 2, 3, 4, 4, 5, 6],
    [1 / 2, 1, 2, 3, 3, 4, 5],
    [1 / 3, 1 / 2, 1, 2, 2, 3, 4],
    [1 / 4, 1 / 3, 1 / 2, 1, 1, 2, 3],
    [1 / 4, 1 / 3, 1 / 2, 1, 1, 2, 3],
    [1 / 5, 1 / 4, 1 / 3, 1 / 2, 1 / 2, 1, 2],
    [1 / 6, 1 / 5, 1 / 4, 1 / 3, 1 / 3, 1 / 2, 1],
  ];
  const RANDOM_INDEX = { 1: 0, 2: 0, 3: 0.58, 4: 0.9, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45 };

  function ahpWeights(matrix = AHP_MATRIX, iters = 100) {
    const n = matrix.length;
    let w = Array(n).fill(1 / n);
    for (let k = 0; k < iters; k++) {
      const v = matrix.map((row) => row.reduce((s, a, j) => s + a * w[j], 0));
      const s = v.reduce((a, b) => a + b, 0);
      w = v.map((x) => x / s);
    }
    const aw = matrix.map((row) => row.reduce((s, a, j) => s + a * w[j], 0));
    const lam = aw.reduce((s, a, i) => s + a / w[i], 0) / n;
    const ci = (lam - n) / (n - 1);
    return { w, lam, cr: ci / RANDOM_INDEX[n] };
  }

  const DEFAULTS = {
    model_version: 1, horizon_months: 12, start_month: 6, area_ha: 5.0, irrigation_mm_day: 5.0, hours_per_day: 8.0,
    WTD_max: 60.0, R_ref: 200.0, h_sat: 8.0, drawdown: 5.0, C_fixo: 1200.0, c_perf: 70.0,
    c_revest: 35.0, C_bomba: 1500.0, C_inst: 1200.0, c_mob_km: 15.0, max_wells: 20,
    Dz_max: 100.0, D_max_km: 15.0, env_flow_frac: 0.1, C_bomba_rio: 2500.0, C_captacao: 1500.0,
    hazen_C: 140.0, pipe_v: 1.0, h_s: 3.0, h_d: 10.0, eta: 0.55, c_energia: 0.22,
    w1: 0.3, w2: 0.25, w3: 0.25, w4: 0.1, w5: 0.1,
  };

  function params(d) {
    const p = Object.assign({}, DEFAULTS);
    for (const k in d || {}) if (k in p && d[k] !== null && d[k] !== undefined && d[k] !== "") p[k] = Number(d[k]);
    p.horizon_months = Math.max(1, Math.min(60, Math.trunc(p.horizon_months)));
    p.start_month = Math.max(1, Math.min(12, Math.trunc(p.start_month)));
    p.max_wells = Math.trunc(p.max_wells);
    return p;
  }

  const AHP = ahpWeights();
  const GPI_W = AHP.w;
  const clip = (x, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, x));
  const sum = (a) => a.reduce((s, x) => s + x, 0);
  const windowMonths = (p) => Array.from({ length: p.horizon_months }, (_, k) => (p.start_month - 1 + k) % 12);

  // modelo v2: troca as covariáveis sintéticas pelas reais quando a célula as tiver
  function effective(c, p) {
    if (p.model_version !== 2) return c;
    const e = Object.assign({}, c);
    if (c.P_m_chirps) { e.P_m = c.P_m_chirps; e.P = c.P_chirps; }
    if (c.bgs_yield_Ls !== undefined && c.bgs_yield_Ls !== null) { e.yield_Ls = c.bgs_yield_Ls; e.lito = c.bgs_fav; }
    if (c.sand !== undefined && c.sand !== null) e.So = clip(0.15 + 0.009 * c.sand - 0.006 * c.clay, 0.1, 0.95);
    return e;
  }

  function wtd(c) {
    const v = c.WTD0 + 0.22 * c.HAND + 0.8 * c.S + 8.0 * c.C + 0.9 * c.D_d_km
      - 0.006 * (c.P - 1600) + 0.01 * (c.ET - 1250) - 6.0 * (c.NDVI - 0.6);
    return clip(v, 1.5, 150.0);
  }

  function gpiFactors(c, R) {
    return {
      lito: c.lito, perm: c.So, rech: clip(R / 400.0), slope: clip(1 - c.S / 15.0),
      dd: Math.exp(-c.D_d_km / 5.0), dens: clip(c.dens / 0.3), lu: c.NDVI,
    };
  }

  function pipe(q, L, p) {
    const d = Math.max(0.05, Math.sqrt((4 * q) / (Math.PI * p.pipe_v)));
    const hf = q > 0 ? (10.67 * L * Math.pow(q, 1.852)) / (Math.pow(p.hazen_C, 1.852) * Math.pow(d, 4.87)) : 0;
    return [d, hf];
  }

  function riverOption(src, c, qDem, months, p, hours) {
    const D_m = src.d_km * 1000;
    const dz = c.E_low - src.z;
    const k = src.regime !== undefined ? src.regime : 0.9;
    const pm = c.P_m;
    const pmean = sum(pm) / 12;
    const qm = [];
    for (let m = 0; m < 12; m++) qm.push(Math.max(0.05, 1 + k * (pm[(m + 11) % 12] / pmean - 1)) * src.q);
    const qWin = sum(months.map((m) => qm[m])) / months.length;
    const qAvail = p.env_flow_frac * qWin;
    const A_sup = Math.min(1, qAvail / qDem) * clip(1 - Math.max(dz, 0) / p.Dz_max) * clip(1 - src.d_km / p.D_max_km);
    const R_clima = months.filter((m) => p.env_flow_frac * qm[m] >= qDem).length / months.length;
    const [d, hf] = pipe(qDem, D_m, p);
    const H_t = Math.max(dz, 0) + hf + p.h_s + p.h_d;
    const kw = (RHO * G * qDem * H_t) / p.eta / 1000;
    const C_op = kw * hours * p.c_energia;
    const C_cap = p.C_bomba_rio + p.C_captacao + D_m * (8 + 150 * d);
    return {
      name: src.name || "local drainage (DEM)", D_km: src.d_km, Q_rio: Math.round(src.q * 100) / 100,
      Q_disp: Math.round(qAvail * 1e4) / 1e4, dz: Math.round(dz * 10) / 10, H_t: Math.round(H_t * 10) / 10,
      pipe_d_mm: Math.round(d * 1000), A_sup, R_clima, C_bombeamento: C_op,
      C_bombeamento_ano: (C_op * 12) / months.length, C_capex: C_cap, C_total: C_cap + C_op,
    };
  }

  function evaluate(c0, p) {
    const c = effective(c0, p);
    const months = windowMonths(p);
    const hpd = p.hours_per_day;
    const qDem = (p.area_ha * p.irrigation_mm_day * 10) / (hpd * 3600);
    const need = [];
    for (let m = 0; m < 12; m++) need.push(clip(1 - c.P_m[m] / Math.max(c.PET_m[m], 1), 0.15, 1.0));
    const hours = sum(months.map((m) => M_DAYS[m] * hpd * need[m]));

    const alpha = 0.15 + 0.2 * c.So;
    const R = alpha * c.P;
    const W = p.model_version === 2 && c.wtd_g_p25 !== undefined && c.wtd_g_p25 !== null ? clip(c.wtd_g_p25, 1.5, 150.0) : wtd(c);
    const fx = gpiFactors(c, R);
    const GPI = sum(GPI_FACTORS.map((f, i) => GPI_W[i] * fx[f]));
    const P_poco = clip(GPI * (1 - W / p.WTD_max) * Math.min(1, R / p.R_ref));
    const H = W + p.h_sat;
    const qWell = c.yield_Ls / 1000;
    const nWells = Math.min(p.max_wells, Math.max(1, Math.ceil(qDem / qWell)));
    const yieldOk = nWells * qWell >= qDem;
    const unit = p.C_fixo + (p.c_perf + p.c_revest) * H + p.C_bomba + p.C_inst;
    const C_poco_capex = nWells * unit + p.c_mob_km * c.D_road_km;
    const H_t_w = W + p.drawdown + p.h_d;
    const C_poco_op = ((RHO * G * qDem * H_t_w) / p.eta / 1000) * hours * p.c_energia;
    const C_poco_total = C_poco_capex + C_poco_op;
    const A_sub = P_poco * (yieldOk ? 1.0 : 0.6);
    const pm = c.P_m;
    const R_clima_poco = clip(0.6 + (0.4 * (sum(months.map((m) => pm[m])) / months.length)) / (sum(pm) / 12));

    const opts = [riverOption(c.major, c, qDem, months, p, hours), riverOption(c.stream, c, qDem, months, p, hours)];
    const rio = opts[1].A_sup > opts[0].A_sup || (opts[1].A_sup === opts[0].A_sup && opts[1].C_total < opts[0].C_total) ? opts[1] : opts[0];
    const A_sup = rio.A_sup;

    const E_custo = rio.C_total / (C_poco_total + rio.C_total);
    const R_clima = 0.5 + 0.5 * (R_clima_poco - rio.R_clima);
    const A_acesso = 0.7 * Math.exp(-c.D_road_km / 25) + 0.3 * Math.exp(-c.D_town_km / 60);
    const comp = { A_sub, A_sup_inv: 1 - A_sup, E_custo, R_clima, A_acesso };
    const ws = [p.w1, p.w2, p.w3, p.w4, p.w5];
    const wsum = sum(ws) || 1;
    const IR = sum(Object.values(comp).map((v, i) => ws[i] * v)) / wsum;

    let cls;
    if (Math.max(A_sub, A_sup) < 0.12) cls = "nao_recomendado";
    else if (Math.abs(IR - 0.5) < 0.03) cls = "inconclusivo";
    else if (IR > 0.5) cls = P_poco >= 0.45 ? "poco_alto" : "poco_viavel";
    else cls = "rio";
    const rec = IR > 0.5 ? "poco" : "rio";

    let cand;
    if (rec === "poco") {
      cand = {};
      for (const f of ["lito", "perm", "slope", "dd", "rech"]) cand[GPI_LABELS[f]] = fx[f];
      cand[W < p.WTD_max / 2 ? "shallow water table" : "deep water table"] = 1 - W / p.WTD_max;
    } else {
      cand = {
        "river flow": Math.min(1, rio.Q_disp / qDem),
        "river-to-field lift": clip(1 - Math.max(rio.dz, 0) / p.Dz_max),
        "distance to river": clip(1 - rio.D_km / p.D_max_km),
        "cost versus well": 1 - E_custo,
      };
    }
    const keys = Object.keys(cand);
    // mesmo critério de desempate do max/min do Python: primeira ocorrência
    let pos = keys[0], neg = keys[0];
    for (const k of keys) { if (cand[k] > cand[pos]) pos = k; if (cand[k] < cand[neg]) neg = k; }

    const conf = clip(0.35 + 0.4 * Math.exp(-c.D_station_km / 120) + 0.5 * Math.abs(IR - 0.5));

    return {
      id: c.id, cls, rec, IR, P_poco, GPI, WTD: W, H, R, AI: c.P / c.PET,
      n_pocos: nWells, vazao_poco_Ls: c.yield_Ls, vazao_ok: yieldOk,
      C_poco: C_poco_capex, C_poco_op, C_poco_total, A_sub, A_sup,
      R_clima_poco, R_clima_rio: rio.R_clima, E_custo, A_acesso, componentes: comp,
      rio, fatores_gpi: fx, fator_pos: pos, fator_neg: neg, confianca: conf,
      Q_demanda: qDem, horas_op: hours, turfeira: c.peat,
    };
  }

  function summarize(cells, results) {
    const by = {};
    cells.forEach((c, i) => {
      const r = results[i];
      for (const d of c.depts) {
        const s = by[d] || (by[d] = { dept: d, n: 0, classes: {}, p_sum: 0, p_n: 0, ir_sum: 0, c_poco: [], c_rio: [] });
        s.n += 1;
        s.classes[r.cls] = (s.classes[r.cls] || 0) + 1;
        s.ir_sum += r.IR;
        if (r.rec === "poco") { s.p_sum += r.P_poco; s.p_n += 1; s.c_poco.push(r.C_poco_total); }
        else s.c_rio.push(r.rio.C_total);
      }
    });
    const med = (a) => (a.length ? a.slice().sort((x, y) => x - y)[Math.floor(a.length / 2)] : null);
    return Object.values(by).map((s) => {
      let dom = null;
      for (const k in s.classes) if (dom === null || s.classes[k] > s.classes[dom]) dom = k;
      return {
        dept: s.dept, n_celulas: s.n, classes: s.classes, classe_dominante: dom,
        pct_poco: Math.round((100 * s.p_n) / s.n),
        P_poco_media: s.p_n ? Math.round((s.p_sum / s.p_n) * 1e4) / 1e4 : null,
        IR_medio: Math.round((s.ir_sum / s.n) * 1e4) / 1e4,
        C_poco_mediano: med(s.c_poco), C_rio_mediano: med(s.c_rio),
      };
    }).sort((a, b) => (a.dept < b.dept ? -1 : 1));
  }

  const api = { evaluate, summarize, params, DEFAULTS, GPI_W, AHP, GPI_FACTORS, GPI_LABELS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HidroModel = api;
})(typeof window !== "undefined" ? window : globalThis);
