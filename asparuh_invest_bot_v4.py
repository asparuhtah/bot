#!/usr/bin/env python3
"""
Asparuh's Investment BOT v4
============================
- Крипто цени от CoinGecko (работи на PythonAnywhere free)
- EUR/USD от Kraken
- Акции/ETF цени с /setprice команда
- P&L изчисления с реални EUR суми
- Дневен CSV запис в 23:00
- Команди: /prices /pnl /alerts /setprice /history /morning /help

Инсталация:
    pip install requests schedule

Стартиране:
    python asparuh_invest_bot_v4.py
"""

import requests
import schedule
import time
import csv
import os
from datetime import datetime

# ─── КОНФИГУРАЦИЯ ─────────────────────────────────────────────────────────────
BOT_TOKEN = "8635032958:AAEgK2HJT8f2odzS2cZ3d0VVFT9P5sRTftw"
CHAT_ID   = "6087726724"
CSV_FILE  = "portfolio_history.csv"

# ─── ПОРТФОЛИО — РЕАЛНИ СУМИ ОТ REVOLUT ──────────────────────────────────────
PORTFOLIO = {
    "BTC-USD": {
        "name": "Bitcoin (BTC)",
        "currency": "CRYPTO",
        "invested_eur": 68.48,
        "shares": 0.00091802,
    },
    "ETC-USD": {
        "name": "Ethereum Classic (ETC)",
        "currency": "CRYPTO",
        "invested_eur": 58.03,
        "shares": 6.72696447,
    },
    "FLR-USD": {
        "name": "Flare (FLR)",
        "currency": "CRYPTO",
        "invested_eur": 0.10,
        "shares": 14.8080141,
    },
    "EXI2.DE": {
        "name": "EXI2 ETF",
        "currency": "EUR",
        "invested_eur": 50.00,
        "shares": 0.477463713,
    },
    "MRVL": {
        "name": "Marvell (MRVL)",
        "currency": "USD",
        "invested_eur": 37.04,
        "shares": 0.258598397,
    },
    "DFEN.DE": {
        "name": "VanEck Defense ETF",
        "currency": "EUR",
        "invested_eur": 51.00,
        "shares": 0.891265597,
    },
    "ROBO": {
        "name": "Robo-Advisor",
        "currency": "EUR",
        "invested_eur": 23.42,
        "shares": 1.0,
    },
}

# ─── COINGECKO MAP ────────────────────────────────────────────────────────────
COINGECKO_MAP = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "ETC-USD": "ethereum-classic",
    "FLR-USD": "flare-networks",
}

# ─── РЪЧНИ ЦЕНИ (акции/ETF) — обновяват се с /setprice ───────────────────────
MANUAL_PRICES = {
    "EXI2.DE": 104.95,
    "MRVL":    157.20,
    "DFEN.DE": 55.715,
    "ROBO":    23.37,
}

# ─── ЦЕНОВИ АЛЕРТИ ────────────────────────────────────────────────────────────
ALERTS = {
    "MRVL":    {"buy": 140,   "warn": 190,   "name": "Marvell Technology", "curr": "$"},
    "DFEN.DE": {"buy": 54,    "warn": 65,    "name": "VanEck Defense ETF", "curr": "€"},
    "BTC-USD": {"buy": 60000, "warn": 95000, "name": "Bitcoin",            "curr": "$"},
    "EXI2.DE": {"buy": 95,    "warn": 115,   "name": "EXI2 ETF",           "curr": "€"},
    "ETC-USD": {"buy": 6.0,   "warn": 12.0,  "name": "Ethereum Classic",   "curr": "$"},
}

_alert_state    = {}
_last_update_id = None
_cg_cache       = {}

# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
def send_message(text: str) -> bool:
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Telegram грешка: {e}")
        return False

def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json().get("result", [])
    except:
        return []

# ─── ЦЕНИ ─────────────────────────────────────────────────────────────────────
def get_coingecko_prices() -> dict:
    """Всички крипто цени от CoinGecko — EUR и USD."""
    global _cg_cache
    try:
        ids = ",".join(COINGECKO_MAP.values())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur,usd"
        r   = requests.get(url, timeout=10)
        if r.status_code == 200:
            _cg_cache = r.json()
            return _cg_cache
    except Exception as e:
        print(f"CoinGecko грешка: {e}")
    return _cg_cache

