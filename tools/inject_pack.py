#!/usr/bin/env python3
"""Inject packs/scw-qatar-starter.v0.1.0.json into app/index.html."""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(BASE, "app", "index.html")
PACK = os.path.join(BASE, "packs", "scw-qatar-starter.v0.1.0.json")

with io.open(HTML, encoding="utf-8") as f:
    html = f.read()
with io.open(PACK, encoding="utf-8") as f:
    pack = f.read().strip()
assert "__PACK_JSON__" in html, "placeholder missing"
html = html.replace("__PACK_JSON__", pack)
with io.open(HTML, "w", encoding="utf-8") as f:
    f.write(html)
print("injected %d bytes" % len(pack))
