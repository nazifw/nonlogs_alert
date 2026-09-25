"""nonlogs.io public JSON endpoints (the same ones the website polls)."""

from decimal import Decimal

import httpx

BASE_URL = "https://nonlogs.io"


def usd_rates(markets: list[dict]) -> dict[str, Decimal]:
    """Symbol -> USD price, from each *-USDT market's last price (USDT/USDC = 1)."""
    rates = {"USDT": Decimal(1), "USDC": Decimal(1)}
    for m in markets:
        if m.get("quote_symbol") == "USDT" and m.get("last_price"):
            rates[m["base_symbol"]] = Decimal(m["last_price"])
    return rates


class NonlogsClient:
    def __init__(self, timeout: float = 10.0):
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "nonlogs-tg-notifier/1.0"},
        )

    async def close(self):
        await self._http.aclose()

    async def recent_executions(self) -> list[dict]:
        """Homepage 'Recent Trades' feed (newest first, ~20 rows)."""
        r = await self._http.get("/api/executions/recent")
        r.raise_for_status()
        return r.json().get("executions", [])

    async def market_snapshot(self, pair: str) -> dict:
        """Order book of a pair plus market info and USD rates.

        Returns {"market": {...}, "bids": {price: amount}, "asks": {price: amount},
        "trades": {id: (side, price, amount)}, "usd_rates": {symbol: usd}}. The API aggregates orders per price level, so
        a single order is not visible individually; only the total at each price.
        """
        r = await self._http.get(f"/api/markets/{pair}/snapshot", params={"include_candles": "0"})
        r.raise_for_status()
        data = r.json()
        book = data.get("order_book") or {}
        snap = {
            side: {Decimal(lvl["price"]): Decimal(lvl["amount"]) for lvl in book.get(side, [])}
            for side in ("bids", "asks")
        }
        # Paritenin son işlemleri: bir seviyedeki azalmanın eşleşme mi iptal mi olduğunu ayırmak için
        snap["trades"] = {
            str(t["id"]): (t.get("side"), Decimal(t["price"]), Decimal(t["amount"]))
            for t in data.get("recent_trades") or []
        }
        snap["market"] = data.get("market") or {}
        snap["usd_rates"] = usd_rates(data.get("markets") or [])
        return snap
