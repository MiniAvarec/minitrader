"""FastAPI entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api import admin as admin_routes
from app.api import exchanges as exchange_routes
from app.api import execution as execution_routes
from app.api import integrations as integration_routes
from app.api import internal as internal_routes
from app.api import journal as journal_routes
from app.api import klines as klines_routes
from app.api import news as news_routes
from app.api import orders as order_routes
from app.api import portfolio as portfolio_routes
from app.api import positions as position_routes
from app.api import risk_tools as risk_tool_routes
from app.api import sentiment as sentiment_routes
from app.api import settings as settings_routes
from app.api import signals as signal_routes
from app.api import strategies as strategy_routes
from app.api import watchlist as watchlist_routes
from app.auth import routes as auth_routes
from app.config import get_settings
from app.keys import routes as key_routes
from app.security import (
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
    limiter,
)
from app.ws import live as ws_live

app = FastAPI(title="trader", version="0.1.0")

s = get_settings()

# Rate-limit infra — endpoints opt in via @limiter.limit("...").
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Order matters: outermost runs first. ProxyHeaders must run before anything
# that inspects request.url.scheme / request.client.host, so the rest of the
# stack sees the real client IP and HTTPS scheme forwarded by the edge.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


app.include_router(auth_routes.router, prefix="/api")
app.include_router(admin_routes.router, prefix="/api")
app.include_router(key_routes.router, prefix="/api")
app.include_router(signal_routes.router, prefix="/api")
app.include_router(order_routes.router, prefix="/api")
app.include_router(journal_routes.router, prefix="/api")
app.include_router(position_routes.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")
app.include_router(news_routes.router, prefix="/api")
app.include_router(sentiment_routes.router, prefix="/api")
app.include_router(klines_routes.router, prefix="/api")
app.include_router(strategy_routes.router, prefix="/api")
app.include_router(internal_routes.router, prefix="/api")
app.include_router(exchange_routes.router, prefix="/api")
app.include_router(integration_routes.router, prefix="/api")
app.include_router(watchlist_routes.router, prefix="/api")
app.include_router(portfolio_routes.router, prefix="/api")
app.include_router(execution_routes.router, prefix="/api")
app.include_router(risk_tool_routes.router, prefix="/api")
app.include_router(ws_live.router)
