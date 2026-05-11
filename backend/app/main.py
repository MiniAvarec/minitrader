"""FastAPI entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import exchanges as exchange_routes
from app.api import execution as execution_routes
from app.api import integrations as integration_routes
from app.api import internal as internal_routes
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
from app.ws import live as ws_live

app = FastAPI(title="trader", version="0.1.0")

s = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


app.include_router(auth_routes.router, prefix="/api")
app.include_router(key_routes.router, prefix="/api")
app.include_router(signal_routes.router, prefix="/api")
app.include_router(order_routes.router, prefix="/api")
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