def get_eurusd() -> float:
    """EUR/USD от Kraken."""
    try:
        url  = "https://api.kraken.com/0/public/Ticker?pair=EURUSD"
        r    = requests.get(url, timeout=10)
        data = r.json()
        if not data.get("error") or not data["error"]:
            result = data.get("result", {})
            if result:
                pair  = list(result.keys())[0]
                return round(float(result[pair]["c"][0]), 4)
    except Exception as e:
        print(f"Kraken грешка: {e}")
    return 1.08

def get_price_eur(ticker: str, cg_prices: dict = None) -> float | None:
    """Връща цена в EUR."""
    # Крипто — от CoinGecko директно в EUR
    if ticker in COINGECKO_MAP:
        prices = cg_prices or get_coingecko_prices()
        cg_id  = COINGECKO_MAP[ticker]
        eur    = prices.get(cg_id, {}).get("eur")
        if eur:
            return round(float(eur), 6)
    # Акции/ETF — ръчна цена
    if ticker in MANUAL_PRICES and MANUAL_PRICES[ticker] > 0:
        return MANUAL_PRICES[ticker]
    return None

def get_price_usd(ticker: str, cg_prices: dict = None) -> float | None:
    """Връща цена в USD (за показване)."""
    if ticker in COINGECKO_MAP:
        prices = cg_prices or get_coingecko_prices()
        cg_id  = COINGECKO_MAP[ticker]
        usd    = prices.get(cg_id, {}).get("usd")
        if usd:
            return round(float(usd), 4)
    return None

# ─── P&L ИЗЧИСЛЕНИЯ ───────────────────────────────────────────────────────────
def calc_portfolio() -> tuple[list, dict, float]:
    """Връща (results, cg_prices, eurusd)."""
    eurusd    = get_eurusd()
    cg_prices = get_coingecko_prices()
    results   = []

    for ticker, data in PORTFOLIO.items():
        name      = data["name"]
        invested  = data["invested_eur"]
        shares    = data["shares"]
        currency  = data["currency"]

        # Вземи цена в EUR
        price_eur = get_price_eur(ticker, cg_prices)
        if price_eur is None:
            print(f"⚠️ Няма цена за {ticker}")
            continue

        current_eur = round(shares * price_eur, 2)
        pnl         = round(current_eur - invested, 2)
        pnl_pct     = round(pnl / invested * 100, 2) if invested else 0

        # USD цена за показване
        price_usd = get_price_usd(ticker, cg_prices) if currency == "CRYPTO" else None
        price_display = price_usd or (MANUAL_PRICES.get(ticker, 0))

        results.append({
            "name":          name,
            "ticker":        ticker,
            "currency":      currency,
            "invested":      invested,
            "current":       current_eur,
            "price_eur":     price_eur,
            "price_display": price_display,
            "pnl":           pnl,
            "pnl_pct":       pnl_pct,
        })

    return results, cg_prices, eurusd

def status_emoji(pct: float) -> str:
    if pct >= 50:  return "🚀 Отлично!"
    if pct >= 20:  return "✅ Добре"
    if pct >= 0:   return "📈 На плюс"
    if pct >= -15: return "😐 Малка загуба"
    if pct >= -30: return "⚠️ Внимание"
    return "🚨 Прегледай стратегия"

# ─── CSV ЛОГВАНЕ ──────────────────────────────────────────────────────────────
CSV_COLUMNS = [
    "Дата", "Час",
    "BTC (€)", "ETC (€)", "FLR (€)",
    "EXI2 ETF (€)", "MRVL (€)", "VanEck DFEN (€)", "Robo-Advisor (€)",
    "Крипто Общо (€)", "Инвестиции Общо (€)", "Портфолио Общо (€)",
    "BTC цена ($)", "ETC цена ($)",
    "EXI2 цена (€)", "MRVL цена ($)", "DFEN цена (€)",
    "EUR/USD",
    "Дневна промяна (€)", "Дневна промяна (%)"
]

_prev_total = None

