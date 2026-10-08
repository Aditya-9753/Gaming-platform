"""Application entry point and FastAPI factory with lifecycle management."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from fastapi import FastAPI

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None  # type: ignore[assignment]

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis, init_redis
from app.middleware.cors import setup_cors
from app.middleware.error_handler import setup_error_handlers
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and graceful shutdown resources."""
    settings = get_settings()

    # 1. Initialize logging
    setup_logging()
    logger.info("Initializing Gaming Platform Application", env=settings.APP_ENV)

    # 2. Optional Sentry integration
    if sentry_sdk and settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            traces_sample_rate=1.0 if settings.is_development else 0.1,
            environment=settings.APP_ENV,
        )
        logger.info("Sentry monitoring configured")

    # 3. Initialize Database connection pool
    try:
        await init_db()
    except Exception as exc:
        logger.error("Database initialization encountered an error", error=str(exc))

    # 3b. Seed reference data + hard-coded staff accounts (non-production only)
    from app.core.bootstrap import bootstrap_dev_data
    await bootstrap_dev_data()

    # 4. Initialize Redis client & PubSub bridge
    bridge = None
    games_task: Optional[asyncio.Task] = None
    affiliate_task: Optional[asyncio.Task] = None
    try:
        redis_client = await init_redis()
        if redis_client is None:
            raise RuntimeError("Redis is unreachable; live games and WebSockets are disabled")
        from app.websocket.pubsub import RedisPubSubBridge
        bridge = RedisPubSubBridge(redis_client)
        bridge.start()

        # 5. Live game engines in-process (dev) so one command runs everything
        if settings.run_game_engines_in_api:
            from app.core.database import get_session_factory
            from app.games.runtime import run_game_runtime
            games_task = asyncio.create_task(
                run_game_runtime(get_session_factory(), redis_client)
            )
            logger.info("Game engines started in API process")
    except Exception as exc:
        logger.error("Redis initialization encountered an error", error=str(exc))

    # 6. Affiliate background jobs in-process (dev); production runs them on Celery beat
    if settings.run_game_engines_in_api:
        from app.affiliate.jobs import dev_loop
        from app.core.database import get_session_factory as _factory

        affiliate_task = asyncio.create_task(dev_loop(_factory()))
        logger.info("Affiliate jobs started in API process")

    yield

    # Shutdown sequence
    logger.info("Shutting down Gaming Platform Application")
    if affiliate_task:
        affiliate_task.cancel()
    if games_task:
        games_task.cancel()
        try:
            await games_task
        except (asyncio.CancelledError, Exception):
            pass
    if bridge:
        await bridge.stop()
    await close_redis()
    await close_db()
    logger.info("Resources gracefully closed")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Virtual-credit real-time gaming platform backend API",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Register error handlers
    setup_error_handlers(app)

    # Register ASGI middlewares
    # Order matters: RequestIdMiddleware is outermost to capture request ID for all subsequent handlers
    app.add_middleware(SecurityHeadersMiddleware)
    setup_cors(app)
    app.add_middleware(RequestIdMiddleware)

    # Mount API routers
    app.include_router(api_router, prefix="/api/v1")

    # Mount WebSocket router
    from app.websocket.routes import router as ws_router
    app.include_router(ws_router)

    # Top-level direct health check for orchestrators / load balancers
    app.include_router(health_router, prefix="")

    # Partner tracking links on the API domain: /r/{code} and /?ref={code}
    from fastapi import Depends, Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.api.v1.affiliate.public import redirect_router, track_redirect
    from app.core.database import get_db

    app.include_router(redirect_router)

    @app.get("/", tags=["Root"], response_model=None)
    async def root(request: Request, db: AsyncSession = Depends(get_db)):
        """Root API status endpoint (or a partner click when ?ref= is present)."""
        ref = request.query_params.get("ref")
        if ref:
            return await track_redirect(request, ref, db)
        return {
            "name": settings.APP_NAME,
            "version": "1.0.0",
            "environment": settings.APP_ENV,
            "status": "online",
        }

    return app


# Application singleton for ASGI servers like uvicorn
app = create_app()