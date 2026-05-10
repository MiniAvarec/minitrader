# trader

Self-hosted day-trading signal & auto-execution tool for Binance USDT-M perpetual futures.

- React web UI + FastAPI backend
- Live klines from Binance WS, news from Finnhub + CryptoPanic, macro calendar
- RSI / MACD / EMA(20,50) on 1m / 3m / 15m / 1h
- Signal-only or auto-execute per user
- Telegram bot delivers signals with inline Execute / Dismiss buttons
- Risk controls: per-trade size cap, SL/TP required, daily loss kill-switch, max concurrent positions

## Quickstart

```
cp .env.example .env
# edit .env: set MASTER_KEY (run `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
# set FINNHUB_API_KEY, CRYPTOPANIC_API_KEY, TELEGRAM_BOT_TOKEN, JWT_SECRET
docker compose up --build
```

Open http://localhost:5173 and register. Add Binance keys in Settings (testnet recommended).

## Services

| Service | Port | Notes |
|---|---|---|
| frontend | 5173 | Vite dev server |
| backend | 8000 | FastAPI |
| postgres | 5432 | data |
| redis | 6379 | live klines + signal pubsub |
| ingestor | — | Binance WS kline ingestor |
| signals | — | signal engine |
| news | — | news pollers |
| telegram | — | bot worker |
| executor | — | order executor |

## Testnet

Use `BINANCE_USE_TESTNET=true` in `.env` to route all order/balance calls to `testnet.binancefuture.com`.

## Tests

```
docker compose run --rm backend pytest
```
