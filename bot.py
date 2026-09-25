"""nonlogs.io -> Telegram bildirim botu.

- Anasayfadaki "Recent Trades" akışına yeni işlem düşünce bildirir.
- PAIRS içindeki paritelerin order book'unda değişiklik olunca bildirir.
- /start yazan herkes abone olur, /stop ile çıkar.
"""

import asyncio
import json
import logging
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from messages import orderbook_messages, trade_message, welcome_message
from nonlogs_api import NonlogsClient

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
DEFAULT_PAIRS = (
    "GRIN-USDT,GRIN-XMR,GRIN-USDC,GRIN-BTC,"
    "ARRR-USDT,"
    "FIRO-USDT,FIRO-XMR,FIRO-BTC,"
    "XMR-USDT,XMR-USDC,XMR-BTC,"
    "ZEC-USDT,ZEC-XMR,ZEC-USDC,ZEC-BTC,"
    "DGB-USDT"
)
PAIRS = [p.strip().upper() for p in os.getenv("PAIRS", DEFAULT_PAIRS).split(",") if p.strip()]
# Recent Trades'te bu coinlerin geçtiği paritelerin işlemleri bildirilmez (ör. WOW-BTC, WOW-USDT)
EXCLUDED_COINS = {c.strip().upper() for c in os.getenv("EXCLUDED_COINS", "WOW").split(",") if c.strip()}
TRADES_POLL_SECONDS = float(os.getenv("TRADES_POLL_SECONDS", "2"))
ORDERBOOK_POLL_SECONDS = float(os.getenv("ORDERBOOK_POLL_SECONDS", "5"))
# Order book'tan iptal edilen/geri çekilen emirleri bildir. Eşleşme ile azalanlar
# bildirilmez (onlar zaten Recent Trades bildirimi olarak geliyor).
NOTIFY_CANCELLED_ORDERS = os.getenv("NOTIFY_CANCELLED_ORDERS", "true").lower() == "true"
SUBSCRIBERS_FILE = Path(os.getenv("SUBSCRIBERS_FILE", "subscribers.json"))

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("nonlogs-bot")


# ---------------------------------------------------------------- subscribers

def load_subscribers() -> set[int]:
    try:
        return set(json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return set()


def save_subscribers(subs: set[int]) -> None:
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps(sorted(subs)), encoding="utf-8")


subscribers = load_subscribers()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.add(update.effective_chat.id)
    save_subscribers(subscribers)
    await update.message.reply_text(welcome_message(PAIRS), parse_mode=ParseMode.HTML)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)
    save_subscribers(subscribers)
    await update.message.reply_text("🔕 Bildirimler durduruldu. Tekrar açmak için /start")


async def send(app: Application, chat_id: int, text: str) -> None:
    await app.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


async def broadcast(app: Application, text: str) -> None:
    for chat_id in list(subscribers):
        try:
            try:
                await send(app, chat_id, text)
            except RetryAfter as e:
                wait = e.retry_after
                await asyncio.sleep(wait.total_seconds() if hasattr(wait, "total_seconds") else wait)
                await send(app, chat_id, text)
        except Forbidden:
            # Kullanıcı botu engellemiş / sohbeti silmiş
            subscribers.discard(chat_id)
            save_subscribers(subscribers)
        except TelegramError as e:
            log.warning("send to %s failed: %s", chat_id, e)
        await asyncio.sleep(0.05)  # Telegram limitine takılmamak için


# ---------------------------------------------------------------- order book diff

# API her tarafta en fazla bu kadar fiyat seviyesi döndürüyor. Liste doluyken en alttaki
# seviyenin altı görünmüyor; oradan "yeni" gibi beliren seviyeler sahte bildirim olmasın.
BOOK_DEPTH_LIMIT = 30


def visible(levels: dict, side: str, price: Decimal) -> bool:
    if len(levels) < BOOK_DEPTH_LIMIT:
        return True
    return price >= min(levels) if side == "bids" else price <= max(levels)


