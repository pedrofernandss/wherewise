"""Mapas base estáticos gerados no Google Earth Engine (Web Mercator, 256 px).

Gera uma vez os blocos que cobrem a RDC e grava em ../frontend/tiles/<camada>/<z>/<x>/<y>.<ext>,
mais um tiles/manifest.json lido pelo frontend. O app só serve os arquivos; não fala com o
Earth Engine nem precisa da credencial.

  sat      mosaico Sentinel-2 sem nuvens (máscara SCL, mediana 2023-2024), JPEG, zoom 4-9
           (opcional e lento: os zooms baixos levam ~1 min por bloco; o app usa o satélite do Azure Maps)
  relief   relevo do SRTM (30 m): cores por altitude + sombreamento, JPEG, zoom 4-8
  cover    uso do solo ESA WorldCover 2021 (10 m), PNG, zoom 4-8

Usa ee.data.computePixels (permissão de leitura basta). Retoma de onde parou: blocos já gravados
são pulados. Credenciais como em build_gee.py (EE_PROJECT, EE_SERVICE_ACCOUNT_KEY).
    python pipeline/build_tiles.py [camada ...]
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import ee
from shapely.geometry import box, shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_data import OUT, ROOT, log  # noqa: E402
from build_gee import init  # noqa: E402

TILES = ROOT / "frontend" / "tiles"
R = 6378137.0
WORKERS = 8
MIN_ZOOM = 4

# ESA WorldCover v200: classes e cores oficiais (legenda no frontend)
COVER = [(10, "Tree cover", "006400"), (20, "Shrubland", "ffbb22"), (30, "Grassland", "ffff4c"),
         (40, "Cropland", "f096ff"), (50, "Built-up", "fa0000"), (60, "Bare / sparse", "b4b4b4"),
         (70, "Snow and ice", "f0f0f0"), (80, "Permanent water", "0064c8"), (90, "Herbaceous wetland", "0096a0"),
         (95, "Mangroves", "00cf75"), (100, "Moss and lichen", "fae6a0")]


def layers() -> dict:
    # Sentinel-2: máscara de nuvem/sombra pela classificação de cena (SCL) de cada imagem, mediana 2023-2024
    # (Cloud Score+ dá um mosaico melhor, mas ficou lento demais para gerar ~760 blocos)
    clear = lambda im: im.updateMask(im.select("SCL").remap([3, 8, 9, 10, 11], [0, 0, 0, 0, 0], 1))
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate("2023-01-01", "2025-01-01")
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)).map(clear).median())
    dem = ee.Image("USGS/SRTMGL1_003")
    shade = ee.Terrain.hillshade(dem.multiply(6), 315, 35).divide(255)   # exagero vertical: a bacia é muito plana
    tint = dem.visualize(min=250, max=2200, palette=["9fbf8f", "cfd8a6", "e6dcb4", "c9ad87", "a07f62", "8a7a72"])
    relief = tint.multiply(shade.multiply(0.55).add(0.45)).uint8()
    # mar em azul-claro: onde o SRTM não tem dado (quadrados só de oceano) ou tem altitude <= 0
    sea = ee.Image.constant([206, 222, 228]).rename(["vis-red", "vis-green", "vis-blue"]).uint8()
    relief = sea.where(dem.unmask(0).gt(0), relief.unmask(0))
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    vals = [c[0] for c in COVER]
    return {
        "sat": {"img": s2.visualize(bands=["B4", "B3", "B2"], min=150, max=1900, gamma=1.25), "fmt": "JPEG", "ext": "jpg",
                "max_zoom": 9, "label": "Satellite", "attribution": "Contains modified Copernicus Sentinel-2 data (2023-24), SCL cloud mask, via Google Earth Engine"},
        "relief": {"img": relief, "fmt": "JPEG", "ext": "jpg",
                   "max_zoom": 8, "label": "Relief", "attribution": "SRTM 1 arc-second (NASA/USGS), via Google Earth Engine"},
        "cover": {"img": wc.remap(vals, list(range(len(vals)))).visualize(min=0, max=len(vals) - 1, palette=[c[2] for c in COVER]),
                  "fmt": "PNG", "ext": "png", "max_zoom": 8, "label": "Land cover",
                  "attribution": "ESA WorldCover 2021 v200, via Google Earth Engine",
                  "legend": [{"label": c[1], "color": "#" + c[2]} for c in COVER if c[0] not in (70, 100)]},
    }


def tile_bounds_lonlat(z, x, y):
    n = 2 ** z
    lon0, lon1 = x / n * 360 - 180, (x + 1) / n * 360 - 180
    lat = lambda t: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * t / n))))
    return lon0, lat(y + 1), lon1, lat(y)


def tiles_for(area, zmax):
    out = []
    minx, miny, maxx, maxy = area.bounds
    for z in range(MIN_ZOOM, zmax + 1):
        n = 2 ** z
        x0, x1 = int((minx + 180) / 360 * n), int((maxx + 180) / 360 * n)
        ty = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
        for x in range(x0, x1 + 1):
            for y in range(ty(maxy), ty(miny) + 1):
                if area.intersects(box(*tile_bounds_lonlat(z, x, y))):
                    out.append((z, x, y))
    return out


def render(img, fmt, z, x, y) -> bytes:
    size = 2 * math.pi * R / 2 ** z
    grid = {"dimensions": {"width": 256, "height": 256}, "crsCode": "EPSG:3857",
            "affineTransform": {"scaleX": size / 256, "shearX": 0, "translateX": -math.pi * R + x * size,
                                "shearY": 0, "scaleY": -size / 256, "translateY": math.pi * R - y * size}}
    for attempt in range(5):
        try:
            return ee.data.computePixels({"expression": img, "fileFormat": fmt, "grid": grid})
        except ee.EEException as e:
            if attempt == 4:
                raise
            time.sleep(3 * (attempt + 1) + (10 if "rate" in str(e).lower() or "429" in str(e) else 0))


def main(names):
    init()
    country = unary_union([shape(f["geometry"]).buffer(0) for f in json.loads((OUT / "departments.geojson").read_text())["features"]])
    area = box(*country.buffer(0.5).bounds)   # retângulo: o Leaflet pede todos os blocos dentro de "bounds"
    defs = layers()
    manifest_path = TILES / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"layers": {}}
    for name in names:
        d = defs[name]
        todo = [t for t in tiles_for(area, d["max_zoom"])
                if not (TILES / name / str(t[0]) / str(t[1]) / f"{t[2]}.{d['ext']}").exists()]
        total = len(tiles_for(area, d["max_zoom"]))
        log(f"{name}: {total} blocos ({len(todo)} a gerar)")
        t0, done = time.time(), 0
        with ThreadPoolExecutor(WORKERS) as pool:
            futs = {pool.submit(render, d["img"], d["fmt"], *t): t for t in todo}
            for f in as_completed(futs):
                z, x, y = futs[f]
                p = TILES / name / str(z) / str(x) / f"{y}.{d['ext']}"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(f.result())
                done += 1
                if done % 100 == 0:
                    log(f"  {name}: {done}/{len(todo)} ({time.time() - t0:.0f}s)")
        size = sum(p.stat().st_size for p in (TILES / name).rglob(f"*.{d['ext']}"))
        log(f"  {name}: pronto, {size / 1e6:.1f} MB")
        manifest["layers"][name] = {k: d[k] for k in ("label", "ext", "max_zoom", "attribution")} | (
            {"legend": d["legend"]} if "legend" in d else {}) | {"min_zoom": MIN_ZOOM, "bounds": list(area.bounds)}
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:] or ["relief", "cover"])
