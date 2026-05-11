# minitrader

Самостоятельно развёртываемая платформа для торговли криптовалютами на бессрочных USDT-фьючерсах. Подписывается на котировки нескольких бирж, прогоняет их через настраиваемый движок стратегий с учётом новостного фона, доставляет сигналы в веб-интерфейс и Telegram, а при включённом авто-режиме сама размещает ордера с жёстким контролем риска.

> Это инструмент для опытных пользователей. Запускайте в режиме сигналов или на тестнете до тех пор, пока не убедитесь в адекватности своих стратегий и риск-настроек.

---

## Содержание

1. [Возможности](#возможности)
2. [Архитектура](#архитектура)
3. [Быстрый старт](#быстрый-старт)
4. [Конфигурация](#конфигурация)
5. [Веб-интерфейс](#веб-интерфейс)
6. [Подключение бирж](#подключение-бирж)
7. [Новости и рыночный сентимент](#новости-и-рыночный-сентимент)
8. [Движок стратегий (DSL)](#движок-стратегий-dsl)
9. [Сигналы, исполнение и риск-контроль](#сигналы-исполнение-и-риск-контроль)
10. [Бэктест](#бэктест)
11. [Telegram-бот](#telegram-бот)
12. [Миграции БД и обновление](#миграции-бд-и-обновление)
13. [Разработка и тесты](#разработка-и-тесты)
14. [Технологический стек](#технологический-стек)

---

## Возможности

**Мультибиржевая работа.** Параллельные стримы Binance USDT-M Futures, OKX Perpetual Swaps и Bybit Linear Perpetuals. У каждого пользователя — собственный список наблюдаемых пар (watchlist) и собственная стратегия на каждой паре.

**Движок стратегий на YAML-DSL.** Декларативно описываете правила входа через дерево булевых выражений над индикаторами: RSI, MACD, EMA/SMA, ATR, Bollinger Bands, Donchian, VWAP, Supertrend, Heikin Ashi, StochRSI и др. Поддержка SL/TP по ATR или фиксированному проценту, кулдаун между сигналами, параметризация. 10+ встроенных стратегий «из коробки» + редактор и форк-копирование пользовательских.

**Новости и сентимент как часть сигнала.** Параллельная подкачка из Finnhub, CryptoPanic, CryptoCompare, GDELT 2.0, NewsData.io + ежедневный индекс Fear & Greed + скрейпинг хайпа из основных крипто-сабреддитов. Все источники нормализованы в общую таблицу `news_items` и доступны стратегии через DSL-функции `news_sentiment[minutes]`, `news_blackout[]`, `fear_greed[]`, `reddit_hype[]`. Дополнительно — макроэкономический календарь с автоматическим «блэкаутом» сигналов вокруг событий высокой важности.

**Два режима торговли.**
- `signal_only` — сигналы только показываются в UI / приходят в Telegram, исполнение по кнопке вручную;
- `auto_execute` — каждый сигнал, прошедший риск-контур, размещается на бирже автоматически.

**Риск-контур.** Лимит на размер позиции (USDT), дневной лимит убытка (kill-switch), максимум одновременных позиций, обязательность SL/TP. Срабатывания записываются в `risk_events` с указанием причины.

**Бэктест на тех же стратегиях.** Прокатываете YAML-стратегию по историческим клайнам выбранной пары, получаете win-rate, PnL, кривую эквити, журнал сделок.

**Веб-интерфейс в стиле Bloomberg.** React + shadcn/ui, светлая и тёмная темы, командное меню, real-time обновления через WebSocket.

**Telegram-бот.** Каждый сигнал приходит личным сообщением с inline-кнопками `Execute` / `Dismiss`.

**Все ключи API настраиваются из веб-интерфейса.** Биржевые ключи и ключи новостных сервисов хранятся в БД зашифрованными (Fernet, `MASTER_KEY`); правка не требует перезапуска воркеров. `.env` остаётся как fallback для свежих развёртываний.

---

## Архитектура

```
                 ┌──────────────┐
                 │   frontend   │  Vite + React (5173)
                 └──────┬───────┘
                        │ HTTP / WS
                 ┌──────▼───────┐    ┌──────────────┐
                 │   backend    │◄──►│   postgres   │
                 │   FastAPI    │    └──────────────┘
                 └──────┬───────┘
                        │ Redis pub/sub + cache
              ┌─────────┴─────────┐
              │      redis        │
              └─────────┬─────────┘
   ┌──────┬──────┬──────┼──────┬──────┬──────┬──────┐
   ▼      ▼      ▼      ▼      ▼      ▼      ▼      ▼
ingestor news signals executor tracker fillstream instruments telegram
   │      │      │       │       │        │           │         │
   ▼      ▼      ▼       ▼       ▼        ▼           ▼         ▼
 биржи  API    стратегии биржи  периодич. wallet/    биржи     Telegram
 WS    новостей  DSL    REST   close PnL fills      REST      Bot API
```

**Сервисы (`docker-compose.yml`):**

| Сервис | Порт | Назначение |
|---|---|---|
| `frontend` | 5173 | Vite dev-сервер React-приложения |
| `backend` | 8000 | FastAPI: REST API + WebSocket |
| `postgres` | 5432 | пользователи, сигналы, ордера, новости, стратегии |
| `redis` | 6379 | кэш клайнов, pub/sub каналы (`signals`, `news`, `watchlist:changed`, …) |
| `ingestor` | — | менеджер WS-стримов: подписывает все наблюдаемые пары на всех биржах |
| `signals` | — | подписан на канал `signals` (закрытие свечей), прогоняет стратегии, публикует новые сигналы |
| `news` | — | поллит Finnhub / CryptoPanic / CryptoCompare / GDELT / NewsData.io + Fear & Greed + Reddit-хайп + макрокалендарь |
| `instruments` | — | разово/периодически тянет exchangeInfo с бирж в таблицу `instruments` (tick/lot/min-notional) |
| `executor` | — | размещает ордера в `auto_execute` режиме, проверяет риск-контур |
| `tracker` | — | периодически считает realized PnL по закрытым позициям |
| `fillstream` | — | слушает потоки фактических исполнений ордеров с бирж |
| `telegram` | — | бот: рассылка сигналов и обработка inline-кнопок |

---

## Быстрый старт

Требования: Docker + Docker Compose, ~2 GB RAM, открытые порты 5173 / 8000 / 5432 / 6379.

```bash
git clone git@github.com:MiniAvarec/minitrader.git
cd minitrader

cp .env.example .env

# Сгенерировать MASTER_KEY (Fernet) — без него секреты не шифруются:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Прописать в .env обязательные поля:
#   MASTER_KEY=<значение выше>
#   JWT_SECRET=<любая длинная случайная строка>
#   POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
#   DATABASE_URL=postgresql+asyncpg://<user>:<pass>@postgres:5432/<db>

docker compose up --build -d
docker compose logs -f backend       # дождитесь "alembic upgrade head" → "Application startup complete"
```

Откройте `http://localhost:5173`, зарегистрируйте первого пользователя, затем настройте подключения в `Settings` (см. ниже).

Остановить: `docker compose down`. Очистить БД: `docker compose down -v`.

---

## Конфигурация

### Обязательное (только через `.env`)

| Переменная | Описание |
|---|---|
| `MASTER_KEY` | Fernet-ключ, шифрует все секреты в БД. **При смене этого ключа все сохранённые API-ключи становятся нечитаемы.** |
| `JWT_SECRET` | секрет для подписи токенов сессии |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@postgres:5432/db` |
| `REDIS_URL` | по умолчанию `redis://redis:6379/0` |
| `POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB` | для контейнера БД |

### Опциональное (через `.env`, можно переопределить из UI)

| Переменная | Назначение |
|---|---|
| `ENABLED_EXCHANGES` | список разрешённых бирж: `binance,okx,bybit` |
| `BINANCE_USE_TESTNET` / `OKX_USE_TESTNET` / `BYBIT_USE_TESTNET` | использовать тестнет (рекомендуется до боевого режима) |
| `DEFAULT_TIMEFRAMES` | таймфреймы, которые ингестор подписывает по умолчанию: `1m,3m,15m,1h` |
| `FINNHUB_API_KEY`, `CRYPTOPANIC_API_KEY`, `CRYPTOCOMPARE_API_KEY`, `NEWSDATA_API_KEY` | ключи новостных API (предпочтительнее настраивать через UI → Settings → Integrations) |
| `REDDIT_USER_AGENT` | UA для публичных JSON-эндпоинтов Reddit (обязателен для скрейпинга хайпа) |
| `TELEGRAM_BOT_TOKEN` | токен Telegram-бота для рассылки сигналов |
| `FRONTEND_ORIGIN` | базовый URL фронтенда для CORS, по умолчанию `http://localhost:5173` |

### Где приоритет

Для новостных API-ключей значение из БД (вкладка **Settings → Integrations**) перебивает `.env`. Это позволяет ротировать ключи без перезапуска сервисов — следующий цикл воркера `news` (≤ 2 минут) подхватит новое значение.

---

## Веб-интерфейс

После логина доступны разделы:

- **Dashboard** — watchlist, основной график выбранной пары, лента сигналов и новостей в правой панели, бейдж индекса Fear & Greed.
- **Positions** — открытые/закрытые позиции по всем биржам, реализованный PnL.
- **Signals** — полный журнал сигналов с фильтрацией.
- **Strategies** — список встроенных и пользовательских стратегий, форк и редактирование.
- **Strategy Edit** — YAML-редактор с подсветкой и встроенным бэктестом.
- **Settings** — все настройки в одном месте (см. ниже).

### Вкладки Settings

| Вкладка | Что внутри |
|---|---|
| **Strategies** | привязка стратегии к каждой `(exchange, symbol)` в watchlist (если не задано — используется встроенная `multi_tf_confluence`) |
| **Pairs** | список наблюдаемых пар, добавление/удаление через `AddPairDialog` (поиск по `instruments`) |
| **Trading mode** | переключатель `signal_only` ↔ `auto_execute` |
| **Exchanges** | ключи Binance / OKX / Bybit, кнопка `Test & save` — пробный запрос баланса перед сохранением |
| **Integrations** | ключи Finnhub, CryptoPanic, CryptoCompare, NewsData.io + Reddit User-Agent. Под каждым полем бейдж `Stored in DB` / `Loaded from .env` / `Not set`. |
| **Risk** | per-trade max notional, дневной лимит убытка, max concurrent positions, require SL/TP |
| **Telegram** | привязка чата (генерация одноразового токена) |

---

## Подключение бирж

Поддерживаются три биржи; все ключи строго на бессрочные USDT-перпы (USDT-M Futures / Perpetual Swaps / Linear Perps).

| Биржа | Тип контрактов | Требует passphrase | Тестнет |
|---|---|---|---|
| **Binance** | USDT-M Futures | нет | `testnet.binancefuture.com` |
| **OKX** | Perpetual Swaps | **да** | demo-режим |
| **Bybit** | Linear Perps | нет | `testnet.bybit.com` |

Создайте API-ключ на бирже **только с правом торговли фьючерсами** (без withdrawal!) и впишите его в **Settings → Exchanges**. Кнопка `Test & save` выполнит реальный запрос баланса USDT — если ответ получен, ключ сохранится зашифрованным; при ошибке отобразится сообщение биржи.

Ключи на разных биржах независимы; одна и та же пара (например, `BTCUSDT`) на разных биржах считается двумя разными инструментами и может иметь разные стратегии.

---

## Новости и рыночный сентимент

### Источники

| Источник | Тип данных | Стоимость | Где получить ключ |
|---|---|---|---|
| **Finnhub** | заголовки крипто-новостей | бесплатный тариф | [finnhub.io](https://finnhub.io) |
| **CryptoPanic** | агрегатор с голосами сообщества (positive/negative/important/toxic) | бесплатный тариф | [cryptopanic.com](https://cryptopanic.com/developers/api/) |
| **CryptoCompare (CCData)** | 150+ источников | бесплатно с ключом | [cryptocompare.com](https://www.cryptocompare.com/cryptopian/api-keys) |
| **GDELT 2.0** | мировые новости с тональностью (`tone`) | бесплатно, без ключа | — |
| **NewsData.io** | мейнстрим-новости, упоминающие крипту | бесплатный тариф 200 запросов/день | [newsdata.io](https://newsdata.io/register) |
| **Alternative.me Fear & Greed** | ежедневный индекс 0–100 | бесплатно, без ключа | — |
| **Reddit (public JSON)** | хайп в крипто-сабреддитах | бесплатно, без ключа (нужен `User-Agent`) | — |
| **Экономический календарь** | события высокой важности → автоматический blackout | бесплатно | — |

Все заголовочные источники складываются в общую таблицу `news_items` с дедупликацией по `(source, external_id)`. Каждой записи присваивается оценка сентимента в шкале `-1..+1` (для CryptoPanic — на основе голосов, для GDELT — нормализованный `tone`, для остальных — словарный анализ заголовка/описания).

Fear & Greed пишется отдельно в `market_sentiment` (история по часам), последнее значение кэшируется в Redis. Reddit-хайп — в `reddit_hype` с per-symbol скором `0..1`, нормализованным по пику в окне 60 минут.

### Использование в стратегиях

Все новостные данные доступны DSL-функциями (см. ниже):

- `news_sentiment[minutes]` — средний сентимент **за последние N минут**, отфильтрованный по `ctx.symbol`;
- `news_blackout[]` — `true` во время события высокой важности;
- `fear_greed[]` — текущее значение F&G (`0..100`);
- `reddit_hype[]` — хайп-скор для текущего символа (`0..1`).

---

## Движок стратегий (DSL)

Стратегия — это YAML-документ. Парсер валидирует структуру, ограничивает глубину вложенности (макс. 6) и общее число сравнений (макс. 50).

### Структура

```yaml
name: "Моя стратегия"
description: "..."
timeframes: ["15m", "1h"]
cooldown_min: 10
params:
  rsi_overbought: 70

entry:
  long:
    all_of:
      - { lhs: { close: ["15m"] }, op: ">", rhs: { ema: ["15m", 20] } }
      - { lhs: { rsi: ["15m", 14] }, op: "<", rhs: { param: rsi_overbought } }
      - { lhs: { fear_greed: [] }, op: "<", rhs: 75 }   # запретить лонг в экстремальной жадности
  short:
    all_of:
      - ...

sl: { atr_mult: 1.5, tf: "15m" }   # либо { pct: 0.005, tf: "15m" }
tp: { atr_mult: 2.5, tf: "15m" }

news_modifier:
  allow_veto: true   # отменить сигнал при сильном противоположном сентименте
  allow_boost: true  # +15% к confidence при сонаправленном сентименте
```

### Логические узлы (`RuleNode`)

- `{ all_of: [...] }` — И
- `{ any_of: [...] }` — ИЛИ
- `{ not: <node> }` — отрицание
- сравнение: `{ lhs: <value>, op: "<op>", rhs: <value> }`

Операторы: `<`, `>`, `<=`, `>=`, `==`, `!=`, `crosses_above`, `crosses_below`.

### Значения (`ValueRef`)

Литералы (число, строка, bool), параметры `{ param: name }`, либо индикаторы и контекстные функции:

| Функция | Аргументы | Что возвращает |
|---|---|---|
| `rsi` | `[tf, length]` | RSI |
| `macd_line`, `macd_signal`, `macd_hist` | `[tf]` | компоненты MACD |
| `ema`, `sma` | `[tf, length]` | скользящая средняя |
| `atr` | `[tf, length]` | ATR |
| `close`, `open`, `high`, `low`, `volume` | `[tf]` | OHLCV последней свечи |
| `bb_upper`, `bb_basis`, `bb_lower` | `[tf, length, std]` | Bollinger Bands |
| `donchian_high`, `donchian_low` | `[tf, length]` | Donchian |
| `vwap` | `[tf]` | VWAP |
| `supertrend` | `[tf, length, mult]` | `+1` / `-1` |
| `ha_open`, `ha_close`, `ha_high`, `ha_low` | `[tf]` | Heikin Ashi |
| `stochrsi_k`, `stochrsi_d` | `[tf, rsi_len, stoch_len, k_smooth, d_smooth]` | стохастический RSI |
| `news_sentiment` | `[minutes]` | средний сентимент в окне (`-1..+1`) |
| `news_blackout` | `[]` | `true` во время события календаря |
| `fear_greed` | `[]` | индекс Fear & Greed (`0..100`) |
| `reddit_hype` | `[]` | хайп-скор для `ctx.symbol` (`0..1`) |
| `minute_of_hour`, `hour_of_day_utc` | `[]` | временны́е фильтры |

### Встроенные стратегии

Лежат в `backend/app/signals/dsl/builtins/`:

`multi_tf_confluence` (дефолтная), `ema_9_21_cross`, `macd_trend`, `rsi_mean_reversion`, `bb_reversion`, `donchian_breakout`, `supertrend`, `vwap_bounce`, `orb_open_range`, `heikin_ashi`, `abely_scalper` (быстрый скальпер на 3m).

Любую встроенную можно форкнуть в свою копию через UI или REST: `POST /api/strategies/{id}/fork` → правка YAML → сохранить → выбрать в Settings → Strategies для нужной пары.

---

## Сигналы, исполнение и риск-контроль

### Поток

1. Ингестор получает закрытую свечу с биржи → пишет в Redis `klines:{exchange}:{symbol}:{tf}` → публикует событие `kline_closed` в канал `signals`.
2. Воркер `signals` подписан на канал. На каждом событии находит всех пользователей с этой `(exchange, symbol)` в watchlist, для каждого — выбранную стратегию (или дефолтную).
3. Воркер собирает: клайны нужных таймфреймов из Redis, новости за 30 минут (из БД), флаг блэкаута, актуальный F&G и Reddit-хайп (из Redis) — упаковывает в `MarketCtx` и запускает `evaluate_strategy()`.
4. Если стратегия возвращает `Signal` — запись пишется в таблицу `signals` и публикуется в канал `signals` (UI и Telegram-бот слушают этот канал).
5. На каждую пару действует `cooldown_min` минут после сигнала: повторные не генерируются (чтобы не «спамить»).

### Авто-исполнение

В режиме `auto_execute` подписан воркер `executor`. На каждый новый сигнал он:

1. Прогоняет риск-контур (см. ниже). При фейле — `risk_events.ok=false`, ордер не выставляется.
2. Округляет `qty` под `lot_size` и `entry` под `tick_size` (значения из `instruments`).
3. Размещает MARKET-ордер на биржу, опционально с reduce-only SL/TP.
4. Пишет запись в `orders`, публикует событие исполнения.

Воркер `fillstream` параллельно слушает websocket-потоки исполнений у биржи и подтягивает фактические `qty` / `entry_price`. Воркер `tracker` периодически закрывает завершённые позиции и считает `realized_pnl_usdt`.

### Риск-контур

Настраивается в **Settings → Risk** (хранится в `risk_configs`):

- **Per-trade max notional (USDT)** — лимит на размер одной позиции.
- **Daily loss limit (USDT)** — kill-switch: после превышения дневного убытка все новые ордера блокируются до полуночи UTC.
- **Max concurrent positions** — максимум одновременно открытых позиций.
- **Require SL/TP** — отклонять сигналы без выставленных стопов.

Каждое срабатывание (как успех, так и блокировка) фиксируется в `risk_events` с указанием причины.

---

## Бэктест

В редакторе стратегий (`StrategyEdit.tsx`) есть встроенный бэктест: выбираете пару и горизонт (часы), бэкенд прокатывает стратегию по историческим клайнам и возвращает:

- общий PnL (USDT и %),
- win-rate,
- максимальный drawdown,
- кривую эквити,
- журнал сделок (вход, выход, причина закрытия: `tp` / `sl` / `timeout`).

Запуск также доступен через REST: `POST /api/strategies/{id}/backtest` с телом `{exchange, symbol, hours}`.

---

## Telegram-бот

1. Создайте бота через [@BotFather](https://t.me/BotFather), получите токен.
2. Положите токен в `.env` → `TELEGRAM_BOT_TOKEN=...` и перезапустите сервис `telegram`.
3. В UI откройте **Settings → Telegram → Generate link token**.
4. В Telegram напишите боту: `/start <токен>`. Бот свяжет ваш chat_id с аккаунтом.

После этого каждый сигнал приходит вам в чат с двумя inline-кнопками:
- **Execute** — поставить рыночный ордер прямо из чата (если `auto_execute` выключен);
- **Dismiss** — пометить сигнал как отклонённый.

---

## Миграции БД и обновление

Миграции прогоняются автоматически при старте контейнера `backend` (`alembic upgrade head` в `command:`). При обновлении кода обычно достаточно:

```bash
git pull
docker compose build
docker compose up -d
```

Если что-то не сошлось — выполните вручную:

```bash
docker compose exec backend alembic upgrade head
docker compose restart backend signals news executor
```

Список миграций (`backend/alembic/versions/`):

- `0001_init` — базовая схема (users, signals, orders, …)
- `0002_strategies` — таблицы `strategies` и `user_strategy_selections`
- `0003_seed_more_builtins` — посев встроенных стратегий
- `0004_multi_exchange` — exchange-столбцы, `instruments`, `user_watchlist`, passphrase для OKX
- `0005_market_sentiment` — `market_sentiment` (F&G) и `reddit_hype`
- `0006_app_settings` — зашифрованные системные настройки (ключи новостных API)

---

## Разработка и тесты

Прогон тестов:

```bash
docker compose run --rm backend pytest
```

Линтер:

```bash
docker compose run --rm backend ruff check app/
```

Локальный фронтенд без Docker (бэкенд при этом всё равно в Docker):

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173 → проксирует /api на :8000
npx tsc -b       # типчек
```

Локальный бэкенд без Docker (Python 3.12, Postgres и Redis на хосте):

```bash
cd backend
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --reload
```

---

## Технологический стек

- **Backend:** FastAPI · SQLAlchemy 2.0 (async) · Alembic · asyncpg · Redis · httpx · websockets · ccxt · pandas
- **Frontend:** React 18 · Vite · TanStack Query · shadcn/ui · Tailwind · lightweight-charts · CodeMirror (YAML)
- **Инфраструктура:** Docker Compose · Postgres 16 · Redis 7
- **Шифрование:** Fernet (cryptography) — биржевые ключи, ключи новостных API, любые секреты в `app_settings`
- **Боты:** python-telegram-bot

---

## Лицензия и поддержка

Self-hosted, ничего не отправляется наружу кроме запросов к выбранным биржам, новостным API и Telegram. Перед боевой торговлей — **обязательно прогоните стратегию через тестнет** и проверьте поведение риск-контура (особенно `daily_loss_limit_usdt`).

Issues и pull requests — в репозитории [MiniAvarec/minitrader](https://github.com/MiniAvarec/minitrader).
