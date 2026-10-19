"""Pipeline de dados do protótipo Wherewise.

Baixa dados abertos leves, deriva covariáveis por célula da grade e grava os
arquivos que a API e o frontend consomem em ../data/.

Região: República Democrática do Congo (RDC).

Fontes reais:
  * geoBoundaries (gbOpen COD ADM1, OSM) -> limites das 26 províncias
  * Natural Earth 10m (rios principais, estradas, cidades, contorno dos países)
                                         -> github.com/nvkelso/natural-earth-vector
  * AWS Terrain Tiles (Terrarium, derivado de SRTM/NASADEM) -> elevação, declive,
    curvatura e rede de drenagem derivada (D8 + priority-flood, estilo HydroSHEDS)
  * NOAA GHCN-Daily (estações da RDC e vizinhos) + NASA POWER (climatologia
    2001-2025 em grade de 1,5°, cobre as lacunas do GHCN) -> normais mensais de
    precipitação e temperatura (PET por Hargreaves)

Covariáveis sintéticas (marcadas em meta.json): domínios hidrogeológicos,
permeabilidade do solo, NDVI, vazões de literatura dos grandes rios.

Uso:
    python pipeline/build_data.py            # baixa (com cache) e gera data/
"""
from __future__ import annotations

import csv
import heapq
import io
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import LineString, MultiLineString, Point, box, mapping, shape
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data"
CACHE = Path(os.environ.get("HIDRO_CACHE", ROOT / ".cache"))

NE_BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
GHCN = "https://noaa-ghcn-pds.s3.amazonaws.com/"
GB_ADM1 = ("https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/COD/ADM1/"
           "geoBoundaries-COD-ADM1_simplified.geojson")
POWER = ("https://power.larc.nasa.gov/api/temporal/climatology/point?parameters=PRECTOTCORR,T2M,T2M_RANGE"
         "&community=AG&longitude={lon}&latitude={lat}&format=JSON")
POWER_STEP = 1.5        # espaçamento da grade de pseudo-estações NASA POWER (graus)
# geoBoundaries mistura nomes em inglês e francês; usamos os nomes oficiais (francês)
PROV_NAMES = {"Lower Uele": "Bas-Uele", "Upper Uele": "Haut-Uele", "North Kivu": "Nord-Kivu",
              "South Kivu": "Sud-Kivu", "Central Kasai": "Kasaï-Central", "Kasai": "Kasaï",
              "Kasai-Oriental": "Kasaï-Oriental"}

# Área de processamento (um pouco maior que o país para não truncar bacias)
BBOX = (12.0, -13.6, 31.4, 5.5)
# resoluções da grade: a primeira é a padrão (cells.geojson); as demais vão para cells_<deg>.geojson
RESOLUTIONS = (0.4, 0.2)   # ~44 km e ~22 km
DEM_ZOOM = 6            # ~2,4 km por pixel
STREAM_MIN_KM2 = 50     # limiar de drenagem (densidade / distância à drenagem)
RIVER_MIN_KM2 = 500     # limiar de "rio bombeável" derivado do DEM
BUDYKO_W = 3.5          # calibrado para escoamento ~350-400 mm/ano na bacia do Congo

# Vazões médias anuais aproximadas (m³/s), ordens de grandeza de literatura (GRDC /
# ORE-HYBAM / SO-HYBAM); conferir no GRDC antes de usar fora do protótipo.
# Regime: amortecimento da sazonalidade (0 = constante, 1 = segue a chuva local).
# Nomes como aparecem no Natural Earth (rivers_lake_centerlines) dentro da RDC.
MAJOR_RIVERS = {
    "Congo": (41000, 0.25), "Lualaba": (3500, 0.4), "Kasai": (9900, 0.35), "Ubangi": (4000, 0.5),
    "Ruki": (3500, 0.3), "Busira": (1800, 0.35), "Tshuapa": (800, 0.4), "Lomami": (900, 0.45),
    "Sankuru": (1800, 0.45), "Lukenie": (600, 0.45), "Fimi": (1200, 0.35), "Kwango": (2700, 0.45),
    "Kwilu": (900, 0.5), "Lua": (200, 0.55), "Aruwimi": (2000, 0.4), "Ituri": (500, 0.5),
    "Uele": (1200, 0.55), "Kibali": (300, 0.6), "Bomu": (800, 0.6), "Mongala": (800, 0.45),
    "Lokoro": (400, 0.45), "Ebola": (200, 0.5), "Luvua": (650, 0.35), "Luapula": (700, 0.35),
    "Lufira": (150, 0.65), "Lukuga": (200, 0.2), "Rusizi": (230, 0.3), "Semliki": (120, 0.3),
    "Inkisi": (250, 0.6),
}

