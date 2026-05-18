#!/usr/bin/env python3
"""
Daily dashboard data generator.
Fetches live prices, calculates portfolio values, and updates docs/data.json.
Run via GitHub Actions every day, or manually: python generate_dashboard.py
"""

import json
import os
import requests
from datetime import datetime, timezone

# ── Portfolio (mirrors asparuh_invest_bot_v4.py) ──────────────────────────────
PORTFOLIO = {
    "BTC-USD": {"name": "Bitcoin (BTC)",          "currency": "CRYPTO", "invested": 68.48,  "shares": 0.00091802,    "cgId": "bitcoin"},
    "ETC-USD": {"name": "Ethereum Classic (ETC)", "currency": "CRYPTO", "invested": 58.03,  "shares": 6.72696447,    "cgId": "ethereum-classic"},
    "FLR-USD": {"name": "Flare (FLR)",            "currency": "CRYPTO", "invested": 0.10,   "shares": 14.8080141,    "cgId": "flare-networks"},
    "EXI2.DE": {"name": "EXI2 ETF",              "currency": "EUR",    "invested": 50.00,  "shares": 0.477463713},
    "MRVL":    {"name": "Marvell (MRVL)",         "currency": "USD",    "invested": 37.04,  "shares": 0.258598397},
    "DFEN.DE": {"name": "VanEck Defense ETF",     "currency": "EUR",    "invested": 51.00,  "shares": 0.891265597},
    "ROBO":    {"name": "Robo-Advisor",           "currency": "EUR",    "invested": 23.42,  "shares": 1.0},
}

DEFAULT_PRICES = {"EXI2.DE": 104.95, "MRVL": 157.20, "DFEN.DE": 55.715, "ROBO": 23.37}
TOTAL_INVESTED = sum(a["invested"] for a in PORTFOLIO.values())
DATA_FILE      = os.path.join(os.path.dirname(__file__), "docs", "data.json")
MAX_HISTORY    = 30


def fetch_coingecko():
    ids = "bitcoin,ethereum-classic,flare-networks"
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=eur,usd"
    r   = requests.get(url, timeout=12)
    r.raise_for_status()
    return r.json()


def fetch_eurusd():
    r    = requests.get("https://api.kraken.com/0/public/Ticker?pair=EURUSD", timeout=10)
    data = r.json()
    if not data.get("error"):
        pair = list(data["result"].keys())[0]
        return round(float(data["result"][pair]["c"][0]), 4)
    return 1.08


def get_price_eur(ticker, cg, eur_usd, manual):
    a = PORTFOLIO[ticker]
    if "cgId" in a:
        eur = cg.get(a["cgId"], {}).get("eur")
        if eur:
            return float(eur)
    mp = manual.get(ticker, DEFAULT_PRICES.get(ticker))
    if mp:
        return mp / eur_usd if a["currency"] == "USD" else mp
    return None


def load_existing():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": []}


def main():
    print("Fetching prices…")
    cg      = fetch_coingecko()
    eur_usd = fetch_eurusd()
    manual  = DEFAULT_PRICES.copy()

    print(f"EUR/USD: {eur_usd}")

    total_current = 0.0
    prices_out    = {}

    for ticker, asset in PORTFOLIO.items():
        peur = get_price_eur(ticker, cg, eur_usd, manual)
        if peur is None:
            print(f"  WARNING: no price for {ticker}")
            continue
        val   = asset["shares"] * peur
        total_current += val
        prices_out[ticker] = round(peur, 6)
        print(f"  {ticker}: €{peur:.4f} → €{val:.2f}")

    pnl     = total_current - TOTAL_INVESTED
    pnl_pct = (pnl / TOTAL_INVESTED) * 100 if TOTAL_INVESTED else 0
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Load existing data and append to history
    existing = load_existing()
    history  = existing.get("history", [])

    # Replace today's entry if it exists, otherwise append
    history = [h for h in history if h.get("date") != today]
    history.append({
        "date":  today,
        "total": round(total_current, 2),
        "pnl":   round(pnl, 2),
        "pct":   round(pnl_pct, 2),
    })
    history = sorted(history, key=lambda h: h["date"])[-MAX_HISTORY:]

    data = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "eurUsd":      eur_usd,
        "prices":      prices_out,
        "portfolio": {
            "totalInvested": round(TOTAL_INVESTED, 2),
            "totalCurrent":  round(total_current, 2),
            "pnl":           round(pnl, 2),
            "pnlPct":        round(pnl_pct, 2),
        },
        "history": history,
    }

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nPortfolio: €{total_current:.2f} (P&L {pnl:+.2f} / {pnl_pct:+.1f}%)")
    print(f"data.json written → {DATA_FILE}")


if __name__ == "__main__":
    main()
