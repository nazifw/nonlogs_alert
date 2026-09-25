"""Telegram bildirim metinleri (HTML)."""

import html
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from nonlogs_api import BASE_URL

SEP = "━━━━━━━━━━━━━━━━━━"
TR_TZ = timezone(timedelta(hours=3))  # Türkiye saati (TSİ), yaz saati uygulaması yok
STABLES = {"USDT", "USDC"}
TELEGRAM_LIMIT = 4000


# ---------------------------------------------------------------- sayı / zaman

def num(d: Decimal, max_dp: int = 8) -> str:
    """1234.50000000 -> '1,234.5'"""
    q = Decimal(d).quantize(Decimal(1).scaleb(-max_dp), rounding=ROUND_HALF_UP)
    s = format(q, ",f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def usd(d: Decimal) -> str:
    d = Decimal(d)
    if d >= 1:
        return f"${d:,.2f}"
    if d == 0:
        return "$0"
    # 1$ altı: 4 anlamlı basamak ($0.009460)
    dp = -d.adjusted() + 3
    s = format(d.quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP), "f")
    return "$" + s.rstrip("0").rstrip(".")


def tr_time(dt: datetime | None = None) -> str:
    dt = (dt or datetime.now(timezone.utc)).astimezone(TR_TZ)
    return dt.strftime("%d.%m.%Y %H:%M:%S") + " TSİ"


def parse_iso(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def e(value) -> str:
    return html.escape(str(value))


def trade_link(code: str, label: str) -> str:
    return f'🔗 <a href="{BASE_URL}/trade/{e(code)}">{e(label)} sayfasını aç</a>'


def in_quote(amount: Decimal, quote: str, rate: Decimal | None, bold: bool = True) -> str:
    """Quote cinsinden tutar + dolar karşılığı: '1.875 XMR (≈ $708.75)' / '$7.75'"""
    b, _b = ("<b>", "</b>") if bold else ("", "")
    if quote in STABLES:
        return f"{b}{usd(amount)}{_b}"
    text = f"{b}{num(amount)} {e(quote)}{_b}"
    return f"{text}  (≈ {usd(amount * rate)})" if rate else text


# ---------------------------------------------------------------- recent trades

def trade_message(t: dict, tracked: bool = False) -> str:
    is_buy = t.get("side") == "buy"
    head = "🟢 ALIŞ GERÇEKLEŞTİ" if is_buy else "🔴 SATIŞ GERÇEKLEŞTİ"
    qty = Decimal(t["quantity"])
    value = Decimal(t["usdt_value"]) if t.get("usdt_value") is not None else None
    approx = "≈ " if t.get("usdt_value_estimated") else ""

    lines = [f"<b>{head}</b>" + (f"  ·  <b>{approx}{usd(value)}</b>" if value is not None else "")]
    lines.append(f"<b>{e(t['market_label'])}</b>" + ("  ⭐ takip listende" if tracked else ""))
    lines.append(SEP)
    lines.append(f"📦 Miktar:  <b>{num(qty)} {e(t['quantity_symbol'])}</b>")
    if value is not None:
        lines.append(f"💵 Tutar:  <b>{approx}{usd(value)}</b>")
        if qty > 0:
            lines.append(f"🏷 Birim fiyat:  {approx}{usd(value / qty)}")
    else:
        lines.append("💵 Tutar:  —")
    lines.append(f"🔄 Yön:  {e(t['from_symbol'])} ➜ {e(t['to_symbol'])}")
    executed = parse_iso(t.get("executed_at_iso"))
    lines.append(f"🕒 {tr_time(executed) if executed else e(t.get('executed_at_display', ''))}")
    lines.append(SEP)
    lines.append(trade_link(t["market_code"], t["market_label"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- order book

def orderbook_card(pair: str, change: tuple, snap: dict) -> str:
    side, kind, price, amount, level_total = change
    market = snap.get("market") or {}
    base = market.get("base_symbol") or pair.split("-")[0]
    quote = market.get("quote_symbol") or pair.split("-")[1]
    label = market.get("pair") or pair.replace("-", "/")
    rate = snap["usd_rates"].get(quote)
    side_txt = "ALIŞ" if side == "bids" else "SATIŞ"
    total = amount * price
    total_usd = total * rate if rate else None

    if kind in ("new", "up"):
        head = f"{'🟢' if side == 'bids' else '🔴'} YENİ {side_txt} EMRİ"
    else:
        head = f"❌ {side_txt} EMRİ İPTAL EDİLDİ"

    lines = [f"<b>{head}</b>" + (f"  ·  <b>{usd(total_usd)}</b>" if total_usd is not None else "")]
    lines.append(f"<b>{e(label)}</b>")
    lines.append(SEP)
    lines.append(f"💰 Fiyat:  {in_quote(price, quote, rate)}")
    lines.append(f"📦 {'İptal edilen miktar' if kind.startswith('cancel') else 'Miktar'}:  <b>{num(amount)} {e(base)}</b>")
    lines.append(f"💵 Tutar:  {in_quote(total, quote, rate)}")
    if kind == "up":
        lines.append(f"📊 Bu fiyattaki toplam:  {num(level_total)} {e(base)}")
    elif kind == "cancel":
        lines.append(f"📊 Bu fiyatta kalan:  {num(level_total)} {e(base)}")
    elif kind == "cancel_gone":
        lines.append("📊 Bu fiyatta başka emir kalmadı")

    lines.append(SEP)
    bids, asks = snap.get("bids") or {}, snap.get("asks") or {}
    best_bid = in_quote(max(bids), quote, rate, bold=False) if bids else "—"
    best_ask = in_quote(min(asks), quote, rate, bold=False) if asks else "—"
    lines.append(f"📈 En iyi alış:  {best_bid}")
    lines.append(f"📉 En iyi satış:  {best_ask}")
    lines.append(f"🕒 {tr_time()}")
    lines.append(trade_link(pair, label))
    return "\n".join(lines)


def orderbook_messages(pair: str, changes: list[tuple], snap: dict) -> list[str]:
    """Aynı turdaki değişiklikleri Telegram limitine sığacak şekilde mesajlara böler."""
    messages, current = [], ""
    for change in changes:
        card = orderbook_card(pair, change, snap)
        if current and len(current) + len(card) + 2 > TELEGRAM_LIMIT:
            messages.append(current)
            current = card
        else:
            current = f"{current}\n\n{card}" if current else card
    if current:
        messages.append(current)
    return messages


# ---------------------------------------------------------------- komutlar

def welcome_message(pairs: list[str]) -> str:
    return (
        "<b>✅ nonlogs.io bildirimlerine abone oldun</b>\n"
        f"{SEP}\n"
        "Şunları anlık bildireceğim:\n"
        "• Recent Trades'e düşen <b>tüm gerçekleşen işlemler - WOW</b>\n"
        "• Takip edilen paritelerde <b>order book'a giren alış/satış emirleri</b>\n"
        "• Takip edilen paritelerde <b>iptal edilen emirler</b>\n"
        f"{SEP}\n"
        f"<b>📋 Takip edilen pariteler ({len(pairs)}):</b>\n"
        f"<code>{e(', '.join(pairs))}</code>\n\n"
        "Bildirimleri durdurmak için /stop"
    )
