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

# ── Портфейлът идва от един източник: docs/invest/portfolio.json (+ latest.json от бота) ──
ROOT        = os.path.dirname(os.path.abspath(__file__))
CFG_FILE    = os.path.join(ROOT, "docs", "invest", "portfolio.json")
LATEST_FILE = os.path.join(ROOT, "docs", "invest", "latest.json")
DATA_FILE   = os.path.join(ROOT, "docs", "data.json")
MAX_HISTORY = 30


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def open_assets():
    """Само активните позиции (closed=true и кешът отпадат)."""
    cfg = load_json(CFG_FILE, {"assets": []})
    return [a for a in cfg["assets"] if not a.get("closed") and a.get("group") != "cash"]


def fetch_news():
    """Новини за портфейлните активи: Yahoo Finance RSS (акции) + CoinDesk (крипто).
    Връща списък [{title, link, date, source, tickers}] — най-новите 14."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    assets = open_assets()
    stocks = [a["symbol"] for a in assets if a.get("source") == "yahoo"]
    crypto = [a["id"] for a in assets if a.get("group") == "crypto"]
    feeds = []
    if stocks:
        feeds.append(("Yahoo Finance", [x.split(".")[0] for x in stocks],
                      "https://feeds.finance.yahoo.com/rss/2.0/headline?s=" + ",".join(stocks)
                      + "&region=US&lang=en-US"))
    if crypto:
        feeds.append(("CoinDesk", crypto, "https://www.coindesk.com/arc/outboundfeeds/rss/"))
    items = []
    for source, tickers, url in feeds:
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link  = (it.findtext("link") or "").strip()
                pub   = (it.findtext("pubDate") or "").strip()
                try:
                    date = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
                except Exception:
                    date = pub[:16]
                if title and link:
                    items.append({"title": title, "link": link, "date": date,
                                  "source": source, "tickers": tickers})
        except Exception as e:
            print(f"  news WARNING ({source}): {e}")
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return items[:14]


def load_existing():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": []}


def main():
    """Стойностите се вземат от latest.json на Invest Tracker (бота) — същите цени и позиции."""
    latest = load_json(LATEST_FILE, {})
    ids = {a["id"] for a in open_assets()}
    rows = [r for r in latest.get("assets", []) if r["asset"] in ids]
    if not rows:
        print("⚠️ latest.json липсва или е празен — пускам без нов запис")
        return
    eur_usd = latest.get("eurusd")
    prices_out = {r["asset"]: r["price_eur"] for r in rows}
    total_current = sum(r["value_eur"] or 0 for r in rows)
    total_invested = sum(r["invested_eur"] or 0 for r in rows if r.get("invested_eur") is not None)
    for r in rows:
        print(f"  {r['asset']}: €{r['price_eur']} → €{r['value_eur']}")
    pnl     = total_current - total_invested
    pnl_pct = (pnl / total_invested) * 100 if total_invested else 0
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    TOTAL_INVESTED = total_invested

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
        "news":    fetch_news(),
    }

    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nPortfolio: €{total_current:.2f} (P&L {pnl:+.2f} / {pnl_pct:+.1f}%)")
    print(f"data.json written → {DATA_FILE}")


if __name__ == "__main__":
    main()
