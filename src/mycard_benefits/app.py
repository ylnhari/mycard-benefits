"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .catalog.router import create_catalog_router
from .config import API_VERSION, APP_ID, PACKAGE_ROOT, Settings
from .identity import InstallationIdentity
from .qa import create_qa_router
from .vault.router import CardReader, create_private_cards_router


def create_app(
    settings: Settings | None = None,
    *,
    private_card_reader: CardReader | None = None,
) -> FastAPI:
    settings = settings or Settings.from_environment()
    templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.identity = InstallationIdentity.load_or_create(settings.data_dir)
        yield

    application = FastAPI(
        title="MyCard Benefits",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )
    application.include_router(create_catalog_router(settings.catalog_dir))
    application.include_router(create_qa_router(settings.catalog_dir))
    application.include_router(
        create_private_cards_router(
            settings.data_dir,
            reader=private_card_reader,
        )
    )
    application.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_ROOT / "static")),
        name="static",
    )

    @application.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"app_version": __version__, "demo": settings.demo},
        )

    @application.get("/api/v1/health")
    async def health(request: Request, nonce: str | None = Query(default=None)) -> dict[str, object]:
        identity: InstallationIdentity = request.app.state.identity
        if nonce is not None:
            try:
                signed = identity.signed_health(nonce)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from None
            return {"status": "ok", "version": __version__, **signed}
        return {
            "status": "ok",
            "app_id": APP_ID,
            "api_version": API_VERSION,
            "version": __version__,
            "install_id": identity.install_id,
            "public_key": identity.public_key,
        }

    return application


app = create_app()
