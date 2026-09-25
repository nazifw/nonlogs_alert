# nonlogs_alert

[nonlogs.io](https://nonlogs.io) borsasındaki hareketleri anlık olarak Telegram'a bildiren bot.

## Ne bildirir?

- **Gerçekleşen işlemler** — Anasayfadaki "Recent Trades" akışına düşen her yeni alış/satış (miktar, tutar, birim fiyat, yön, saat). `EXCLUDED_COINS` içindeki coinlerin pariteleri atlanır (varsayılan: `WOW`).
- **Yeni order book emirleri** — Takip edilen paritelerde order book'a giren yeni alış/satış emirleri veya mevcut fiyat seviyesine yapılan eklemeler.
- **İptal edilen emirler** — Order book'tan çekilen emirler. Eşleşme (işlem) sonucu azalan miktarlar iptal sayılmaz; bunlar zaten işlem bildirimi olarak gelir.

Tutarlar, USDT paritelerindeki son fiyatlar kullanılarak dolar karşılığıyla gösterilir. Saatler Türkiye saatindedir (TSİ).

## Kullanım

Botla sohbette:

| Komut   | Açıklama                    |
|---------|-----------------------------|
| `/start` | Bildirimlere abone ol       |
| `/stop`  | Bildirimleri durdur         |

Aboneler `subscribers.json` dosyasında tutulur. Botu engelleyen kullanıcılar listeden otomatik çıkarılır.

## Kurulum

Python 3.13 gerekir.

```bash
git clone https://github.com/nazifw/nonlogs_alert.git
cd nonlogs_alert
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Proje köküne bir `.env` dosyası oluştur:

```env
BOT_TOKEN=123456:ABC...        # @BotFather'dan alınan token (zorunlu)
```

Çalıştır:

```bash
python bot.py
```

## Ayarlar

Tüm ayarlar ortam değişkeni (veya `.env`) üzerinden yapılır:

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `BOT_TOKEN` | — | Telegram bot token'ı (zorunlu) |
| `PAIRS` | GRIN, ARRR, FIRO, XMR, ZEC, DGB pariteleri | Order book'u takip edilecek pariteler, virgülle ayrılmış (ör. `XMR-USDT,ZEC-BTC`) |
| `EXCLUDED_COINS` | `WOW` | İşlem bildirimlerinde atlanacak coinler |
| `TRADES_POLL_SECONDS` | `3` | Recent Trades sorgulama aralığı (sn) |
| `ORDERBOOK_POLL_SECONDS` | `5` | Order book sorgulama aralığı (sn) |
| `NOTIFY_CANCELLED_ORDERS` | `true` | İptal edilen emirleri bildir |
| `SUBSCRIBERS_FILE` | `subscribers.json` | Abone listesinin tutulduğu dosya |

## Deploy

Repoda Heroku/Railway uyumlu bir `Procfile` var (`worker: python bot.py`). Platformda `BOT_TOKEN`'ı ortam değişkeni olarak tanımlaman yeterli. Abone listesinin yeniden başlatmalarda kaybolmaması için `SUBSCRIBERS_FILE`'ı kalıcı bir diske (volume) yönlendir.

## Nasıl çalışır?

Bot, nonlogs.io sitesinin kendisinin kullandığı herkese açık JSON uç noktalarını belirli aralıklarla sorgular:

- `GET /api/executions/recent` — son işlemler
- `GET /api/markets/{PAIR}/snapshot` — parite order book'u, son işlemler ve piyasa bilgileri

Her turda yeni snapshot bir öncekiyle karşılaştırılır. API emirleri fiyat seviyesine göre topladığı için tekil emirler değil, **seviyedeki toplam miktar değişimi** bildirilir. Bir seviyedeki azalmanın işlemle açıklanamayan kısmı iptal olarak değerlendirilir. API her tarafta en fazla 30 seviye döndürdüğü için görünür aralığın dışından kayan seviyeler yanlış bildirim üretmesin diye filtrelenir.

Bot ilk açıldığında mevcut durumu yalnızca "görüldü" olarak kaydeder; bildirimler açılıştan sonraki değişikliklerle başlar.

## Dosyalar

| Dosya | İçerik |
|-------|--------|
| `bot.py` | Telegram komutları, abone yönetimi, sorgulama döngüleri, order book karşılaştırması |
| `nonlogs_api.py` | nonlogs.io API istemcisi |
| `messages.py` | Bildirim metinleri (HTML) |
