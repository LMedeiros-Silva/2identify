"""FastAPI application for the public, read-only alert panel."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.public_panel.config import PublicPanelSettings
from app.public_panel.feed import FeedCapacityError, FeedEvent, PublicAlertFeed
from app.public_panel.repository import PublicAlert, PublicAlertRepository

logger = logging.getLogger(__name__)

# Files of 2identify_web that the panel may serve; nothing else in that folder is public.
_WEB_FILES = {
    "index.html": "text/html; charset=utf-8",
    "qr.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "panel.js": "text/javascript; charset=utf-8",
    "qr.js": "text/javascript; charset=utf-8",
    "icon.svg": "image/svg+xml",
}
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
_HEARTBEAT_SECONDS = 15.0


def _read_only_loader(settings: PublicPanelSettings) -> Callable[[], list[PublicAlert]]:
    url = settings.database_url.get_secret_value()
    connect_args: dict[str, object] = {}
    if url.startswith("postgresql"):
        # Every transaction of this process is read-only at the PostgreSQL level.
        connect_args = {
            "connect_timeout": settings.database_connect_timeout_seconds,
            "application_name": "2Identify painel público",
            "options": (
                f"-csearch_path={settings.database_schema} -cdefault_transaction_read_only=on"
            ),
        }
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True, connect_args=connect_args)
    sessions = sessionmaker(bind=engine, class_=Session, autoflush=False)

    def load() -> list[PublicAlert]:
        with sessions() as session:
            return PublicAlertRepository(session).recent(settings.public_panel_window)

    return load


def _sse(event: FeedEvent) -> bytes:
    data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.kind}\ndata: {data}\n\n".encode()


def create_public_app(
    settings: PublicPanelSettings | None = None,
    loader: Callable[[], list[PublicAlert]] | None = None,
) -> FastAPI:
    resolved = settings or PublicPanelSettings()  # type: ignore[call-arg]
    feed = PublicAlertFeed(
        loader or _read_only_loader(resolved),
        interval_seconds=resolved.public_panel_poll_seconds,
        max_listeners=resolved.public_panel_max_clients,
    )
    web_dir = Path(resolved.public_panel_web_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await feed.start()
        try:
            yield
        finally:
            await feed.stop()

    app = FastAPI(
        title="2Identify painel público",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.feed = feed

    @app.middleware("http")
    async def read_only_and_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in {"GET", "HEAD"}:
            return JSONResponse(
                {"detail": "Painel público somente leitura."},
                status_code=405,
                headers={"Allow": "GET, HEAD", **_SECURITY_HEADERS},
            )
        response = await call_next(request)
        response.headers.update(_SECURITY_HEADERS)
        return response

    @app.get("/api/public/alerts")
    async def alerts() -> JSONResponse:
        return JSONResponse(feed.snapshot(), headers={"Cache-Control": "no-store"})

    @app.get("/api/public/config")
    async def config() -> JSONResponse:
        return JSONResponse(
            {"public_url": resolved.public_panel_url or None},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/public/stream")
    async def stream(request: Request) -> StreamingResponse:
        try:
            listener = feed.subscribe()
        except FeedCapacityError as error:
            raise HTTPException(status_code=503, detail="Painel lotado, tente de novo.") from error

        async def events() -> AsyncIterator[bytes]:
            try:
                yield b"retry: 3000\n\n"
                yield _sse(FeedEvent("snapshot", feed.snapshot()))
                while not await request.is_disconnected():
                    try:
                        event = await asyncio.wait_for(
                            listener.queue.get(), timeout=_HEARTBEAT_SECONDS
                        )
                    except TimeoutError:
                        # A named event (not a comment) so the page can detect a dead link.
                        yield b"event: ping\ndata: {}\n\n"
                        continue
                    if event is None:
                        return
                    yield _sse(event)
            finally:
                feed.unsubscribe(listener)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/public/qr.svg")
    async def qr(url: str = Query(min_length=8, max_length=300)) -> Response:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise HTTPException(status_code=422, detail="Informe uma URL http(s).")
        import segno

        buffer = io.BytesIO()
        # A standalone SVG (with xmlns) so it also renders inside <img>.
        segno.make(url, error="m").save(
            buffer, kind="svg", scale=10, border=2, dark="#0A1A33", xmldecl=False
        )
        return Response(
            buffer.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"}
        )

    @app.api_route("/", methods=["GET", "HEAD"])
    async def index() -> FileResponse:
        return _web_file(web_dir, "index.html")

    @app.api_route("/qr", methods=["GET", "HEAD"])
    async def qr_page() -> FileResponse:
        return _web_file(web_dir, "qr.html")

    @app.api_route("/{name}", methods=["GET", "HEAD"])
    async def web_file(name: str) -> FileResponse:
        return _web_file(web_dir, name)

    return app


def _web_file(web_dir: Path, name: str) -> FileResponse:
    media_type = _WEB_FILES.get(name)
    path = web_dir / name
    if media_type is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Não encontrado.")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-cache"})