M_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch(url: str, name: str) -> bytes:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / name
    if not p.exists():
        log("baixando", url)
        with urllib.request.urlopen(url, timeout=120) as r:
            p.write_bytes(r.read())
    return p.read_bytes()


def add_sources(real: list[str]):
    """Registra fontes extras no meta.json (usado pelos scripts build_bgs/build_gee/build_wpdx)."""
    p = OUT / "meta.json"
    m = json.loads(p.read_text())
    src = m.setdefault("sources", {"real": [], "synthetic": []})
    for r in real:
        key = r.split(":")[0]
        src["real"] = [x for x in src["real"] if x.split(":")[0] != key] + [r]
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2))


def ne(name: str) -> dict:
    return json.loads(fetch(NE_BASE + name + ".geojson", name + ".geojson"))


# ----------------------------------------------------------------------------
# Geometria auxiliar
# ----------------------------------------------------------------------------
def km_per_deg(lat: float) -> tuple[float, float]:
    return 111.32 * math.cos(math.radians(lat)), 110.57


def to_local_km(geom, lat0: float):
    """Projeção equiretangular simples centrada em lat0 (use a latitude local)."""
    from shapely.affinity import scale
    kx, ky = km_per_deg(lat0)
    return scale(geom, xfact=kx, yfact=ky, origin=(0, 0))


def rnd(geom, nd=3):
    def r(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(c[0], nd), round(c[1], nd)]
        return [r(x) for x in c]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


# ----------------------------------------------------------------------------
# DEM: mosaico Terrarium + priority-flood + D8
# ----------------------------------------------------------------------------
def tile_xy(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def load_dem():
    z = DEM_ZOOM
    x0, y0 = tile_xy(BBOX[0], BBOX[3], z)
    x1, y1 = tile_xy(BBOX[2], BBOX[1], z)
    rows = []
    for ty in range(y0, y1 + 1):
        row = []
        for tx in range(x0, x1 + 1):
            png = fetch(TERRARIUM.format(z=z, x=tx, y=ty), f"t{z}_{tx}_{ty}.png")
            a = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(np.float64)
            row.append(a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768)
        rows.append(np.hstack(row))
    dem = np.vstack(rows)
    n = 2 ** z
    H, W = dem.shape
    px = (np.arange(W) + 0.5) / 256 + x0
    py = (np.arange(H) + 0.5) / 256 + y0
    lons = px / n * 360 - 180
    lats = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * py / n))))
    cmask = (lons >= BBOX[0]) & (lons <= BBOX[2])
    rmask = (lats >= BBOX[1]) & (lats <= BBOX[3])
    return dem[np.ix_(rmask, cmask)], lons[cmask], lats[rmask]


def hydrology(dem, lons, lats, runoff_mm):
    """Priority-flood (Barnes 2014) dá direção de fluxo e ordem topológica."""
    H, W = dem.shape
    N = H * W
    flat = dem.ravel()
    ocean = flat <= 0
    filled = flat.copy()
    down = np.full(N, -1, dtype=np.int64)
    seen = np.zeros(N, dtype=bool)
    heap = []
    for i in range(N):
        r, c = divmod(i, W)
        if ocean[i] or r == 0 or c == 0 or r == H - 1 or c == W - 1:
            heapq.heappush(heap, (filled[i], i))
            seen[i] = True
    order = []
    nbr = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while heap:
        e, i = heapq.heappop(heap)
        order.append(i)
        r, c = divmod(i, W)
        for dr, dc in nbr:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W:
                j = rr * W + cc
                if not seen[j]:
                    seen[j] = True
                    filled[j] = max(filled[j], e + 1e-4)
                    down[j] = i
                    heapq.heappush(heap, (filled[j], j))
    order = np.array(order)
    # área de cada pixel (km²)
    dx = abs(lons[1] - lons[0])
    dys = np.abs(np.gradient(lats))
    area_row = dx * 111.32 * np.cos(np.radians(lats)) * dys * 110.57
    area = np.repeat(area_row, W)
    acc = area.copy()
    vol = runoff_mm.ravel() / 1000 * area * 1e6  # m³/ano
    for i in order[::-1]:
        d = down[i]
        if d >= 0:
            acc[d] += acc[i]
            vol[d] += vol[i]
    q = vol / (365.25 * 86400)
    return acc.reshape(H, W), q.reshape(H, W), down.reshape(H, W), ocean.reshape(H, W)


