"""Gera dist/wherewise.html: demo estática de arquivo único (sem API).

Embute os dados de data/ e o frontend; os cálculos rodam em frontend/model.js
(idêntico ao backend, ver backend/tests/test_parity.py).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE, DATA, DIST = ROOT / "frontend", ROOT / "data", ROOT / "dist"


def main():
    html = (FE / "index.html").read_text()
    html = re.sub(r"<!doctype html>\s*<html[^>]*>\s*", "", html, flags=re.I)
    html = re.sub(r'<meta charset="utf-8">\s*<meta name="viewport"[^>]*>\s*', "", html)
    data = {
        "meta": json.loads((DATA / "meta.json").read_text()),
        "cells": json.loads((DATA / "cells.geojson").read_text()),
        "departments": json.loads((DATA / "departments.geojson").read_text()),
        "rivers": json.loads((DATA / "rivers.geojson").read_text()),
        "cities": json.loads((DATA / "cities.json").read_text()),
    }
    leaflet_css = (FE / "vendor" / "leaflet.css").read_text()
    html = html.replace('<link rel="stylesheet" href="vendor/leaflet.css">', f"<style>{leaflet_css}</style>")
    html = html.replace('<link rel="stylesheet" href="style.css">', f"<style>{(FE / 'style.css').read_text()}</style>")
    html = html.replace('<script src="vendor/leaflet.js"></script>',
                        '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>')
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace('<script src="model.js"></script>',
                        f"<script>window.HIDRO_DATA={payload};</script>\n<script>{(FE / 'model.js').read_text()}</script>")
    html = html.replace('<script src="app.js"></script>', f"<script>{(FE / 'app.js').read_text()}</script>")
    # o chat depende do backend (/api/chat), então fica fora da demo estática
    html = html.replace('<link rel="stylesheet" href="ChatWidget.css">\n', "")
    html = html.replace('<script src="ChatWidget.js"></script>\n', "")
    DIST.mkdir(exist_ok=True)
    out = DIST / "wherewise.html"
    out.write_text(html)
    print(out, round(out.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
