import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.datasets.router import router as datasets_router
from src.presentations.router import router as presentations_router
from src.query.router import router as query_router
from src.settings.router import router as settings_router

# Render's log stream is the only visibility into a deployed failure -- there's
# no APM/observability stack here, so a plain root logger configured once at
# import time is what "check the logs" actually means for this app.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="CSV Data Analysis Tool")

    # Logged at startup so a misconfigured/empty CORS_ORIGINS on Render (the
    # most common cause of a browser-side "Failed to fetch" on upload) shows
    # up immediately in the deploy logs instead of only being discoverable by
    # inspecting the failing request's Network tab.
    logger.info("CORS allow_origins=%s", settings.cors_origin_list)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        # A blocked CORS preflight still reaches the server and gets logged
        # here -- the browser only hides the *response* from the page, so
        # this is the one place that can confirm "the request landed but the
        # origin didn't match" versus "the request never arrived at all".
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s origin=%s -> %s (%.1fms)",
            request.method,
            request.url.path,
            request.headers.get("origin"),
            response.status_code,
            duration_ms,
        )
        return response

    app.include_router(datasets_router)
    app.include_router(presentations_router)
    app.include_router(query_router)
    app.include_router(settings_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
