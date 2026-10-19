"""Produtividade de aquíferos do BGS (Africa Groundwater Atlas, MacDonald et al. 2012) por célula.

Baixa (com cache) a grade de 5 km de produtividade de águas subterrâneas da África e acrescenta a
cada célula, em ../data/cells*.geojson:
  * bgs_class     classe predominante (VL, L, LM, M, H, VH)
  * bgs_yield_Ls  vazão típica por poço, média dos valores representativos das classes na célula
  * bgs_fav       favorabilidade 0-1 derivada da classe, usada no GPI do modelo v2

Rodar depois de build_data.py:
    python pipeline/build_bgs.py
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
from shapely import contains_xy, prepare
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import BBOX, OUT, add_sources, fetch, log  # noqa: E402

URL = "https://www.bgs.ac.uk/groundwater/download/africa-groundwater-productivity-map-xyz-ascii-file/?wpdmdl=5969"
# classes do mapa (L/s, readme do BGS): VL <0,1 · L 0,1-0,5 · LM 0,5-1 · M 1-5 · H 5-20 · VH >20
CLASSES = ["VL", "L", "LM", "M", "H", "VH"]
YIELD = {"VL": 0.05, "L": 0.3, "LM": 0.75, "M": 2.5, "H": 10.0, "VH": 20.0}   # valor representativo (L/s)
FAV = {"VL": 0.05, "L": 0.2, "LM": 0.4, "M": 0.6, "H": 0.8, "VH": 0.95}


def load_grid():
    z = zipfile.ZipFile(io.BytesIO(fetch(URL, "bgs_gwprod_v1.zip")))
    name = next(n for n in z.namelist() if n.startswith("xyzASCII_gwprod"))
    xs, ys, cs = [], [], []
    for line in z.read(name).decode().splitlines()[1:]:
        x, y, c = line.split("\t")
        x, y = float(x), float(y)
        if c in YIELD and BBOX[0] - 0.1 <= x <= BBOX[2] + 0.1 and BBOX[1] - 0.1 <= y <= BBOX[3] + 0.1:
            xs.append(x); ys.append(y); cs.append(c)
    return np.array(xs), np.array(ys), np.array(cs)


def main():
    xs, ys, cs = load_grid()
    log(len(cs), "pontos da grade BGS na região")
    meta = json.loads((OUT / "meta.json").read_text())
    for res, info in (meta.get("resolutions") or {str(meta["cell_deg"]): {"file": "cells.geojson"}}).items():
        path = OUT / info["file"]
        fc = json.loads(path.read_text())
        empty = 0
        for f in fc["features"]:
            g = shape(f["geometry"])
            x0, y0, x1, y1 = g.bounds
            m = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
            prepare(g)
            inside = cs[m][contains_xy(g, xs[m], ys[m])] if m.any() else cs[:0]
            if not inside.size:  # célula menor que o passo de 5 km: usa o ponto mais próximo do centro
                c = f["properties"]
                inside = cs[[int(np.argmin((xs - c["lon"]) ** 2 + (ys - c["lat"]) ** 2))]]
                empty += 1
            cnt = Counter(inside.tolist())
            cls = max(cnt, key=lambda k: (cnt[k], CLASSES.index(k)))
            f["properties"].update({
                "bgs_class": cls,
                "bgs_yield_Ls": round(float(np.mean([YIELD[k] for k in inside])), 2),
                "bgs_fav": round(float(np.mean([FAV[k] for k in inside])), 3),
            })
        path.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
        dist = Counter(f["properties"]["bgs_class"] for f in fc["features"])
        log(f"  {res}°: classes {dict(sorted(dist.items(), key=lambda t: CLASSES.index(t[0])))}; "
            f"{empty} células pelo ponto mais próximo")
    add_sources(["BGS Africa Groundwater Atlas (MacDonald et al. 2012): aquifer productivity, 5 km (model v2)"])


if __name__ == "__main__":
    main()