def log_to_csv(results: list, eurusd: float):
    global _prev_total

    date_str    = datetime.now().strftime("%d.%m.%Y")
    time_str    = datetime.now().strftime("%H:%M")
    file_exists = os.path.exists(CSV_FILE)

    by_ticker = {r["ticker"]: r for r in results}

    def v(t): return by_ticker.get(t, {}).get("current", 0)
    def p(t): return by_ticker.get(t, {}).get("price_display", "")

    btc  = v("BTC-USD"); etc  = v("ETC-USD"); flr  = v("FLR-USD")
    exi2 = v("EXI2.DE"); mrvl = v("MRVL");   dfen = v("DFEN.DE"); robo = v("ROBO")

    crypto_total = round(btc + etc + flr, 2)
    invest_total = round(exi2 + mrvl + dfen + robo, 2)
    grand_total  = round(crypto_total + invest_total, 2)

    daily_change     = round(grand_total - _prev_total, 2) if _prev_total else 0
    daily_change_pct = round(daily_change / _prev_total * 100, 2) if _prev_total else 0
    _prev_total      = grand_total

    row = [
        date_str, time_str,
        btc, etc, flr,
        exi2, mrvl, dfen, robo,
        crypto_total, invest_total, grand_total,
        p("BTC-USD"), p("ETC-USD"),
        p("EXI2.DE"), p("MRVL"), p("DFEN.DE"),
        eurusd, daily_change, daily_change_pct,
    ]

    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if not file_exists:
            w.writerow(CSV_COLUMNS)
        w.writerow(row)

    print(f"✅ CSV записан: {date_str} {time_str} | Общо: €{grand_total}")

# ─── КОМАНДИ ──────────────────────────────────────────────────────────────────
def cmd_pnl():
    results, _, eurusd = calc_portfolio()
    if not results:
        send_message("⚠️ Няма данни. Провери /setprice за акциите.")
        return

    msg  = f"💰 <b>P&L — Печалба/Загуба</b>\n"
    msg += f"💱 EUR/USD: {eurusd}\n"
    msg += "─" * 22 + "\n\n"

    total_inv = total_cur = 0
    for r in results:
        arrow   = "🟢" if r["pnl"] >= 0 else "🔴"
        pnl_str = f"+€{r['pnl']:.2f}" if r["pnl"] >= 0 else f"-€{abs(r['pnl']):.2f}"
        pct_str = f"{r['pnl_pct']:+.1f}%"

        if r["currency"] == "CRYPTO" and r["price_display"]:
            price_str = f"  ${r['price_display']:,.2f}\n"
        elif r["currency"] == "USD" and r["price_display"]:
            price_str = f"  ${r['price_display']:,.2f}\n"
        else:
            price_str = ""

        msg += f"{arrow} <b>{r['name']}</b>\n"
        msg += f"   €{r['invested']:.2f} → €{r['current']:.2f}{price_str}"
        msg += f"   {pnl_str} ({pct_str}) {status_emoji(r['pnl_pct'])}\n\n"
        total_inv += r["invested"]
        total_cur += r["current"]

    pnl     = total_cur - total_inv
    pnl_pct = (pnl / total_inv * 100) if total_inv else 0
    arrow   = "🟢" if pnl >= 0 else "🔴"
    pnl_str = f"+€{pnl:.2f}" if pnl >= 0 else f"-€{abs(pnl):.2f}"

    msg += "─" * 22 + "\n"
    msg += f"{arrow} <b>ОБЩО: €{total_inv:.2f} → €{total_cur:.2f}</b>\n"
    msg += f"   {pnl_str} ({pnl_pct:+.1f}%) {status_emoji(pnl_pct)}\n"
    msg += f"\n🕐 {datetime.now().strftime('%H:%M · %d.%m.%Y')}"
    send_message(msg)

def cmd_prices():
    results, cg_prices, eurusd = calc_portfolio()
    msg = f"📊 <b>Текущи цени</b>  💱 EUR/USD: {eurusd}\n" + "─" * 22 + "\n\n"

    msg += "<b>🪙 Крипто (CoinGecko live):</b>\n"
    for ticker, cg_id in COINGECKO_MAP.items():
        eur = cg_prices.get(cg_id, {}).get("eur", "н/д")
        usd = cg_prices.get(cg_id, {}).get("usd", "н/д")
        name = PORTFOLIO.get(ticker, {}).get("name", ticker)
        if eur != "н/д":
            msg += f"• {name}: €{eur:,.4f}  (${usd:,.2f})\n"
        else:
            msg += f"• {name}: н/д\n"

    msg += "\n<b>📈 Акции/ETF (обнови с /setprice):</b>\n"
    for ticker, price in MANUAL_PRICES.items():
        name = PORTFOLIO.get(ticker, {}).get("name", ticker)
        curr = "€" if ".DE" in ticker or ticker == "ROBO" else "$"
        msg += f"• {name}: {curr}{price}\n"

    msg += f"\n🕐 {datetime.now().strftime('%H:%M · %d.%m.%Y')}"
    send_message(msg)