def filled_amounts(old: dict, new: dict) -> dict[tuple[str, Decimal], Decimal]:
    """İki snapshot arasında gerçekleşen işlemlerin order book'tan düştüğü miktar.

    Satış işlemi alış (bids) seviyesini, alış işlemi satış (asks) seviyesini tüketir;
    işlem fiyatı = tüketilen seviyenin fiyatı.
    """
    filled: dict[tuple[str, Decimal], Decimal] = {}
    old_ids = set(old.get("trades", {}))
    for trade_id, (side, price, amount) in new.get("trades", {}).items():
        if trade_id in old_ids:
            continue
        book_side = "bids" if side == "sell" else "asks"
        filled[(book_side, price)] = filled.get((book_side, price), Decimal(0)) + amount
    return filled


def diff_book(old: dict, new: dict) -> list[tuple[str, str, Decimal, Decimal, Decimal]]:
    """Değişiklikler: (side, kind, price, değişen miktar, seviyede kalan toplam).

    kind: new (yeni seviye), up (seviyeye ekleme), cancel (kısmi iptal), cancel_gone (seviye tamamen iptal)
    """
    changes = []
    filled = filled_amounts(old, new)
    for side in ("bids", "asks"):
        o, n = old.get(side, {}), new.get(side, {})
        for price in sorted(set(o) | set(n), reverse=True):
            if not (visible(o, side, price) and visible(n, side, price)):
                continue
            a, b = o.get(price, Decimal(0)), n.get(price, Decimal(0))
            if b > a:
                changes.append((side, "new" if a == 0 else "up", price, b - a, b))
            elif b < a and NOTIFY_CANCELLED_ORDERS:
                # Azalmanın işlemle açıklanamayan kısmı = iptal
                cancelled = (a - b) - filled.get((side, price), Decimal(0))
                if cancelled > (a - b) * Decimal("0.001"):  # yuvarlama farklarını yok say
                    changes.append((side, "cancel_gone" if b == 0 else "cancel", price, cancelled, b))
    return changes


# ---------------------------------------------------------------- watchers

def is_excluded(t: dict) -> bool:
    coins = set(str(t.get("market_code", "")).upper().split("-"))
    coins |= {str(t.get("from_symbol", "")).upper(), str(t.get("to_symbol", "")).upper()}
    return bool(coins & EXCLUDED_COINS)


async def watch_recent_trades(app: Application, api: NonlogsClient):
    seen: set[str] | None = None  # ilk turda mevcutları sadece "görüldü" say
    while True:
        try:
            executions = await api.recent_executions()
            ids = [str(t["id"]) for t in executions]
            if seen is not None:
                new = [
                    t for t in executions
                    if str(t["id"]) not in seen and not is_excluded(t)
                ]
                for t in reversed(new):  # eskiden yeniye sırayla gönder
                    await broadcast(app, trade_message(t, tracked=t.get("market_code") in PAIRS))
                seen.update(ids)
                if len(seen) > 5000:
                    seen = set(ids)
            else:
                seen = set(ids)
                log.info("recent trades seeded with %d rows", len(ids))
        except Exception as e:
            log.warning("recent trades poll failed: %s", e)
        await asyncio.sleep(TRADES_POLL_SECONDS)


async def watch_order_book(app: Application, api: NonlogsClient, pair: str):
    last: dict | None = None
    while True:
        try:
            snap = await api.market_snapshot(pair)
            if last is not None:
                changes = diff_book(last, snap)
                for text in orderbook_messages(pair, changes, snap):
                    await broadcast(app, text)
            else:
                log.info("%s order book seeded", pair)
            last = snap
        except Exception as e:
            log.warning("%s order book poll failed: %s", pair, e)
        await asyncio.sleep(ORDERBOOK_POLL_SECONDS)


# ---------------------------------------------------------------- main

async def post_init(app: Application):
    api = NonlogsClient()
    app.bot_data["api"] = api
    tasks = [asyncio.create_task(watch_recent_trades(app, api))]
    stagger = ORDERBOOK_POLL_SECONDS / max(len(PAIRS), 1)
    for i, pair in enumerate(PAIRS):
        await asyncio.sleep(stagger if i else 0)  # istekleri aralığa eşit yay
        tasks.append(asyncio.create_task(watch_order_book(app, api, pair)))
    app.bot_data["tasks"] = tasks
    log.info("watching recent trades + order books: %s", ", ".join(PAIRS))


async def post_shutdown(app: Application):
    for t in app.bot_data.get("tasks", []):
        t.cancel()
    if api := app.bot_data.get("api"):
        await api.close()


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