def stream_lines(acc, down, lons, lats, thr):
    H, W = acc.shape
    segs = []
    idx = np.flatnonzero(acc.ravel() >= thr)
    for i in idx:
        d = down.ravel()[i]
        if d < 0:
            continue
        r, c = divmod(int(i), W)
        rd, cd = divmod(int(d), W)
        segs.append(((lons[c], lats[r]), (lons[cd], lats[rd])))
    merged = linemerge(MultiLineString(segs))
    return merged


# ----------------------------------------------------------------------------
# Clima: GHCN-Daily -> normais mensais
# ----------------------------------------------------------------------------
def ra_mm_day(lat_deg, month):
    """Radiação extraterrestre (FAO-56) em mm/dia equivalentes, dia 15 do mês."""
    j = sum(M_DAYS[:month]) + 15
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * j / 365)
    dec = 0.409 * math.sin(2 * math.pi * j / 365 - 1.39)
    ws = math.acos(max(-1, min(1, -math.tan(phi) * math.tan(dec))))
    ra = 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(phi) * math.sin(dec) +
                                              math.cos(phi) * math.cos(dec) * math.sin(ws))
    return ra * 0.408


def load_stations(region):
    txt = fetch(GHCN + "ghcnd-stations.txt", "ghcnd-stations.txt").decode()
    out = []
    for line in txt.splitlines():
        lat, lon = float(line[12:20]), float(line[21:30])
        if region.contains(Point(lon, lat)):
            sid = line[:11]
            try:
                raw = fetch(GHCN + f"csv/by_station/{sid}.csv", f"ghcn_{sid}.csv").decode()
            except Exception as e:  # estação sem arquivo
                log("sem dados", sid, e)
                continue
            m = defaultdict(lambda: defaultdict(list))
            for r in csv.DictReader(io.StringIO(raw)):
                if r["Q_FLAG"] or r["ELEMENT"] not in ("PRCP", "TMAX", "TMIN"):
                    continue
                m[r["ELEMENT"]][r["DATE"][:6]].append(float(r["DATA_VALUE"]) / 10)
            prcp = [[] for _ in range(12)]
            for ym, v in m["PRCP"].items():
                if len(v) >= 25:  # mês quase completo
                    mo = int(ym[4:]) - 1
                    prcp[mo].append(sum(v) / len(v) * M_DAYS[mo])
            if min(len(p) for p in prcp) < 5:  # cobertura do GHCN na RDC é rala
                continue
            tx = [[] for _ in range(12)]
            tn = [[] for _ in range(12)]
            for el, dst in (("TMAX", tx), ("TMIN", tn)):
                for ym, v in m[el].items():
                    if len(v) >= 15:
                        dst[int(ym[4:]) - 1].append(sum(v) / len(v))
            st = {
                "id": sid, "name": line[41:71].strip().title(), "lat": lat, "lon": lon,
                "elev": float(line[31:37]),
                "prcp": [round(float(np.mean(p)), 1) for p in prcp],
                "n_months": sum(len(p) for p in prcp),
            }
            if min(len(t) for t in tx) >= 5 and min(len(t) for t in tn) >= 5:
                st["tmax"] = [float(np.mean(t)) for t in tx]
                st["tmin"] = [float(np.mean(t)) for t in tn]
            out.append(st)
    log(len(out), "estações GHCN com normais válidas")
    return out