def cmd_alerts():
    _, cg_prices, _ = calc_portfolio()
    msg = "🔔 <b>Ценови алерти</b>\n" + "─" * 22 + "\n\n"

    for ticker, data in ALERTS.items():
        curr     = data["curr"]
        buy_lvl  = data["buy"]
        warn_lvl = data["warn"]
        name     = data["name"]

        # Вземи USD цена за алертите
        if ticker in COINGECKO_MAP:
            cg_id = COINGECKO_MAP[ticker]
            price = cg_prices.get(cg_id, {}).get("usd")
        else:
            price = MANUAL_PRICES.get(ticker)

        if price is None:
            msg += f"⬜ <b>{name}</b> — въведи с /setprice\n\n"
            continue

        if price <= buy_lvl:
            status = f"🟢 КУПИ! {curr}{price:,.2f} ≤ {curr}{buy_lvl:,.0f}"
        elif price >= warn_lvl:
            status = f"🟡 ВНИМАНИЕ {curr}{price:,.2f} ≥ {curr}{warn_lvl:,.0f}"
        else:
            pct    = ((price - buy_lvl) / buy_lvl) * 100
            status = f"⬜ Неутрален {pct:+.1f}% до алерт ({curr}{buy_lvl:,.0f})"

        msg += f"<b>{name}</b>\n{status}\n\n"

    send_message(msg)

def cmd_setprice():
    msg  = "✏️ <b>Обнови цени на акции/ETF</b>\n\n"
    msg += "Формат:\n"
    msg += "<code>price EXI2.DE 106.50</code>\n"
    msg += "<code>price MRVL 162.30</code>\n"
    msg += "<code>price DFEN.DE 57.20</code>\n"
    msg += "<code>price ROBO 24.10</code>\n\n"
    msg += "<b>Текущи цени:</b>\n"
    for ticker, price in MANUAL_PRICES.items():
        name = PORTFOLIO.get(ticker, {}).get("name", ticker)
        curr = "€" if ".DE" in ticker or ticker == "ROBO" else "$"
        msg += f"• {name}: {curr}{price}\n"
    send_message(msg)

def cmd_history():
    if not os.path.exists(CSV_FILE):
        send_message("📭 Няма история още. Първото логване е в 23:00.")
        return

    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))

    if len(rows) <= 1:
        send_message("📭 Няма данни още.")
        return

    dates = sorted(set(r[0] for r in rows[1:] if r))[-7:]
    msg   = "📅 <b>История — последните дни</b>\n" + "─" * 22 + "\n\n"

    for date in dates:
        day_rows = [r for r in rows[1:] if r and r[0] == date]
        if not day_rows:
            continue
        last = day_rows[-1]  # последният запис за деня
        try:
            total   = float(last[11]) if last[11] else 0
            crypto  = float(last[8])  if last[8]  else 0
            invest  = float(last[9])  if last[9]  else 0
            change  = float(last[18]) if last[18] else 0
            chg_pct = float(last[19]) if last[19] else 0
            arrow   = "🟢" if change >= 0 else "🔴"
            chg_str = f"+€{change:.2f}" if change >= 0 else f"-€{abs(change):.2f}"
            msg    += f"{arrow} <b>{date}</b>: €{total:.2f} ({chg_str}, {chg_pct:+.1f}%)\n"
            msg    += f"   🪙 €{crypto:.2f}  📈 €{invest:.2f}\n\n"
        except:
            msg += f"• {date}: данни\n\n"

    send_message(msg)

