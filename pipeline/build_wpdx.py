"""Pontos de água do WPdx-Basic (Water Point Data Exchange) para a RDC.

Baixa (com cache) os pontos da RDC, atribui cada um a uma célula da grade em cada
resolução e grava, em ../data/:
  * waterpoints.json  pontos para a camada do mapa
  * wpdx_cells.json   contagens por célula e resolução, usadas em /api/validation

Rodar depois de build_data.py (lê os cells*.geojson que ele grava):
    python pipeline/build_wpdx.py

Filtros e cuidados (detalhes em VALIDACAO.md):
  * só registros com country_id == "CD": o WPdx-Basic também traz, com coordenadas dentro da
    RDC, pontos de conjuntos de Uganda, Ruanda etc. (provável erro de georreferência);
  * "poço" = water_source_category == "Well" (poço tubular ou poço protegido);
  * funcional = status_id == "Yes".
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import OUT, add_sources, fetch, log  # noqa: E402

WPDX = "https://data.waterpointdata.org/resource/jfkt-jmqa.json"
FIELDS = ["lat_deg", "lon_deg", "country_id", "water_source_clean", "water_source_category",
          "water_tech_category", "status_id", "status_clean", "install_year", "report_date", "dataset_title"]
PAGE = 5000
SURVEY_KM = 50   # células a até 50 km de algum ponto WPdx contam como "área levantada"


def download() -> list[dict]:
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"$select": ",".join(FIELDS), "$where": "clean_country_id='COD'",
                                    "$order": "row_id", "$limit": PAGE, "$offset": offset})
        page = json.loads(fetch(f"{WPDX}?{q}", f"wpdx_cod_{offset}.json"))
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def main():
    raw = download()
    pts = []
    for r in raw:
        if r.get("country_id") != "CD" or "lat_deg" not in r:
            continue
        status = {"Yes": 1, "No": 0}.get(r.get("status_id"), -1)
        pts.append({
            "lon": round(float(r["lon_deg"]), 5), "lat": round(float(r["lat_deg"]), 5),
            "well": r.get("water_source_category") == "Well",
            "source": r.get("water_source_clean") or "Unknown",
            "tech": r.get("water_tech_category") or "Unknown",
            "status": status, "status_txt": r.get("status_clean") or "Unknown",
            "year": int(r["install_year"]) if r.get("install_year", "").isdigit() else None,
            "dataset": r.get("dataset_title") or "",
        })
    log(len(raw), "registros WPdx na RDC;", len(pts), "com country_id CD")

    meta = json.loads((OUT / "meta.json").read_text())
    resolutions = meta.get("resolutions") or {str(meta["cell_deg"]): {"file": "cells.geojson"}}
    per_res, surveyed = {}, {}
    plon = np.array([p["lon"] for p in pts]); plat = np.array([p["lat"] for p in pts])
    for res, info in resolutions.items():
        feats = json.loads((OUT / info["file"]).read_text())["features"]
        geoms = [shape(f["geometry"]) for f in feats]
        ids = [f["properties"]["id"] for f in feats]
        tree = STRtree(geoms)
        agg = defaultdict(lambda: [0, 0, 0])   # [pontos, poços, poços funcionais]
        outside = 0
        for p in pts:
            pt = Point(p["lon"], p["lat"])
            hit = next((i for i in tree.query(pt) if geoms[i].covers(pt)), None)
            if hit is None:
                outside += 1
                continue
            a = agg[ids[hit]]
            a[0] += 1
            if p["well"]:
                a[1] += 1
                a[2] += p["status"] == 1
        per_res[res] = {str(k): v for k, v in sorted(agg.items())}
        near = []
        for f in feats:
            c = f["properties"]
            d = np.hypot((plon - c["lon"]) * 111.32 * np.cos(np.radians(c["lat"])), (plat - c["lat"]) * 110.57)
            if d.min() <= SURVEY_KM:
                near.append(c["id"])
        surveyed[res] = near
        log(f"  {res}°: {len(agg)} células com pontos; {outside} pontos fora da grade; "
            f"{len(near)} células na área levantada (≤{SURVEY_KM} km)")

    titles = sorted({p["dataset"] for p in pts})
    (OUT / "waterpoints.json").write_text(json.dumps({
        "source": "Water Point Data Exchange (WPdx-Basic), data.waterpointdata.org, dataset jfkt-jmqa",
        "datasets": titles,
        "fields": ["lon", "lat", "well", "status", "source", "tech", "status_txt", "year"],
        "points": [[p["lon"], p["lat"], int(p["well"]), p["status"], p["source"], p["tech"], p["status_txt"], p["year"]]
                   for p in pts],
    }, ensure_ascii=False, separators=(",", ":")))
    (OUT / "wpdx_cells.json").write_text(json.dumps({
        "fields": ["n_points", "n_wells", "n_wells_functional"], "cells": per_res,
        "survey_km": SURVEY_KM, "surveyed": surveyed,
    }, separators=(",", ":")))
    log("gravado: waterpoints.json, wpdx_cells.json")
    add_sources([f"Water Point Data Exchange (WPdx-Basic): {len(pts)} DRC water points (validation)"])


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    main()
