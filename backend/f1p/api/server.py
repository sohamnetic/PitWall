"""Production server: the API under /api and the built frontend for everything else.

    uvicorn f1p.api.server:app --host 0.0.0.0 --port 8000

The frontend is a single-page app, so unknown paths (e.g. /races/2026-17) return index.html
and the client-side router takes over. Interactive API docs live at /api/docs.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, Response

from f1p import __version__, config
from f1p.api.main import app as api

STATIC_DIR = Path(os.environ.get("F1P_STATIC_DIR", config.ROOT_DIR / "frontend" / "dist"))

NO_CACHE = {"Cache-Control": "no-cache"}  # app shell and service worker: always revalidate
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}  # hashed asset files


def create_app(static_dir: Path = STATIC_DIR) -> FastAPI:
    root = FastAPI(title="PitWall", version=__version__, docs_url=None, redoc_url=None)
    root.mount("/api", api)
    static_dir = static_dir.resolve()
    index = static_dir / "index.html"

    @root.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> Response:
        if not index.exists():
            return Response(
                "Frontend not built. Run `npm --prefix frontend run build`.", status_code=503
            )
        target = (static_dir / path).resolve()
        # Only serve files inside the build folder (no ../ escapes).
        if path and target.is_file() and target.is_relative_to(static_dir):
            headers = IMMUTABLE if path.startswith("assets/") else NO_CACHE
            return FileResponse(target, headers=headers)
        return FileResponse(index, headers=NO_CACHE)

    return root


app = create_app()
