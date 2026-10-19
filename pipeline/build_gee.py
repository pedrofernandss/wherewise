"""Covariáveis do Google Earth Engine por célula (modelo v2).

Calcula, para cada célula de ../data/cells*.geojson, e grava nas propriedades:
  * wtd_g_med, wtd_g_p25  profundidade do lençol (m), GLOBGM v1.0 steady-state (Verkaik et al. 2024);
                          p25 representa as partes baixas da célula, onde ficam lavoura e captação
  * P_chirps, P_m_chirps  chuva anual e mensal (mm), climatologia CHIRPS 1991-2020
  * pop_wp                população estimada (habitantes), WorldPop 2020 (100 m)
  * sand, clay            areia e argila (%), média 0-30 cm, SoilGrids 250 m v2.0
  * water_frac            fração da célula com água superficial em >50% do tempo (JRC GSW v1.4)

Credenciais (o app publicado não precisa delas, só este script):
  EE_PROJECT=hackathon-511816
  EE_SERVICE_ACCOUNT_KEY=~/.config/hidro/ee-key.json   (conta de serviço; sem ela usa o login
                                                        de `earthengine authenticate`)
Rodar depois de build_data.py:
    python pipeline/build_gee.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import ee

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import OUT, add_sources, log  # noqa: E402

SOURCES = [
    "GLOBGM v1.0 (Verkaik et al. 2024, via Google Earth Engine): steady-state water-table depth, 1 km (model v2)",
    "CHIRPS (via Google Earth Engine): 1991-2020 monthly rainfall climatology, ~5 km (model v2)",
    "SoilGrids 2.0 (ISRIC, via Google Earth Engine): 0-30 cm sand and clay, 250 m (model v2)",
    "WorldPop 2020 (via Google Earth Engine): population per cell, 100 m (validation)",
    "JRC Global Surface Water v1.4 (via Google Earth Engine): permanent surface water share",
]
CHUNK = 250      # células por chamada (limite de tamanho das respostas do Earth Engine)
SCALE = 1000     # m; GLOBGM é ~1 km, CHIRPS ~5 km, SoilGrids/WorldPop/JRC são reamostrados


def init():
    project = os.environ.get("EE_PROJECT", "hackathon-511816")
    key = os.environ.get("EE_SERVICE_ACCOUNT_KEY", "~/.config/hidro/ee-key.json")
    key = os.path.expanduser(key)
    if os.path.exists(key):
        email = json.load(open(key))["client_email"]
        ee.Initialize(ee.ServiceAccountCredentials(email, key), project=project)
        log("Earth Engine: conta de serviço", email)
    else:
        ee.Initialize(project=project)
        log("Earth Engine: credenciais de `earthengine authenticate`")


def population() -> ee.Image:
    """Habitantes por pixel de 100 m (WorldPop 2020, RDC)."""
    return (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "COD"))
            .filter(ee.Filter.eq("year", 2020)).mosaic().unmask(0).rename("pop"))


def covariates() -> ee.Image:
    wtd = ee.Image("projects/sat-io/open-datasets/GLOBGM/STEADY-STATE/globgm-wtd-ss").rename("wtd")

    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/PENTAD").filterDate("1991-01-01", "2021-01-01")
    months = [chirps.filter(ee.Filter.calendarRange(m, m, "month")).sum().divide(30).rename(f"P{m:02d}")
              for m in range(1, 13)]

    def depth_mean(name):
        img = ee.Image(f"projects/soilgrids-isric/{name}_mean")
        b = [f"{name}_0-5cm_mean", f"{name}_5-15cm_mean", f"{name}_15-30cm_mean"]
        return (img.select(b[0]).multiply(5).add(img.select(b[1]).multiply(10)).add(img.select(b[2]).multiply(15))
                .divide(30 * 10).rename(name))   # g/kg -> %
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gt(50).rename("water")

    return ee.Image.cat([wtd, *months, depth_mean("sand"), depth_mean("clay"), water])


def reduce_chunk(img, pop_img, feats):
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": f["properties"]["id"]}) for f in feats])
    reducer = ee.Reducer.mean().combine(ee.Reducer.percentile([25, 50]), sharedInputs=True)
    stats = img.reduceRegions(collection=fc, reducer=reducer, scale=SCALE, tileScale=4)
    # população: soma no pixel nativo (100 m) para não perder pessoas na reamostragem
    stats = pop_img.reduceRegions(collection=stats, reducer=ee.Reducer.sum().setOutputs(["pop_sum"]),
                                  scale=100, tileScale=8)
    for attempt in range(4):
        try:
            return {f["properties"]["id"]: f["properties"] for f in stats.getInfo()["features"]}
        except ee.EEException as e:
            if attempt == 3:
                raise
            log("  repetindo após erro do Earth Engine:", str(e)[:120])
            time.sleep(5 * (attempt + 1))


def main():
    init()
    img = covariates()
    pop_img = population()
    meta = json.loads((OUT / "meta.json").read_text())
    for res, info in (meta.get("resolutions") or {str(meta["cell_deg"]): {"file": "cells.geojson"}}).items():
        path = OUT / info["file"]
        fc = json.loads(path.read_text())
        feats = fc["features"]
        out = {}
        for i in range(0, len(feats), CHUNK):
            out.update(reduce_chunk(img, pop_img, feats[i:i + CHUNK]))
            log(f"  {res}°: {min(i + CHUNK, len(feats))}/{len(feats)} células")
        missing = 0
        for f in feats:
            s = out.get(f["properties"]["id"], {})
            pm = [s.get(f"P{m:02d}_mean") for m in range(1, 13)]
            if s.get("wtd_p25") is None or None in pm:
                missing += 1
                continue
            f["properties"].update({
                "wtd_g_med": round(s["wtd_p50"], 1), "wtd_g_p25": round(s["wtd_p25"], 1),
                "P_chirps": round(sum(pm)), "P_m_chirps": [round(v, 1) for v in pm],
                "pop_wp": round(s.get("pop_sum") or 0),
                "sand": round(s.get("sand_mean") or 0, 1), "clay": round(s.get("clay_mean") or 0, 1),
                "water_frac": round(s.get("water_mean") or 0, 4),
            })
        path.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
        log(f"  {res}°: gravado; {missing} células sem dados do Earth Engine")
    add_sources(SOURCES)


if __name__ == "__main__":
    main()
