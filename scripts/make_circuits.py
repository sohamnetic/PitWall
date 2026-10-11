"""Turn circuit outlines (GeoJSON) into small SVG paths for the frontend.

Source: https://github.com/bacinger/f1-circuits (MIT, (c) 2019-2025 Tomislav Bacinger).
Download f1-circuits.geojson from that repository, then:

    python scripts/make_circuits.py path/to/f1-circuits.geojson

Writes frontend/src/data/circuits.json: {circuit_id: {"d": svg path, "w": width, "h": height}},
keyed by the Jolpica circuit ids the rest of the app uses.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "frontend" / "src" / "data" / "circuits.json"
SIZE = 100  # longest side of each outline, in SVG units

# Jolpica circuit id -> dataset id
IDS = {
    "albert_park": "au-1953",
    "americas": "us-2012",
    "bahrain": "bh-2002",
    "baku": "az-2016",
    "catalunya": "es-1991",
    "hockenheimring": "de-1932",
    "hungaroring": "hu-1986",
    "imola": "it-1953",
    "interlagos": "br-1940",
    "istanbul": "tr-2005",
    "jeddah": "sa-2021",
    "losail": "qa-2004",
    "madring": "es-2026",
    "marina_bay": "sg-2008",
    "miami": "us-2022",
    "monaco": "mc-1929",
    "monza": "it-1922",
    "mugello": "it-1914",
    "nurburgring": "de-1927",
    "portimao": "pt-2008",
    "red_bull_ring": "at-1969",
    "ricard": "fr-1969",
    "rodriguez": "mx-1962",
    "sepang": "my-1999",
    "shanghai": "cn-2004",
    "silverstone": "gb-1948",
    "sochi": "ru-2014",
    "spa": "be-1925",
    "suzuka": "jp-1962",
    "vegas": "us-2023",
    "villeneuve": "ca-1978",
    "yas_marina": "ae-2009",
    "zandvoort": "nl-1948",
}


def outline(coords: list[list[float]]) -> dict:
    """Project lon/lat to a flat plane (fine at circuit scale) and fit it into SIZE units."""
    lat0 = sum(c[1] for c in coords) / len(coords)
    k = math.cos(math.radians(lat0))
    pts = [(lon * k, -lat) for lon, lat, *_ in coords]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    scale = SIZE / span
    pts = [((x - min(xs)) * scale, (y - min(ys)) * scale) for x, y in pts]
    d = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z"
    return {
        "d": d,
        "w": round((max(xs) - min(xs)) * scale, 1),
        "h": round((max(ys) - min(ys)) * scale, 1),
    }


def main(src: str) -> None:
    features = json.loads(Path(src).read_text(encoding="utf-8"))["features"]
    by_id = {f["properties"]["id"]: f["geometry"]["coordinates"] for f in features}
    missing = sorted(c for c, i in IDS.items() if i not in by_id)
    if missing:
        sys.exit(f"not in the dataset: {', '.join(missing)}")
    out = {cid: outline(by_id[i]) for cid, i in sorted(IDS.items())}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(out)} circuits -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1])
