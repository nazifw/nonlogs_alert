# nonlogs_alert

**English** | [Türkçe](README.tr.md)

A Telegram bot that sends real-time alerts for activity on the [nonlogs.io](https://nonlogs.io) exchange.

## What does it notify?

- **Executed trades** — Every new buy/sell that appears in the homepage "Recent Trades" feed (amount, value, unit price, direction, time). Pairs containing coins listed in `EXCLUDED_COINS` are skipped (default: `WOW`).
- **New order book orders** — New buy/sell orders placed on tracked pairs, or additions to an existing price level.
- **Cancelled orders** — Orders pulled from the order book. Decreases caused by matches (trades) are not counted as cancellations; those already arrive as trade alerts.

Values are shown with their USD equivalent, using the last prices of the USDT pairs. Alert messages are in Turkish and timestamps are in Turkey time (TSİ, UTC+3).

## Usage

In a chat with the bot:

| Command  | Description                  |
|----------|------------------------------|
| `/start` | Subscribe to alerts          |
| `/stop`  | Stop alerts                  |

Subscribers are stored in `subscribers.json`. Users who block the bot are removed from the list automatically.

## Setup

Requires Python 3.13.

```bash
git clone https://github.com/nazifw/nonlogs_alert.git
cd nonlogs_alert
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
BOT_TOKEN=123456:ABC...        # token from @BotFather (required)
```

Run:

```bash
python bot.py
```

## Configuration

All settings are set via environment variables (or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_TOKEN` | — | Telegram bot token (required) |
| `PAIRS` | GRIN, ARRR, FIRO, XMR, ZEC, DGB pairs | Pairs whose order books are tracked, comma-separated (e.g. `XMR-USDT,ZEC-BTC`) |
| `EXCLUDED_COINS` | `WOW` | Coins to skip in trade alerts |
| `TRADES_POLL_SECONDS` | `2` | Recent Trades polling interval (seconds) |
| `ORDERBOOK_POLL_SECONDS` | `5` | Order book polling interval (seconds) |
| `NOTIFY_CANCELLED_ORDERS` | `true` | Send alerts for cancelled orders |
| `SUBSCRIBERS_FILE` | `subscribers.json` | File where the subscriber list is stored |

## Deploy

The repo includes a Heroku/Railway-compatible `Procfile` (`worker: python bot.py`). Just set `BOT_TOKEN` as an environment variable on the platform. To keep the subscriber list across restarts, point `SUBSCRIBERS_FILE` to a persistent disk (volume).

## How it works

The bot periodically polls the same public JSON endpoints that the nonlogs.io website itself uses:

- `GET /api/executions/recent` — recent trades
- `GET /api/markets/{PAIR}/snapshot` — pair order book, recent trades and market info

On each round, the new snapshot is compared with the previous one. Since the API aggregates orders per price level, alerts report the **change in total amount at a price level**, not individual orders. The part of a decrease that can't be explained by trades is treated as a cancellation. The API returns at most 30 levels per side, so levels sliding in from outside the visible range are filtered out to avoid false alerts.

On startup, the bot only records the current state as "seen"; alerts start with changes after startup.

## Files

| File | Contents |
|------|----------|
| `bot.py` | Telegram commands, subscriber management, polling loops, order book diffing |
| `nonlogs_api.py` | nonlogs.io API client |
| `messages.py` | Alert message texts (HTML) |
