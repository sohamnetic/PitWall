"""Pack the data a hosted PitWall needs into one archive, for images built without a volume
(e.g. Render's free tier, whose disk resets on every restart).

    python scripts/pack_data.py            # -> deploy/pitwall-data.tar.gz

Includes a consistent copy of the database (write-ahead log folded in), the trained models,
the lap files and the backtest results. FastF1's download cache stays behind: the hosted app
only reads data, it doesn't fetch it.
"""

from __future__ import annotations

import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "deploy" / "pitwall-data.tar.gz"
FOLDERS = ("models", "laps", "backtest")


def main() -> None:
    db = DATA / "f1p.sqlite"
    missing = [p for p in (db, *(DATA / f for f in FOLDERS)) if not p.exists()]
    if missing:
        sys.exit(f"missing: {', '.join(str(p) for p in missing)} (run f1p ingest / train / backtest)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "f1p.sqlite"
        src, dst = sqlite3.connect(db), sqlite3.connect(snapshot)
        with dst:
            src.backup(dst)  # a consistent copy even while the app is running
        src.close()
        dst.close()

        with tarfile.open(OUT, "w:gz") as tar:
            tar.add(snapshot, arcname="f1p.sqlite")
            for folder in FOLDERS:
                tar.add(DATA / folder, arcname=folder)
    print(f"{OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
