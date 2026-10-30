"""Independent FastAPI server; importing it never starts or touches workers."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..settings import Settings
from .quotas import Quotas
from .store import Store

STATIC = Path(__file__).parent / "static"


def create_app(root=None, quotas=None):
    """The board's app over the workflow root (default: the settings' root)."""
    app = FastAPI(title="Dev workflow", docs_url=None, redoc_url=None)
    store = Store(root or Settings.load().root)
    quota_reader = quotas if quotas is not None else Quotas()

    @app.get("/api/quotas")
    def quota_status(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return quota_reader.read()

    @app.get("/api/catalog")
    def catalog(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return store.catalog()

    @app.get("/api/board")
    def board(project: str, cycle: str, response: Response):
        response.headers["Cache-Control"] = "no-store"
        try:
            return store.board(project, cycle)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(503, str(error)) from error

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