def cmd_morning():
    _, cg_prices, eurusd = calc_portfolio()
    dow   = datetime.now().weekday()
    hour  = datetime.now().hour
    greet = "🌅 Добро утро" if hour < 12 else "🌞 Добър ден"

    msg  = f"{greet}, <b>Аспарух!</b>\n"
    msg += f"💱 EUR/USD: {eurusd}\n" + "─" * 22 + "\n\n"

    msg += "<b>🪙 Крипто:</b>\n"
    for ticker, cg_id in COINGECKO_MAP.items():
        usd  = cg_prices.get(cg_id, {}).get("usd")
        eur  = cg_prices.get(cg_id, {}).get("eur")
        name = PORTFOLIO.get(ticker, {}).get("name", ticker)
        if usd and eur:
            msg += f"• {name}: €{eur:,.2f}  (${usd:,.2f})\n"

    msg += "\n📅 "
    if dow == 0:
        msg += "Борсата отваря 16:30 ч.\nПровери MRVL и обнови: /setprice"
    elif dow >= 5:
        msg += "Борсата затворена — само крипто активно."
    else:
        msg += "Борсата работи 16:30–23:00 ч.\nОбнови цените: /setprice"

    msg += f"\n\n🕐 {datetime.now().strftime('%H:%M · %d.%m.%Y')}"
    send_message(msg)

def cmd_start():
    send_message(
        "👋 <b>Здравей Аспарух!</b>\n\n"
        "Команди:\n"
        "/prices — Текущи цени\n"
        "/pnl — Печалба/Загуба по актив\n"
        "/alerts — Ценови алерти\n"
        "/setprice — Обнови цени на акции\n"
        "/history — Последните 7 дни\n"
        "/morning — Сутрешен бриф\n"
        "/help — Тази помощ\n\n"
        "🤖 <b>Автоматично:</b>\n"
        "• 09:00 — Сутрешен бриф\n"
        "• 23:00 — Дневен CSV snapshot\n"
        "• На 30 мин — Ценови алерти\n\n"
        "💡 Крипто → CoinGecko live\n"
        "💡 Акции → /setprice"
    )

# ─── АВТОМАТИЧНИ АЛЕРТИ ───────────────────────────────────────────────────────
def check_price_alerts():
    _, cg_prices, _ = calc_portfolio()

    for ticker, data in ALERTS.items():
        curr     = data["curr"]
        name     = data["name"]
        buy_lvl  = data["buy"]
        warn_lvl = data["warn"]
        prev     = _alert_state.get(ticker, "neutral")

        if ticker in COINGECKO_MAP:
            cg_id = COINGECKO_MAP[ticker]
            price = cg_prices.get(cg_id, {}).get("usd")
        else:
            price = MANUAL_PRICES.get(ticker)

        if price is None:
            continue

        if price <= buy_lvl and prev != "buy":
            _alert_state[ticker] = "buy"
            send_message(
                f"🟢 <b>АЛЕРТ — КУПИ!</b>\n\n"
                f"<b>{name}</b> е на {curr}{price:,.2f}\n"
                f"Под алерт нивото {curr}{buy_lvl:,.0f}\n\n"
                f"💡 Провери /pnl преди да решиш!"
            )
        elif price >= warn_lvl and prev != "warn":
            _alert_state[ticker] = "warn"
            send_message(
                f"🟡 <b>АЛЕРТ — ВНИМАНИЕ!</b>\n\n"
                f"<b>{name}</b> е на {curr}{price:,.2f}\n"
                f"Близо до горното ниво {curr}{warn_lvl:,.0f}"
            )
        elif buy_lvl < price < warn_lvl:
            _alert_state[ticker] = "neutral"

