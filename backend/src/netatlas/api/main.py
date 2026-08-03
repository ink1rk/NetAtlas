"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from netatlas import __version__
from netatlas.api.middleware import LoginRateLimitMiddleware, RequestIdMiddleware
from netatlas.api.routes import auth, devices, topology
from netatlas.api.routes.ops import (
    credentials_router,
    discovery_router,
    discovery_ws,
    docker_router,
    export_router,
    ipam_router,
    snapshots_router,
    system_router,
    vmware_router,
)
from netatlas.bootstrap import startup
from netatlas.config import get_settings

logger = logging.getLogger("netatlas")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
    await startup()
    logger.info("NetAtlas API started version=%s", __version__)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NetAtlas API",
        version=__version__,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(LoginRateLimitMiddleware, limit_per_minute=settings.rate_limit_login_per_minute)

    prefix = settings.api_prefix
    app.include_router(system_router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(devices.router, prefix=prefix)
    app.include_router(topology.router, prefix=prefix)
    app.include_router(discovery_router, prefix=prefix)
    app.include_router(snapshots_router, prefix=prefix)
    app.include_router(ipam_router, prefix=prefix)
    app.include_router(export_router, prefix=prefix)
    app.include_router(credentials_router, prefix=prefix)
    app.include_router(vmware_router, prefix=prefix)
    app.include_router(docker_router, prefix=prefix)
    app.add_api_websocket_route(f"{prefix}/ws/discovery/{{job_id}}", discovery_ws)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("netatlas.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
