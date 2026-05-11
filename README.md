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
11. [Инструменты на портфель (Tools)](#инструменты-на-портфель-tools)
12. [Журнал сделок и AI-ревью](#журнал-сделок-и-ai-ревью)
13. [Telegram-бот](#telegram-бот)
14. [Миграции БД и обновление](#миграции-бд-и-обновление)
15. [Разработка и тесты](#разработка-и-тесты)
16. [Технологический стек](#технологический-стек)

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

**Аналитические инструменты поверх живого портфеля.** Раздел **Tools** в UI: ребалансировщик концентрации, smart-роутер для выбора самой дешёвой биржи под заявку, walk-forward оптимизатор параметров стратегии, симулятор шок-сценариев против дневного лимита убытка.

**Журнал сделок.** Полный пост-трейд-анализ: фильтры (даты, символы, сторона, исход, PnL-диапазон, теги, заметки), агрегаты (win-rate, profit factor, expectancy, max drawdown, MFE/MAE), кривая эквити, KPI-карточки и таблица сделок с подсветкой выигрышей/проигрышей. У каждой сделки — персональные заметки и теги.

**AI-ревью сделок.** Любую открытую или закрытую сделку можно отправить на оценку трём frontier-моделям через OpenRouter (Claude, GPT, Gemini, Grok, DeepSeek — список тянется живьём из каталога OpenRouter, отфильтрованный до topовых вариантов). Модели получают весь контекст сделки: факты, индикаторы на входе (RSI/ATR/MFE/MAE), свечи 4h/1h/5m вокруг входа и после, параметры стратегии, риск-лимиты пользователя. На выходе — вердикт `good` / `mixed` / `bad`, балл 0–100, сильные/слабые стороны, конкретные рекомендации. Каждый пользователь хранит собственный OpenRouter API key (зашифрован тем же `MASTER_KEY`).

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
- **Tools** — четыре инструмента поверх живого портфеля: `Rebalancer`, `Smart Execution Router`, `Walk-Forward Optimizer`, `Scenario Simulator` (подробнее см. ниже).
- **Journal** — журнал сделок с фильтрами, KPI, кривой эквити, заметками/тегами и AI-ревью на 3 модели (подробнее см. ниже).
- **Settings** — все настройки в одном месте (см. ниже).

### Вкладки Settings

| Вкладка | Что внутри |
|---|---|
| **Strategies** | привязка стратегии к каждой `(exchange, symbol)` в watchlist (если не задано — используется встроенная `multi_tf_confluence`) |
| **Pairs** | список наблюдаемых пар, добавление/удаление через `AddPairDialog` (поиск по `instruments`) |
| **Trading mode** | переключатель `signal_only` ↔ `auto_execute` |
| **Exchanges** | ключи Binance / OKX / Bybit, кнопка `Test & save` — пробный запрос баланса перед сохранением |
| **Integrations** | ключи Finnhub, CryptoPanic, CryptoCompare, NewsData.io + Reddit User-Agent. Под каждым полем бейдж `Stored in DB` / `Loaded from .env` / `Not set`. |
| **AI Evaluation** | OpenRouter API key (шифруется), выбор 3 моделей из живого каталога OpenRouter, кнопки `Test connection` и `Refresh model list` |
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

## Инструменты на портфель (Tools)

Раздел **Tools** в UI (`/tools`) собирает четыре отдельных инструмента поверх живых позиций, watchlist и стратегий. Все экраны умеют работать в режиме «только просмотр» (preview / quote / simulate) — реальный ордер выставляется только если у пользователя включён `auto_execute`. Каждый запуск сохраняется в БД для аудита.

### Portfolio Rebalancer

Сводит открытые позиции со всех подключённых бирж в единое представление и предлагает **reduce-only** ордера, которые приводят концентрацию под заданные лимиты.

**Параметры:**

| Поле | Что задаёт |
|---|---|
| `Max exchange share %` | максимальная доля экспозиции на одной бирже от общего USDT-нотонала |
| `Max asset share %` | максимальная доля одного базового актива (например, `BTC`) |
| `Min order USDT` | заявки меньше этого порога отбрасываются (избегаем «пыли») |

Бэкенд (`backend/app/portfolio/rebalancer.py`):

1. Через каждый брокер тянет `positions()`, нормализует в `PositionExposure` (биржа, символ, base, side, нотонал, контракты, mark price).
2. Считает суммарные доли `by_exchange` и `by_asset`. Для каждой группы, у которой `share > cap`, эмитит ордер на закрытие части позиций (от самых крупных к мелким) с причиной вида `exchange_share>0.60`.
3. Дедуплицирует пересекающиеся интенты, ограничивает их нотоналом базовой позиции (нельзя «закрыть больше, чем открыто»).

`POST /api/portfolio/rebalance/preview` — собрать план (`run_id` + список интентов + предупреждения).
`POST /api/portfolio/rebalance/execute` — то же, но с реальной отправкой `reduce_only` MARKET-ордеров через `place_market_order`. Доступно только в `auto_execute`. История в таблице `portfolio_rebalance_runs`.

### Smart Execution Router

Для конкретной заявки (`symbol`, `side`, `notional_usdt`) опрашивает L2-стаканы на каждой подключённой бирже и выбирает площадку с минимальной полной стоимостью.

**Метрики (`backend/app/execution/router.py`):**

- **`expected_price`** — объёмо-взвешенная цена прохождения заявки по стакану (`estimate_market_fill`).
- **`spread_bps`** — спред между лучшим bid/ask в bps.
- **`slippage_bps`** — отклонение `expected_price` от вершины стакана.
- **`fee_usdt`** — taker-комиссия (defaults: `binance 0.04%`, `okx 0.05%`, `bybit 0.055%`).
- **`total_cost_usdt`** — `fee + notional × (spread + slippage)`. Минимизируется при выборе победителя.

Если у пользователя на бирже нет ключа или инструмент не торгуется — площадка попадает в результат с `ok=false` и причиной (`missing API key`, `symbol unavailable`).

`POST /api/execution/route` — получить котировки по всем площадкам и победителя.
`POST /api/execution/route/execute` — выставить MARKET-ордер на победителе, опционально с SL/TP (`auto_execute` только). История в `execution_route_quotes`.

### Walk-Forward Optimizer

Подбирает параметры стратегии через раздельный train/validation split — чтобы не подгонять под одно окно.

**Как работает (`backend/app/optimizer/walk_forward.py`):**

1. Раскрывает `param_grid` ({"rsi_overbought":[65,70,75]} → 3 комбинации). Лимит — 64 комбинации на запуск.
2. Для каждой комбинации запускает два бэктеста по существующему `backtest_run`: `train = 168ч (включает validation)` и `validation = последние 72ч` (значения по умолчанию).
3. Считает композитный скор: `score = val_pnl + 0.25·win_rate + 0.25·stability − 0.75·max_drawdown`, где `stability = 1 − |train_pnl − val_pnl|`. Низкая стабильность → переобучение.
4. Возвращает кандидатов, отсортированных по `score`, плюс `best`.

`POST /api/strategies/{id}/optimize` с телом `{exchange, symbol, param_grid, train_hours, validation_hours, notional_usdt, max_candidates}`.
`GET /api/strategies/{id}/optimize/{run_id}` — получить сохранённый результат. История в `optimizer_runs`.

### Scenario Simulator

Стресс-тест живого портфеля против шоковых пресетов. Ничего не отправляется на биржу — только проекция PnL и проверка дневного лимита убытка.

**Пресеты (`backend/app/scenario/simulator.py`):**

| Preset | Применяемый шок |
|---|---|
| `gap_down` | `−magnitude%` ко всем символам |
| `gap_up` | `+magnitude%` ко всем |
| `volatility_cascade` | `−1.5 × magnitude%` (расширенный обвал) |
| `stop_series` | `−magnitude%` (каскад срабатываний стопов) |
| `correlation_spike` | `−magnitude%` (одновременная корреляция → 1) |

Можно вместо пресета передать кастомный `price_shocks` — словарь `{"*": -0.05, "BTCUSDT": -0.08}`. Поиск ключа: точный символ → `base` (например, `BTC`) → `*`.

Для каждой позиции считается `pnl = notional × shock × ±1` (минус если `short`, плюс если `long`). Затем:

- `total_pnl_usdt` — суммарный шок-эффект.
- `projected_daily_pnl_usdt` — `today_realized + total`.
- `daily_loss_usage` — какая доля `daily_loss_limit_usdt` (из `risk_configs`) уйдёт.
- `daily_loss_breached` — `true`, если шок пробьёт kill-switch.

`POST /api/risk/scenarios` с телом `{preset, magnitude_pct}` или `{price_shocks: {...}}`.
`GET /api/risk/scenarios/{run_id}` — получить сохранённый результат. История в `scenario_runs`.

---

## Журнал сделок и AI-ревью

### Журнал (`/journal`)

Read-and-annotate-надстройка над таблицей `orders`. Всё считается на лету в Python из отфильтрованного набора (типичный пользователь — <100k закрытых сделок, так что хватает).

**Фильтры:** `date_from/to`, символы, биржа, сторона (`buy` / `sell`), статус (`open` / `closed` / `partial`), стратегия, исход (`win` / `loss` / `breakeven`), `min_pnl / max_pnl`, поиск по символу и заметкам.

**KPI-карточки:** total trades, win rate, net PnL, gross profit/loss, profit factor, avg win / avg loss, largest win/loss, expectancy, average duration, max drawdown (USDT и %).

**Группировки:** по символу, стороне, стратегии, дню недели, часу суток — каждая бакета отдаёт `count`, `net_pnl`, `win_rate`.

**Кривая эквити:** массив `{t, pnl, equity}`, рендерится через lightweight-charts.

**Аннотации:** на каждой сделке пользователь хранит `notes` (текст до 2048 символов) и `tags` (до 32 коротких тегов). `PATCH /journal/deals/{id}` обновляет их атомарно.

**Endpoints:** `GET /journal/deals`, `GET /journal/stats`, `GET /journal/equity-curve`, `GET /journal/filters`, `PATCH /journal/deals/{id}`.

### AI-ревью сделок

Любую сделку (открытую или закрытую) из Журнала можно отправить на ревью трём моделям через OpenRouter параллельно. Каждая возвращает вердикт `good` / `mixed` / `bad`, балл 0–100, краткое резюме и списки сильных / слабых сторон / рекомендаций.

#### Что получают модели

Сборщик контекста (`backend/app/ai/context.py`) формирует один и тот же бриф для всех трёх моделей:

- факты по сделке (символ, биржа, направление, qty, нотонал, entry/exit, SL/TP, fee, realized/unrealized PnL, ROI%, R-multiple, duration);
- параметры пристёгнутой стратегии (имя + ключевые поля из YAML);
- риск-лимиты пользователя (`max_notional`, `daily_loss_limit`, `max_concurrent_positions`, `require_sl_tp`);
- свечи вокруг входа на трёх таймфреймах: 30×4h, 50×1h до входа, 24×5m, и 50×1h **после** входа (до закрытия — для закрытых сделок, до текущего момента — для открытых);
- производные индикаторы на момент входа: RSI(14), ATR(14), расстояние entry→SL в ATR, отношение объёма к 20-bar SMA, max favorable / max adverse excursion с момента входа;
- пользовательские заметки и теги по сделке.

Один и тот же контекст идёт во все три модели — это позволяет напрямую сравнивать их ответы.

#### Каталог моделей OpenRouter

Список моделей в **Settings → AI Evaluation** подгружается **на лету** с `https://openrouter.ai/api/v1/models` (без авторизации, кэш 1 час in-process). После загрузки список фильтруется до frontier-уровня:

- белый список лабораторий: Anthropic, OpenAI, Google, xAI, DeepSeek, Meta, Qwen, Mistral;
- отсекаются явные не-frontier варианты: `mini`, `flash`, `haiku`, `nano`, `lite`, `small`, `distill`, `*-7b/8b/13b`, embeddings, vision-only, `:free` / `:beta` / `:nitro`;
- сортировка: сначала по лабам в каноническом порядке, внутри лабы — newest first.

Кнопка **Refresh model list** в настройках принудительно перечитывает каталог. Если OpenRouter недоступен, используется предыдущий снапшот; если и его нет — компактный baked-in fallback (`backend/app/ai/__init__.py`).

При первом открытии Settings бэкенд выбирает дефолтные `model_a/b/c` как лучшие представители Anthropic / OpenAI / Google из живого каталога — пользователь может переопределить любую из трёх. Если выбранная модель потом исчезнет из каталога (ротация OpenRouter), она остаётся в дропдауне с пометкой `(legacy)`, чтобы Select не выглядел пустым.

#### Запуск и хранение

В Журнале откройте карточку сделки → **Evaluate with AI (3 models)**. Бэкенд (`POST /journal/deals/{id}/evaluate`) собирает контекст один раз, делает fan-out через `asyncio.gather` к трём моделям с принудительным `response_format: json_object` (`temperature=0.2`, `max_tokens=1500`), нормализует ответы, записывает три строки в `order_evaluations` (одна на модель) и возвращает их фронту.

- **Rate-limit:** 20 запусков `evaluate` в час на пользователя, 10 `test`-пингов в минуту, 5 `refresh-catalog` в минуту.
- **История:** `GET /journal/deals/{id}/evaluations` отдаёт последний результат на каждую из трёх моделей; кнопка **Re-evaluate** перетирает её.
- **Стоимость:** карточка ответа показывает `prompt_tokens + completion_tokens` и `cost_usd`, если OpenRouter вернул `usage.cost`.
- **Ключ:** хранится в `user_ai_settings.encrypted_openrouter_key` (Fernet, `MASTER_KEY`); никогда не возвращается из API наружу — только бейдж `Stored` / `Not set`.

#### Файлы

- `backend/app/ai/openrouter.py` — async-клиент OpenRouter (httpx, JSON-mode, обработка завёрнутого в ` ```json ` ответа).
- `backend/app/ai/catalog.py` — live-fetch каталога, фильтрация frontier, in-process TTL-кэш, выбор дефолтных моделей.
- `backend/app/ai/context.py` — сборка контекста сделки (свечи через `broker.fetch_klines`, индикаторы пур-Python без новых зависимостей).
- `backend/app/ai/prompts.py` — system-prompt с JSON-схемой и markdown-юзер-prompt; разные формулировки для открытых vs. закрытых сделок.
- `backend/app/api/ai_eval.py` — `POST/GET /journal/deals/{id}/evaluat{e,ions}`.
- `backend/app/api/settings_ai.py` — `GET/PUT /settings/ai`, `POST /settings/ai/test`, `POST /settings/ai/refresh-catalog`.

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
- `0007_trading_intelligence` — таблицы аудита Tools: `portfolio_rebalance_runs`, `execution_route_quotes`, `optimizer_runs`, `scenario_runs`
- `0008_user_admin_approval` — поля `is_admin` / `is_approved` на пользователях (admin-approved registration)
- `0009_signal_order_indexes` — индексы на `signals.created_at` и `orders.created_at` для быстрых выборок журнала
- `0010_order_journal_fields` — поля журнала на ордерах: `exit_price`, `fee_usdt`, `notes`, `tags`
- `0011_ai_evaluations` — `user_ai_settings` (зашифрованный OpenRouter key + 3 выбранные модели) и `order_evaluations` (по строке на каждую модель × сделку)

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

## Деплой на свой сервер (до 10 пользователей)

Минимальный продакшен-сетап для small VPS с TLS на стороне облака (Cloudflare / ALB / любой L7-балансировщик):

1. **Подготовка `.env`** — скопируйте `.env.example` в `.env` на сервере, задайте:
   - `APP_ENV=prod`
   - `JWT_SECRET`, `MASTER_KEY`, `WORKER_SHARED_SECRET`, `TELEGRAM_WEBHOOK_SECRET` — длинные случайные строки.
   - `POSTGRES_PASSWORD` — сильный пароль (не `trader`).
   - `REDIS_PASSWORD` — длинная случайная строка; `REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0`.
   - `ADMIN_EMAIL` — ваш email; первый, кто зарегистрируется с этим адресом, получит права админа.
   - `FRONTEND_ORIGIN` — публичный URL фронтенда (например `https://trader.example.com`).
2. **Запуск:** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`.
   - Базовый `docker-compose.yml` остаётся dev-конфигом (live-reload, открытые порты Postgres/Redis). Оверлей `docker-compose.prod.yml` убирает всё лишнее, переключает фронт на nginx-сборку, добавляет `restart: unless-stopped`.
   - Миграции (`alembic upgrade head`) выполняются автоматически при старте backend.
3. **TLS:** ваш облачный edge терминирует HTTPS и проксирует на `http://<host>:80` (nginx-фронт), передавая `X-Forwarded-For` и `X-Forwarded-Proto`. Backend запускается с `--proxy-headers --forwarded-allow-ips=*`, поэтому cookies автоматически выставляются `Secure`, а rate-limit считается по реальному IP клиента.
4. **Первый запуск:**
   - Зарегистрируйтесь под `ADMIN_EMAIL` — аккаунт сразу активен, в сайдбаре появится пункт **Admin**.
   - Друзья регистрируются как обычно, попадают в очередь **Pending** на `/admin`. Жмёте **Approve** — человек может войти.
5. **Безопасность по умолчанию (после этого обновления):**
   - Регистрации до одобрения админом не дают сессии.
   - Rate-limit: 10 логинов/минута, 5 регистраций/час, 10 бэктестов/минута, 5 оптимизаций/минута (на IP).
   - Cookies `HttpOnly + SameSite=Lax + Secure` (в prod), JWT действителен 24 ч, ws-токен — 5 мин.
   - WebSocket `/ws/live` пропускает к пользователю только его собственные сигналы.
   - Postgres и Redis недоступны с публичного IP, Redis под паролем.
   - Заголовки `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `HSTS` выставляются автоматически.
   - Лимит на размер тела запроса 1 MiB.

Бэкап БД делается изнутри VPS: `docker compose exec postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql`.

---

## Лицензия и поддержка

Self-hosted, ничего не отправляется наружу кроме запросов к выбранным биржам, новостным API и Telegram. Перед боевой торговлей — **обязательно прогоните стратегию через тестнет** и проверьте поведение риск-контура (особенно `daily_loss_limit_usdt`).

Issues и pull requests — в репозитории [MiniAvarec/minitrader](https://github.com/MiniAvarec/minitrader).