# ─── ДНЕВЕН SNAPSHOT (23:00) ──────────────────────────────────────────────────
def daily_snapshot():
    print(f"📸 Дневен snapshot: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    results, _, eurusd = calc_portfolio()

    if not results:
        send_message("⚠️ Дневен snapshot: няма данни. Обнови цените с /setprice.")
        return

    log_to_csv(results, eurusd)

    by_ticker    = {r["ticker"]: r for r in results}
    def v(t): return by_ticker.get(t, {}).get("current", 0)

    btc  = v("BTC-USD"); etc  = v("ETC-USD"); flr  = v("FLR-USD")
    exi2 = v("EXI2.DE"); mrvl = v("MRVL");   dfen = v("DFEN.DE"); robo = v("ROBO")

    crypto_total = round(btc + etc + flr, 2)
    invest_total = round(exi2 + mrvl + dfen + robo, 2)
    grand_total  = round(crypto_total + invest_total, 2)
    total_inv    = sum(d["invested_eur"] for d in PORTFOLIO.values())
    total_pnl    = round(grand_total - total_inv, 2)
    total_pct    = round(total_pnl / total_inv * 100, 2) if total_inv else 0
    arrow        = "🟢" if total_pnl >= 0 else "🔴"
    pnl_str      = f"+€{total_pnl:.2f}" if total_pnl >= 0 else f"-€{abs(total_pnl):.2f}"

    msg  = f"📸 <b>Дневен отчет — {datetime.now().strftime('%d.%m.%Y')}</b>\n"
    msg += "─" * 22 + "\n\n"
    msg += f"🪙 BTC: €{btc:.2f}  ETC: €{etc:.2f}  FLR: €{flr:.3f}\n"
    msg += f"   <b>Крипто: €{crypto_total:.2f}</b>\n\n"
    msg += f"📈 EXI2: €{exi2:.2f}  MRVL: €{mrvl:.2f}\n"
    msg += f"   DFEN: €{dfen:.2f}  Robo: €{robo:.2f}\n"
    msg += f"   <b>Инвестиции: €{invest_total:.2f}</b>\n\n"
    msg += f"{'─'*22}\n"
    msg += f"{arrow} <b>ОБЩО: €{grand_total:.2f}</b>\n"
    msg += f"   Вложено: €{total_inv:.2f}\n"
    msg += f"   P&L: {pnl_str} ({total_pct:+.1f}%)\n"
    msg += f"✅ CSV записан · 💱 EUR/USD: {eurusd}"
    send_message(msg)

# ─── КОМАНДЕН ПРОЦЕСОР ────────────────────────────────────────────────────────
def process_commands():
    global _last_update_id

    offset  = (_last_update_id + 1) if _last_update_id else None
    updates = get_updates(offset=offset)

    for update in updates:
        _last_update_id = update.get("update_id")
        msg  = update.get("message", {})
        text = msg.get("text", "").strip()
        low  = text.lower()

        if low.startswith("price "):
            parts = text.split()
            if len(parts) == 3:
                ticker = parts[1].upper()
                try:
                    price = float(parts[2].replace(",", "."))
                    if ticker in MANUAL_PRICES:
                        MANUAL_PRICES[ticker] = price
                        send_message(f"✅ Обновено: <b>{ticker}</b> = {price}")
                    else:
                        send_message(f"❌ Непознат тикер: {ticker}\nДостъпни: {', '.join(MANUAL_PRICES.keys())}")
                except ValueError:
                    send_message("❌ Пример: <code>price MRVL 162.30</code>")
            else:
                send_message("❌ Формат: <code>price ТИКЕР ЦЕНА</code>")

        elif low in ["/start", "start"]:       cmd_start()
        elif low in ["/prices", "prices"]:     cmd_prices()
        elif low in ["/pnl", "pnl"]:           cmd_pnl()
        elif low in ["/alerts", "alerts"]:     cmd_alerts()
        elif low in ["/setprice", "setprice"]: cmd_setprice()
        elif low in ["/history", "history"]:   cmd_history()
        elif low in ["/morning", "morning"]:   cmd_morning()
        elif low in ["/help", "help"]:         cmd_start()

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 Asparuh's Investment BOT v4 стартира...")
    print(f"📱 Chat ID: {CHAT_ID}")
    print(f"📁 CSV: {CSV_FILE}")
    print("─" * 40)

    send_message(
        "🚀 <b>Бот v4 стартиран!</b>\n\n"
        "✅ Крипто → CoinGecko (работи!)\n"
        "✅ EUR/USD → Kraken\n"
        "✅ Акции → /setprice\n\n"
        "Напиши /prices за проверка!"
    )

    schedule.every().day.at("09:00").do(cmd_morning)
    schedule.every().day.at("23:00").do(daily_snapshot)
    schedule.every(30).minutes.do(check_price_alerts)
    schedule.every(3).seconds.do(process_commands)

    print("📅 Разписание активно.")
    print("✅ Бот работи. Ctrl+C за спиране.\n")

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            send_message("⛔ Ботът е спрян.")
            print("\n⛔ Спрян.")
            break
        except Exception as e:
            print(f"⚠️ Грешка: {e}")
            time.sleep(5)