def load_power(region, step=POWER_STEP):
    """Pseudo-estações NASA POWER (climatologia MERRA-2 2001-2025) numa grade regular."""
    out = []
    for lat in np.arange(BBOX[1] + step / 2, BBOX[3], step):
        for lon in np.arange(BBOX[0] + step / 2, BBOX[2], step):
            lat, lon = round(float(lat), 2), round(float(lon), 2)
            if not region.contains(Point(lon, lat)):
                continue
            try:
                d = json.loads(fetch(POWER.format(lon=lon, lat=lat), f"power_{lon}_{lat}.json"))
            except Exception as e:
                log("POWER falhou", lon, lat, e)
                continue
            par = d["properties"]["parameter"]
            mo = list(par["T2M"])[:12]  # JAN..DEC
            t, rg = [par["T2M"][m] for m in mo], [par["T2M_RANGE"][m] for m in mo]
            out.append({
                "id": f"POWER_{lon}_{lat}", "name": f"NASA POWER {lat:.1f}, {lon:.1f}", "lat": lat, "lon": lon,
                "elev": float(d["geometry"]["coordinates"][2]), "n_months": 300,
                "prcp": [round(par["PRECTOTCORR"][m] * M_DAYS[i], 1) for i, m in enumerate(mo)],
                "tmax": [a + b / 2 for a, b in zip(t, rg)], "tmin": [a - b / 2 for a, b in zip(t, rg)],
            })
    if not out:
        log("AVISO: NASA POWER indisponível; usando só o GHCN")
    log(len(out), "pseudo-estações NASA POWER")
    return out


def idw(stations, key, lat, lon, k=6, p=2.0, elev=None):
    cand = [s for s in stations if key in s]
    d = []
    for s in cand:
        kx, ky = km_per_deg((lat + s["lat"]) / 2)
        dist = math.hypot((lon - s["lon"]) * kx, (lat - s["lat"]) * ky)
        d.append((max(dist, 1.0), s))
    d.sort(key=lambda t: t[0])
    d = d[:k]
    wsum = sum(1 / di ** p for di, _ in d)
    res = np.zeros(12)
    for di, s in d:
        v = np.array(s[key], dtype=float)
        if elev is not None:  # correção de temperatura por gradiente adiabático
            v = v - 0.0065 * (elev - s["elev"])
        res += v / di ** p
    return res / wsum, d[0][0]


def hargreaves_month(tmax, tmin, lat):
    out = []
    for m in range(12):
        tm = (tmax[m] + tmin[m]) / 2
        et0 = 0.0023 * ra_mm_day(lat, m) * (tm + 17.8) * math.sqrt(max(tmax[m] - tmin[m], 0.1))
        out.append(et0 * M_DAYS[m])
    return np.array(out)


def budyko_et(p, pet, w=BUDYKO_W):
    phi = pet / max(p, 1)
    return p * (1 + phi - (1 + phi ** w) ** (1 / w))


# ----------------------------------------------------------------------------
# Domínios hidrogeológicos da RDC (SINTÉTICO: regras lat/lon aproximando o mapa
# de produtividade de aquíferos do BGS Africa Groundwater Atlas / MacDonald et al. 2012)
# ----------------------------------------------------------------------------
ZONES = {
    # nome: (rótulo, favorabilidade litológica, permeabilidade do solo, vazão por poço L/s, WTD base m)
    "costeira": ("Moanda coastal sedimentary basin", 0.75, 0.70, 3.0, 12.0),
    "kongo_central": ("Kongo Central (Mayombe and Schisto-calcaire/karst)", 0.55, 0.50, 1.5, 18.0),
    "rift": ("Albertine/Kivu rift (volcanic and fractured)", 0.45, 0.60, 1.2, 25.0),
    "cuvette": ("Cuvette Centrale (Quaternary sediments)", 0.85, 0.50, 4.0, 4.0),
    "kalahari": ("Kalahari/Batéké plateaus (thick sands)", 0.65, 0.90, 2.5, 30.0),
    "kasai": ("Kasai craton (crystalline basement)", 0.30, 0.45, 0.5, 14.0),
    "katanga": ("Katanga (metasediments and dolomites)", 0.55, 0.50, 1.5, 20.0),
    "embasamento": ("Crystalline basement (north and east)", 0.35, 0.50, 0.7, 12.0),
}


