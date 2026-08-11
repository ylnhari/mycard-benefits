"""FastAPI application factory."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, data_location
from .catalog.loader import load_catalog
from .catalog.router import OwnedDiscoveryState, create_catalog_router
from .config import API_VERSION, APP_ID, PACKAGE_ROOT, Settings
from .destination_workflow import create_destination_workflow_router
from .identity import InstallationIdentity
from .optimizer.router import create_optimizer_router, install_optimizer_openapi_schema
from .reminders import ReminderPreferenceStore, create_reminders_router
from .vault.reconciliation_router import create_reconciliation_router
from .vault.router import (
    CardReader,
    _authorize_keyring_vault,
    _read_keyring_cards,
    _read_keyring_reminder_inputs,
    create_private_cards_router,
)

_PRIVATE_OR_REVIEW_API_PREFIXES = (
    "/api/v1/private",
    "/api/v1/catalog/destination-workflows",
)


def _requires_no_store(path: str) -> bool:
    """Return whether a protected or review API response must never be cached."""
    return path.startswith(_PRIVATE_OR_REVIEW_API_PREFIXES)


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
    def catalog_owned_reader(catalog: Any) -> OwnedDiscoveryState:
        """Project local card envelopes into public rule ownership only."""
        reader = private_card_reader or (
            lambda: _read_keyring_cards(data_location.vault_path_for_data_dir(settings.data_dir))
        )
        cards = reader()
        by_key = {offering.slug: offering for offering in catalog.offerings}
        by_key.update({offering.id: offering for offering in catalog.offerings})
        matched = [
            (offering.id, str(card.get("lifecycle", "unknown")))
            for card in cards
            if (offering := by_key.get(card.get("offering_id"))) is not None
        ]
        offering_ids = sorted({offering_id for offering_id, _ in matched})
        rule_ids = frozenset(
            rule.id for rule in catalog.benefits if rule.offering_id in offering_ids
        )
        revision = hashlib.sha256(json.dumps(
            sorted(matched),
            separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")).hexdigest()
        return OwnedDiscoveryState(
            rule_ids=rule_ids,
            inventory_empty=not cards,
            ownership_revision=revision,
        )

    @application.middleware("http")
    async def add_no_store_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        if _requires_no_store(request.url.path):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    @application.exception_handler(RequestValidationError)
    async def redact_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return useful validation locations without reflecting submitted values.

        FastAPI's default validation representation includes Pydantic's
        ``input`` field. Request values may include private card-related text,
        so API errors deliberately retain only a stable error type, location,
        and message. This applies to every API route, including public routes
        that may be called from the local browser UI.
        """
        errors: list[dict[str, object]] = []
        for error in exc.errors():
            raw_location = error.get("loc", ())
            location = (
                [str(part) for part in raw_location]
                if isinstance(raw_location, tuple | list)
                else []
            )
            message = error.get("msg")
            errors.append(
                {
                    "type": str(error.get("type", "validation_error")),
                    "loc": location,
                    "msg": message if isinstance(message, str) else "Invalid request",
                }
            )
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
        return JSONResponse(status_code=422, content={"detail": errors}, headers=headers)

    application.include_router(
        create_catalog_router(settings.catalog_dir, owned_rule_reader=catalog_owned_reader)
    )
    application.include_router(create_destination_workflow_router())
    application.include_router(
        create_private_cards_router(
            settings.data_dir,
            reader=private_card_reader,
            demo=settings.demo,
            port=settings.port,
            catalog_dir=settings.catalog_dir,
        )
    )
    application.include_router(create_reconciliation_router(settings.data_dir))
    reminder_reader = private_card_reader or (
        (lambda: ()) if settings.demo else
        (lambda: _read_keyring_reminder_inputs(data_location.vault_path_for_data_dir(settings.data_dir)))
    )
    reminder_store = ReminderPreferenceStore(settings.data_dir)
    reminder_authorizer = None if settings.demo or private_card_reader is not None else (
        lambda: _authorize_keyring_vault(data_location.vault_path_for_data_dir(settings.data_dir))
    )
    application.include_router(
        create_reminders_router(
            reminder_reader,
            ntfy_enabled=settings.ntfy_enabled and not settings.demo,
            preference_store=reminder_store,
            authorize_mutation=reminder_authorizer,
            catalog_reader=lambda: load_catalog(settings.catalog_dir),
        )
    )
    application.include_router(create_optimizer_router())

    application.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_ROOT / "static")),
        name="static",
    )

    @application.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        page = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"app_version": __version__, "demo": settings.demo},
        )
        page.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
        return page

    @application.get("/api/v1/health")
    async def health(
        request: Request, nonce: str | None = Query(default=None)
    ) -> dict[str, object]:
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

    default_openapi = application.openapi

    def openapi_with_optimizer_schema() -> dict[str, Any]:
        application.openapi_schema = None
        schema = default_openapi()
        install_optimizer_openapi_schema(schema)
        return schema

    application.openapi = openapi_with_optimizer_schema  # type: ignore[method-assign]

    return application


app = create_app()