def zone_of(lon, lat, dist_ocean_km):
    if dist_ocean_km < 40:
        return "costeira"
    if lon < 15.2 and lat < -4.0:
        return "kongo_central"
    if lon >= 28.0 and lat > -9.0:
        return "rift"
    if ((lon - 21.5) / 5.5) ** 2 + ((lat + 0.5) / 3.5) ** 2 <= 1:
        return "cuvette"
    if lat < -3.0 and 15.2 <= lon < 22.5:
        return "kalahari"
    if lat < -4.0 and 22.5 <= lon < 25.5:
        return "kasai"
    if lat < -6.5 and lon >= 25.5:
        return "katanga"
    return "embasamento"


# ----------------------------------------------------------------------------
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    log("1/6 limites (geoBoundaries) e camadas vetoriais (Natural Earth)")
    adm1 = json.loads(fetch(GB_ADM1, "geoBoundaries-COD-ADM1_simplified.geojson"))["features"]
    depts = []
    for f in adm1:
        nm = f["properties"]["shapeName"]
        depts.append((PROV_NAMES.get(nm, nm), shape(f["geometry"]).buffer(0)))
    depts.sort()
    country = unary_union([g for _, g in depts])

    countries = ne("ne_10m_admin_0_countries")["features"]
    land = unary_union([shape(f["geometry"]).buffer(0) for f in countries
                        if shape(f["geometry"]).intersects(box(*BBOX).buffer(2))])
    coast = land.boundary.intersection(box(*BBOX).buffer(1))
    ocean_poly = box(*BBOX).buffer(1).difference(land)

    bb = box(*BBOX)
    rivers_major = []
    for f in ne("ne_10m_rivers_lake_centerlines")["features"]:
        nm = f["properties"].get("name")
        g = shape(f["geometry"])
        if nm in MAJOR_RIVERS and g.intersects(bb):
            rivers_major.append((nm, g.intersection(bb)))
    roads = [shape(f["geometry"]) for f in ne("ne_10m_roads")["features"]
             if shape(f["geometry"]).intersects(bb)]
    places = [f for f in ne("ne_10m_populated_places_simple")["features"]
              if shape(f["geometry"]).intersects(bb)]
    cities = [{"name": f["properties"]["name"],
               "pop": int(f["properties"]["pop_max"]),
               "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1],
               "country": f["properties"]["adm0_a3"]} for f in places]

    log("2/6 normais climáticas (GHCN-Daily + NASA POWER)")
    region = country.buffer(1.0)
    ghcn = load_stations(region)
    stations = ghcn + load_power(country.buffer(0.5))

    log("3/6 DEM (Terrarium/SRTM)")
    dem, lons, lats = load_dem()
    H, W = dem.shape
    log("  DEM", dem.shape)

    # campo de escoamento coarse para acumular vazão (Budyko) em grade 0.5°
    log("4/6 escoamento e rede de drenagem (priority-flood + D8)")
    runoff = np.zeros_like(dem)
    step = 40
    for r0 in range(0, H, step):
        for c0 in range(0, W, step):
            la, lo = lats[min(r0 + step // 2, H - 1)], lons[min(c0 + step // 2, W - 1)]
            el = float(np.median(dem[r0:r0 + step, c0:c0 + step]))
            pm, _ = idw(stations, "prcp", la, lo)
            tx, _ = idw(stations, "tmax", la, lo, elev=el)
            tn, _ = idw(stations, "tmin", la, lo, elev=el)
            pet = hargreaves_month(tx, tn, la).sum()
            p = pm.sum()
            runoff[r0:r0 + step, c0:c0 + step] = p - budyko_et(p, pet)
    acc, qdem, down, ocean = hydrology(dem, lons, lats, runoff)
    streams_small = stream_lines(acc, down, lons, lats, STREAM_MIN_KM2)
    streams_big = stream_lines(acc, down, lons, lats, RIVER_MIN_KM2)
    log("  drenagem ok")

    # pixels de rio (para distância/vazão/elevação da lâmina d'água)
    rpix = np.argwhere((acc >= RIVER_MIN_KM2) & ~ocean)
    rp_lon = lons[rpix[:, 1]]
    rp_lat = lats[rpix[:, 0]]
    rp_q = qdem[rpix[:, 0], rpix[:, 1]]
    rp_z = dem[rpix[:, 0], rpix[:, 1]]
    rp_acc = acc[rpix[:, 0], rpix[:, 1]]
    spix = np.argwhere((acc >= STREAM_MIN_KM2) & ~ocean)
    sp_lon, sp_lat = lons[spix[:, 1]], lats[spix[:, 0]]
    sp_z = dem[spix[:, 0], spix[:, 1]]

    # pontos densos ao longo dos grandes rios
    major_pts = []
    for nm, g in rivers_major:
        geoms = getattr(g, "geoms", [g])
        for ln in geoms:
            if ln.length == 0:
                continue
            n = max(2, int(ln.length / 0.02))
            for k in range(n + 1):
                p = ln.interpolate(k / n, normalized=True)
                major_pts.append((nm, p.x, p.y))
    mp_lon = np.array([p[1] for p in major_pts])
    mp_lat = np.array([p[2] for p in major_pts])
    mp_name = [p[0] for p in major_pts]

    def dem_at(lon, lat, win=1):
        c = int(np.clip(np.searchsorted(lons, lon), 0, W - 1))
        r = int(np.clip(np.argmin(np.abs(lats - lat)), 0, H - 1))
        return float(dem[max(0, r - win):r + win + 1, max(0, c - win):c + win + 1].min())

    log("5/6 grade de células e covariáveis")
    small_tree_geoms = list(getattr(streams_small, "geoms", [streams_small]))
    small_tree = STRtree(small_tree_geoms)
    road_tree = STRtree(roads)
    country_local_cities = [c for c in cities if c["pop"] >= 8000]

    def build_cells(cell_deg):
        cells = []
        gx = np.arange(BBOX[0], BBOX[2], cell_deg)
        gy = np.arange(BBOX[1], BBOX[3], cell_deg)
        cid = 0
        for y in gy:
            for x in gx:
                sq = box(x, y, x + cell_deg, y + cell_deg)
                if not sq.intersects(country):
                    continue
                part = sq.intersection(country)
                if part.area < 0.15 * sq.area:
                    continue
                c = part.representative_point() if not part.contains(part.centroid) else part.centroid
                lon, lat = c.x, c.y
                shares = sorted(((d[1].intersection(part).area / part.area, d[0]) for d in depts), reverse=True)
                dept = shares[0][1]
                dept_list = [n for a, n in shares if a >= 0.05 or n == dept]
                # DEM na célula
                cm = (lons >= x) & (lons < x + cell_deg)
                rm = (lats >= y) & (lats < y + cell_deg)
                sub = dem[np.ix_(rm, cm)]
                if sub.size == 0:
                    continue
                kx, ky = km_per_deg(lat)
                px_x = abs(lons[1] - lons[0]) * kx * 1000
                px_y = abs(lats[1] - lats[0]) * ky * 1000
                gy_, gx_ = np.gradient(sub, px_y, px_x)
                slope = float(np.mean(np.hypot(gx_, gy_)) * 100)
                lap = np.gradient(gx_, px_x, axis=1) + np.gradient(gy_, px_y, axis=0)
                curv = float(np.mean(lap) * 1e5)  # 1/100 km
                elev = float(np.mean(sub))
                # ponto de implantação: terço baixo do relevo da célula (onde ficam
                # as lavouras e a captação), usado para HAND e desnível ao rio
                e_low = float(np.percentile(sub, 25))
                # drenagem
                pt = Point(lon, lat)
                near = small_tree.nearest(pt)
                ns = small_tree_geoms[near]
                d_d = to_local_km(LineString([pt, ns.interpolate(ns.project(pt))]), lat).length
                clip = [small_tree_geoms[i].intersection(sq) for i in small_tree.query(sq)]
                dens = sum(to_local_km(g, lat).length for g in clip) / (to_local_km(sq, lat).area)
                # rio derivado do DEM mais próximo (melhor relação vazão/distância)
                dk = np.hypot((rp_lon - lon) * kx, (rp_lat - lat) * ky)
                within = np.flatnonzero(dk <= max(25.0, float(dk.min()) + 1))
                j = int(within[np.argmax(rp_q[within] / (1 + dk[within]))])
                stream = {"d_km": round(float(dk[j]), 2), "q": round(float(rp_q[j]), 2),
                          "z": round(float(rp_z[j]), 1), "acc_km2": round(float(rp_acc[j]))}
                # HAND: altura acima da drenagem mais próxima (limiar pequeno)
                ds = np.hypot((sp_lon - lon) * kx, (sp_lat - lat) * ky)
                near_s = np.argpartition(ds, 5)[:5] if ds.size > 5 else np.arange(ds.size)
                hand = max(0.0, e_low - float(np.min(sp_z[near_s])))
                # grande rio (Natural Earth + vazão de literatura)
                dm = np.hypot((mp_lon - lon) * kx, (mp_lat - lat) * ky)
                m = int(np.argmin(dm))
                nm = mp_name[m]
                major = {"name": nm, "d_km": round(float(dm[m]), 2), "q": MAJOR_RIVERS[nm][0],
                         "regime": MAJOR_RIVERS[nm][1], "z": round(dem_at(mp_lon[m], mp_lat[m]), 1)}
                # clima
                pm, _ = idw(stations, "prcp", lat, lon)
                # confiança: distância à estação medida (GHCN) mais próxima, não à grade POWER
                d_st = min((math.hypot((lon - s["lon"]) * kx, (lat - s["lat"]) * ky) for s in ghcn), default=999.0)
                tx, _ = idw(stations, "tmax", lat, lon, elev=elev)
                tn, _ = idw(stations, "tmin", lat, lon, elev=elev)
                pet_m = hargreaves_month(tx, tn, lat)
                p, pet = float(pm.sum()), float(pet_m.sum())
                et = budyko_et(p, pet)
                # acesso
                rd = road_tree.nearest(pt)
                d_road = to_local_km(LineString([pt, roads[rd].interpolate(roads[rd].project(pt))]), lat).length
                dtown = min(country_local_cities, key=lambda cc: (cc["lon"] - lon) ** 2 + (cc["lat"] - lat) ** 2)
                d_town = math.hypot((dtown["lon"] - lon) * kx, (dtown["lat"] - lat) * ky)
                pop_idx = sum(cc["pop"] / (1 + (math.hypot((cc["lon"] - lon) * kx, (cc["lat"] - lat) * ky) / 30) ** 2)
                              for cc in cities)
                d_ocean = to_local_km(LineString([pt, coast.interpolate(coast.project(pt))]), lat).length \
                    if not ocean_poly.contains(pt) else 0.0
                z = zone_of(lon, lat, d_ocean)
                # turfeiras da Cuvette Centrale (Lac Tumba / Mai-Ndombe / Ubangi), aprox.: baixadas da bacia
                peat = z == "cuvette" and hand < 8 and 16.5 <= lon <= 21.5 and -2.5 <= lat <= 2.5
                ndvi = float(np.clip((p - 800) / 1400, 0.35, 0.9))  # SINTÉTICO (proxy por chuva)
                cells.append({
                    "id": cid, "dept": dept, "depts": dept_list, "lon": round(lon, 4), "lat": round(lat, 4),
                    "geom": part.simplify(0.005),
                    "E": round(elev, 1), "E_low": round(e_low, 1), "S": round(slope, 2), "C": round(curv, 3), "HAND": round(hand, 1),
                    "D_d_km": round(d_d, 2), "dens": round(dens, 3),
                    "P": round(p), "P_m": [round(float(v), 1) for v in pm],
                    "PET": round(pet), "PET_m": [round(float(v), 1) for v in pet_m], "ET": round(et),
                    "zone": z, "lito": ZONES[z][1], "So": ZONES[z][2], "yield_Ls": ZONES[z][3],
                    "WTD0": ZONES[z][4], "NDVI": round(ndvi, 2), "peat": peat,
                    "stream": stream, "major": major,
                    "D_road_km": round(d_road, 2), "D_town_km": round(d_town, 1), "town": dtown["name"],
                    "pop_idx": round(pop_idx), "D_station_km": round(d_st, 1),
                })
                cid += 1
        return cells

    grids = {}
    for deg in RESOLUTIONS:
        cells = build_cells(deg)
        zc = defaultdict(int)
        for c in cells:
            zc[c["zone"]] += 1
        log(f"  {deg}°:", len(cells), "células;", len(depts), "províncias | zonas:", dict(zc),
            "| turfeiras:", sum(c["peat"] for c in cells))
        grids[deg] = cells

    log("6/6 gravando arquivos")
    resolutions = {}
    for i, (deg, cells) in enumerate(grids.items()):
        fname = "cells.geojson" if i == 0 else f"cells_{deg}.geojson"
        fc = {"type": "FeatureCollection", "features": []}
        for c in cells:
            g = c.pop("geom")
            fc["features"].append({"type": "Feature", "geometry": rnd(g), "properties": c})
        (OUT / fname).write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")))
        resolutions[str(deg)] = {"file": fname, "n_cells": len(cells), "km": round(deg * 111)}

    dfc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": n}, "geometry": rnd(g.simplify(0.01))} for n, g in depts]}
    (OUT / "departments.geojson").write_text(json.dumps(dfc, ensure_ascii=False, separators=(",", ":")))

    clipbox = country.buffer(0.6)
    rv = []
    for nm, g in rivers_major:
        gg = g.intersection(clipbox)
        if not gg.is_empty:
            rv.append({"type": "Feature", "properties": {"name": nm, "kind": "major", "q": MAJOR_RIVERS[nm][0]},
                       "geometry": rnd(gg.simplify(0.01))})
    sb = streams_big.intersection(clipbox).simplify(0.01)
    rv.append({"type": "Feature", "properties": {"name": "DEM-derived drainage", "kind": "dem"},
               "geometry": rnd(sb)})
    (OUT / "rivers.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": rv},
                                                   ensure_ascii=False, separators=(",", ":")))
    cfc = [c for c in cities if c["country"] == "COD" and country.buffer(0.05).contains(Point(c["lon"], c["lat"]))]
    (OUT / "cities.json").write_text(json.dumps(cfc, ensure_ascii=False))
    (OUT / "stations.json").write_text(json.dumps(
        [{k: s[k] for k in ("id", "name", "lat", "lon", "elev", "n_months")} | {"P": round(sum(s["prcp"]))}
         for s in ghcn], ensure_ascii=False))
    meta = {
        "cell_deg": RESOLUTIONS[0], "bbox": BBOX, "n_cells": resolutions[str(RESOLUTIONS[0])]["n_cells"],
        "resolutions": resolutions,
        "zones": {k: v[0] for k, v in ZONES.items()},
        "sources": {
            "real": [
                "geoBoundaries (gbOpen, OSM): boundaries of the 26 provinces",
                "Natural Earth 10m: major rivers, roads, cities",
                "AWS Terrain Tiles (Terrarium; SRTM/NASADEM): elevation, slope, curvature",
                "Drainage network and discharge derived from the DEM (priority-flood + D8, Budyko runoff)",
                f"NOAA GHCN-Daily: monthly rainfall and temperature normals from {len(ghcn)} stations",
                f"NASA POWER (MERRA-2, 2001-2025 climatology): {len(stations) - len(ghcn)} points on a {POWER_STEP}° grid",
                "PET by Hargreaves (FAO-56) from temperatures",
            ],
            "synthetic": [
                "Hydrogeological domains, lithological favourability and borehole yield (approx. Africa Groundwater Atlas / MacDonald 2012)",
                "Soil permeability by domain (instead of SoilGrids)",
                "NDVI estimated from rainfall (instead of Sentinel/MODIS)",
                "β coefficients of the WTD regression (no calibration wells)",
                "Mean discharge of major rivers: approximate literature values",
                "Population index by city gravity model (instead of WorldPop)",
                "Cuvette Centrale peatlands: approximate extent",
            ],
        },
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    log("pronto:", OUT)


if __name__ == "__main__":
    main()
