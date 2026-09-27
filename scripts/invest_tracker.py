#!/usr/bin/env python3
"""
Invest Tracker v6 — GitHub Actions edition
==========================================
Пуска се от .github/workflows/invest-bot.yml (на ~15 мин). Всеки run:

  1. Дърпа цени: крипто (CoinGecko), акции/ETF (Yahoo → Stooq), EUR/USD (Kraken → Yahoo → ECB).
     Ако източник падне, ползва последната известна цена и я маркира като stale.
  2. Първият run във всеки нов час добавя редове в docs/invest/prices_hourly.csv
     (файлът само расте; живее в git → нищо не се губи при рестарт).
  3. Преизгражда docs/invest/daily.csv (последната стойност за всеки ден),
     latest.json и latest.csv (за dashboard-а и Excel).
  4. Telegram: ценови алерти, рязко движение (±move_pct за ден), P&L прагове,
     сутрешен бриф, дневен отчет, седмично резюме.
  5. Commit + push с retry (при паралелни commit-и от други workflow-и).

Командите в Telegram се обработват от Cloudflare Worker (webhook) —
затова тук НЕ викаме getUpdates (Telegram не позволява и двете).

Конфигурация: docs/invest/portfolio.json   Състояние: docs/invest/state.json
Env: BOT_TOKEN, CHAT_ID (или ID_CHAT). Без BOT_TOKEN → само запис, без съобщения.
Локален тест: INVEST_DRY_RUN=1 python scripts/invest_tracker.py
"""

import csv
import json
import os
import random
import subprocess
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(ROOT, "docs", "invest")
CFG_FILE   = os.path.join(DATA_DIR, "portfolio.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
HOURLY_CSV = os.path.join(DATA_DIR, "prices_hourly.csv")
DAILY_CSV  = os.path.join(DATA_DIR, "daily.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")
LATEST_CSV  = os.path.join(DATA_DIR, "latest.csv")

SOFIA   = ZoneInfo("Europe/Sofia")
DRY_RUN = os.environ.get("INVEST_DRY_RUN") == "1"
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or "").strip()
CHAT_ID   = (os.environ.get("CHAT_ID") or os.environ.get("ID_CHAT") or "6087726724").strip()
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

HOURLY_COLS = ["ts", "date", "time", "asset", "name", "group", "price", "ccy", "price_eur",
               "qty", "value_eur", "invested_eur", "pnl_eur", "pnl_pct", "eurusd", "src"]
LATEST_COLS = ["asset", "name", "group", "price", "ccy", "price_eur", "qty", "value_eur",
               "invested_eur", "pnl_eur", "pnl_pct", "chg_day_pct", "updated", "src"]


def now_sofia() -> datetime:
    fake = os.environ.get("INVEST_FAKE_NOW")          # за тестове: 2026-09-27T23:05
    if fake:
        return datetime.fromisoformat(fake).replace(tzinfo=SOFIA)
    return datetime.now(SOFIA)


# ─── I/O ──────────────────────────────────────────────────────────────────────
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def fnum(x, nd=6):
    return None if x is None else round(float(x), nd)


# ─── ЦЕНИ ─────────────────────────────────────────────────────────────────────
def http_json(url, **kw):
    r = requests.get(url, headers=UA, timeout=15, **kw)
    r.raise_for_status()
    return r.json()


def fetch_coingecko(ids):
    if not ids:
        return {}
    url = ("https://api.coingecko.com/api/v3/simple/price?ids=" + ",".join(ids) +
           "&vs_currencies=eur,usd&include_24hr_change=true")
    for attempt in range(3):
        try:
            return http_json(url)
        except Exception as e:
            print(f"⚠️ CoinGecko опит {attempt + 1}: {e}")
            time.sleep(3 + attempt * 4)
    return {}


def fetch_yahoo(symbol):
    """→ (price, currency, prev_close) или None."""
    for host in ("query1", "query2"):
        try:
            d = http_json(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d")
            meta = d["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            if price:
                return float(price), meta.get("currency"), meta.get("chartPreviousClose")
        except Exception as e:
            print(f"⚠️ Yahoo {host} {symbol}: {e}")
    return None


def stooq_symbol(symbol):
    if symbol.endswith(".DE"):
        return symbol[:-3].lower() + ".de"
    if "=" in symbol or "." in symbol:
        return None
    return symbol.lower() + ".us"


def fetch_stooq(symbol):
    s = stooq_symbol(symbol)
    if not s:
        return None
    try:
        r = requests.get(f"https://stooq.com/q/l/?s={s}&f=sd2t2c&h&e=csv", headers=UA, timeout=15)
        rows = list(csv.DictReader(r.text.splitlines()))
        close = rows[0].get("Close") if rows else None
        if close and close not in ("N/D", ""):
            return float(close), None, None
    except Exception as e:
        print(f"⚠️ Stooq {symbol}: {e}")
    return None


def fetch_eurusd():
    try:
        d = http_json("https://api.kraken.com/0/public/Ticker?pair=EURUSD")
        if not d.get("error"):
            pair = next(iter(d["result"]))
            return float(d["result"][pair]["c"][0]), "kraken"
    except Exception as e:
        print(f"⚠️ Kraken: {e}")
    y = fetch_yahoo("EURUSD=X")
    if y:
        return y[0], "yahoo"
    try:
        d = http_json("https://api.frankfurter.app/latest?from=EUR&to=USD")
        return float(d["rates"]["USD"]), "ecb"
    except Exception as e:
        print(f"⚠️ Frankfurter: {e}")
    return None, None


def collect_prices(assets, state):
    """→ dict id -> {price, ccy, price_eur, src, stale}, eurusd"""
    last = state.setdefault("last_prices", {})
    eurusd, fx_src = fetch_eurusd()
    if eurusd is None:
        eurusd = state.get("last_eurusd") or 1.15
        fx_src = "stale"
        print(f"⚠️ EUR/USD недостъпен → последен известен {eurusd}")
    state["last_eurusd"] = eurusd

    cg_ids = [a["symbol"] for a in assets if a["source"] == "coingecko"]
    cg = fetch_coingecko(cg_ids)
    out = {}
    for a in assets:
        aid, src = a["id"], a["source"]
        got = None
        if src == "coingecko":
            row = cg.get(a["symbol"]) or {}
            if row.get("usd") and row.get("eur"):
                got = {"price": float(row["usd"]), "ccy": "USD", "price_eur": float(row["eur"]),
                       "src": "coingecko", "chg24": row.get("usd_24h_change")}
        elif src == "yahoo":
            y = fetch_yahoo(a["symbol"]) or fetch_stooq(a["symbol"])
            if y:
                price, ccy, _prev = y
                ccy = (ccy or a["ccy"]).upper()
                if ccy == "GBP":            # не очакваме, но да не гръмне
                    ccy = "EUR"
                peur = price / eurusd if ccy == "USD" else price
                got = {"price": price, "ccy": ccy, "price_eur": peur,
                       "src": "yahoo" if len(y) == 3 and y[1] else "stooq"}
        elif src == "manual":
            v = a.get("value_eur")
            if v is not None:
                got = {"price": float(v), "ccy": "EUR", "price_eur": float(v), "src": "manual"}

        if got:
            got["stale"] = False
            last[aid] = {"price": fnum(got["price"]), "ccy": got["ccy"],
                         "price_eur": fnum(got["price_eur"]), "src": got["src"]}
            last[aid]["at"] = now_sofia().isoformat(timespec="minutes")
        elif aid in last:
            got = dict(last[aid], src="stale", stale=True)
            print(f"⚠️ {aid}: няма свежа цена → последна от {last[aid].get('at')}")
        else:
            print(f"❌ {aid}: няма цена изобщо")
            continue
        out[aid] = got
    return out, eurusd, fx_src


# ─── ИЗЧИСЛЕНИЯ ───────────────────────────────────────────────────────────────
def build_rows(assets, prices):
    rows = []
    for a in assets:
        p = prices.get(a["id"])
        if not p:
            continue
        qty = 1.0 if a["source"] == "manual" else float(a.get("qty", 0))
        value = qty * p["price_eur"]
        inv = a.get("invested_eur")
        pnl = (value - inv) if inv is not None else None
        rows.append({
            "asset": a["id"], "name": a["name"], "group": a["group"],
            "price": fnum(p["price"]), "ccy": p["ccy"], "price_eur": fnum(p["price_eur"]),
            "qty": fnum(qty, 9), "value_eur": fnum(value, 2),
            "invested_eur": fnum(inv, 2), "pnl_eur": fnum(pnl, 2),
            "pnl_pct": fnum(pnl / inv * 100, 2) if (pnl is not None and inv) else None,
            "src": p["src"], "stale": p.get("stale", False), "chg24": p.get("chg24"),
        })
    return rows


def totals(rows):
    def s(key, pred=lambda r: True):
        return round(sum((r[key] or 0) for r in rows if pred(r)), 2)
    invested_rows = lambda r: r["invested_eur"] is not None
    t = {
        "crypto":   s("value_eur", lambda r: r["group"] == "crypto"),
        "stocks":   s("value_eur", lambda r: r["group"] == "stocks"),
        "cash":     s("value_eur", lambda r: r["group"] == "cash"),
        "invested": s("invested_eur", invested_rows),
        "value_invested": s("value_eur", invested_rows),
    }
    t["total"] = round(t["crypto"] + t["stocks"] + t["cash"], 2)
    t["pnl"] = round(t["value_invested"] - t["invested"], 2)
    t["pnl_pct"] = round(t["pnl"] / t["invested"] * 100, 2) if t["invested"] else 0.0
    return t


# ─── CSV ──────────────────────────────────────────────────────────────────────
def read_hourly():
    if not os.path.exists(HOURLY_CSV):
        return []
    with open(HOURLY_CSV, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_hourly(rows, eurusd, now):
    new_file = not os.path.exists(HOURLY_CSV)
    with open(HOURLY_CSV, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HOURLY_COLS, extrasaction="ignore", lineterminator="\n")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({**r, "ts": now.isoformat(timespec="minutes"), "date": now.strftime("%Y-%m-%d"),
                        "time": now.strftime("%H:%M"), "eurusd": round(eurusd, 4)})


def rebuild_daily(asset_ids):
    """daily.csv = последният запис за всеки ден (wide формат, удобен за графики/Excel)."""
    last = {}                                       # date -> asset -> row
    for r in read_hourly():
        last.setdefault(r["date"], {})[r["asset"]] = r
    cols = (["date", "time", "total_eur", "invested_eur", "pnl_eur", "pnl_pct",
             "crypto_eur", "stocks_eur", "cash_eur", "eurusd"] +
            [f"{a}_eur" for a in asset_ids] + [f"{a}_price" for a in asset_ids])
    out = []
    for date in sorted(last):
        day = last[date]
        g = lambda grp: sum(float(r["value_eur"] or 0) for r in day.values() if r["group"] == grp)
        inv = sum(float(r["invested_eur"]) for r in day.values() if r["invested_eur"])
        val_inv = sum(float(r["value_eur"] or 0) for r in day.values() if r["invested_eur"])
        pnl = val_inv - inv
        any_row = next(iter(day.values()))
        row = {"date": date, "time": max(r["time"] for r in day.values()),
               "total_eur": round(g("crypto") + g("stocks") + g("cash"), 2),
               "invested_eur": round(inv, 2), "pnl_eur": round(pnl, 2),
               "pnl_pct": round(pnl / inv * 100, 2) if inv else 0,
               "crypto_eur": round(g("crypto"), 2), "stocks_eur": round(g("stocks"), 2),
               "cash_eur": round(g("cash"), 2), "eurusd": any_row["eurusd"]}
        for a in asset_ids:
            r = day.get(a)
            row[f"{a}_eur"] = r["value_eur"] if r else ""
            row[f"{a}_price"] = r["price"] if r else ""
        out.append(row)
    with open(DAILY_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    return out


def prev_day_prices(daily, today):
    """Цени от предишния ден (за % дневна промяна)."""
    prev = [d for d in daily if d["date"] < today]
    return prev[-1] if prev else None


# ─── TELEGRAM ─────────────────────────────────────────────────────────────────
def send(text):
    if DRY_RUN or not BOT_TOKEN:
        print("── [TG не е изпратено] ──\n" + text + "\n──")
        return True
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=15)
        if r.status_code != 200:
            print(f"❌ sendMessage {r.status_code}: {r.text[:300]}")
        return r.status_code == 200
    except Exception as e:
        print(f"❌ Telegram: {e}")
        return False


def eur(x):
    return f"€{x:,.2f}".replace(",", " ")


def signed(x, suffix=""):
    return f"{'+' if x >= 0 else '−'}{abs(x):,.2f}{suffix}".replace(",", " ")


def status_text(pct):
    if pct is None: return ""
    if pct >= 50:  return "🚀"
    if pct >= 20:  return "✅"
    if pct >= 0:   return "📈"
    if pct >= -15: return "😐"
    if pct >= -30: return "⚠️"
    return "🚨"


def fmt_price(p, ccy):
    sym = "$" if ccy == "USD" else "€"
    return f"{sym}{p:,.4f}" if p < 1 else f"{sym}{p:,.2f}"


def portfolio_msg(title, rows, t, eurusd, now, day_ref=None):
    lines = [f"<b>{title}</b>", f"🕐 {now:%d.%m.%Y %H:%M} · 💱 EUR/USD {eurusd:.4f}", ""]
    for grp, label in (("crypto", "🪙 Крипто"), ("stocks", "📈 Инвестиции"), ("cash", "💶 Кеш")):
        g = [r for r in rows if r["group"] == grp]
        if not g:
            continue
        lines.append(f"<b>{label}: {eur(sum(r['value_eur'] for r in g))}</b>")
        for r in g:
            s = f"• {r['name']}: {eur(r['value_eur'])}"
            if r["pnl_pct"] is not None:
                s += f"  ({signed(r['pnl_pct'], '%')}) {status_text(r['pnl_pct'])}"
            if day_ref and day_ref.get(f"{r['asset']}_eur"):
                d = r["value_eur"] - float(day_ref[f"{r['asset']}_eur"])
                if abs(d) >= 0.01:
                    s += f"  · ден {signed(d)}"
            if r["stale"]:
                s += " ⏳"
            lines.append(s)
        lines.append("")
    arrow = "🟢" if t["pnl"] >= 0 else "🔴"
    lines.append(f"{arrow} <b>Инвестирано {eur(t['invested'])} → {eur(t['value_invested'])}</b>")
    lines.append(f"   P&L {signed(t['pnl'])} € ({signed(t['pnl_pct'], '%')})")
    lines.append(f"💼 Общо с кеш: <b>{eur(t['total'])}</b>")
    if any(r["stale"] for r in rows):
        lines.append("\n⏳ = източникът не отговори, показана е последната известна цена")
    return "\n".join(lines)


# ─── АЛЕРТИ ───────────────────────────────────────────────────────────────────
def check_alerts(assets, rows, t, daily, cfg, state, now):
    st = state.setdefault("alert_state", {})
    notify = cfg.get("notify", {})
    today = now.strftime("%Y-%m-%d")
    by_id = {r["asset"]: r for r in rows}
    msgs = []

    # 1) ценови нива (в родната валута)
    for a in assets:
        lv, r = a.get("alert"), by_id.get(a["id"])
        if not lv or not r or r["stale"]:
            continue
        price, prev = r["price"], st.get(a["id"], "neutral")
        if price <= lv["buy"]:
            zone = "buy"
        elif price >= lv["warn"]:
            zone = "warn"
        else:
            zone = "neutral"
        if zone != prev:
            if zone == "buy":
                msgs.append(f"🟢 <b>{a['name']}</b> падна до {fmt_price(price, r['ccy'])} "
                            f"(≤ ниво за покупка {fmt_price(lv['buy'], r['ccy'])})")
            elif zone == "warn":
                msgs.append(f"🟡 <b>{a['name']}</b> достигна {fmt_price(price, r['ccy'])} "
                            f"(≥ горно ниво {fmt_price(lv['warn'], r['ccy'])}) — помисли за частично теглене")
            elif prev in ("buy", "warn"):
                msgs.append(f"⬜ <b>{a['name']}</b> се върна в неутралната зона: {fmt_price(price, r['ccy'])}")
            st[a["id"]] = zone

    # 2) рязко движение спрямо вчерашното затваряне (веднъж на ден на актив)
    move = float(notify.get("move_pct", 5))
    ref = prev_day_prices(daily, today)
    moved = state.setdefault("move_sent", {})
    if ref:
        for r in rows:
            if r["group"] == "cash" or r["stale"]:
                continue
            p0 = ref.get(f"{r['asset']}_price")
            if not p0:
                continue
            chg = (r["price"] - float(p0)) / float(p0) * 100
            key = f"{r['asset']}:{'up' if chg > 0 else 'down'}"
            if abs(chg) >= move and moved.get(key) != today:
                moved[key] = today
                msgs.append(f"{'🚀' if chg > 0 else '📉'} <b>{r['name']}</b> {signed(chg, '%')} за деня "
                            f"→ {fmt_price(r['price'], r['ccy'])} (стойност {eur(r['value_eur'])})")

    # 3) P&L прагове на целия портфейл (свързани с правилата за теглене)
    levels = sorted(notify.get("pnl_levels_pct", [-20, -10, 0, 10, 20]))
    band = sum(1 for lv in levels if t["pnl_pct"] >= lv)
    prev_band = state.get("pnl_band")
    if prev_band is not None and band != prev_band:
        up = band > prev_band
        crossed = levels[band - 1] if up else levels[band]
        hint = ""
        if up and crossed >= 20:
            hint = "\n🟢 Над +20% — „зелена светлина“ за теглене, ако имаш конкретна нужда и е под 25% от портфейла."
        elif not up and crossed <= 0:
            hint = "\n🔴 На загуба — по правилата НЕ теглиш. Не продавай от паника."
        msgs.append(f"{'📈' if up else '📉'} <b>Портфейлът {'премина над' if up else 'падна под'} "
                    f"{signed(crossed, '%')}</b>\nP&L: {signed(t['pnl'])} € ({signed(t['pnl_pct'], '%')}){hint}")
    state["pnl_band"] = band

    if msgs:
        send("🔔 <b>Алерт</b>\n\n" + "\n\n".join(msgs))
    return bool(msgs)


# ─── РАЗПИСАНИЕ ───────────────────────────────────────────────────────────────
def scheduled_messages(rows, t, eurusd, daily, cfg, state, now):
    n = cfg.get("notify", {})
    today = now.strftime("%Y-%m-%d")
    ref = prev_day_prices(daily, today)

    # сутрешен бриф — първият run в прозореца [morning_hour, +3ч)
    mh = int(n.get("morning_hour", 9))
    if mh <= now.hour < mh + 3 and state.get("last_morning") != today:
        send(portfolio_msg("🌅 Добро утро, Аспарух!", rows, t, eurusd, now, ref))
        state["last_morning"] = today

    # дневен отчет — след daily_report_hour (или до 02:00 за вчера, ако cron-ът е закъснял)
    rh = int(n.get("daily_report_hour", 23))
    report_day = today if now.hour >= rh else (
        (now - timedelta(days=1)).strftime("%Y-%m-%d") if now.hour < 2 else None)
    if report_day and state.get("last_daily_report", "") < report_day:
        send(portfolio_msg(f"📸 Дневен отчет — {report_day[8:10]}.{report_day[5:7]}", rows, t, eurusd, now, ref)
             + "\n\n💾 Записано в daily.csv")
        state["last_daily_report"] = report_day

    # седмично резюме
    wd, wh = int(n.get("weekly_weekday", 6)), int(n.get("weekly_hour", 20))
    iso_week = now.strftime("%G-W%V")
    if now.weekday() == wd and now.hour >= wh and state.get("last_weekly") != iso_week:
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        base = [d for d in daily if d["date"] <= week_ago]
        base = base[-1] if base else (daily[0] if daily else None)
        msg = portfolio_msg("🗓 Седмично резюме", rows, t, eurusd, now)
        if base and base["date"] < today:
            dv = t["total"] - float(base["total_eur"])
            msg += f"\n\n📊 За седмицата (от {base['date']}): {signed(dv)} €"
        send(msg)
        state["last_weekly"] = iso_week


# ─── LATEST (за dashboard и Excel) ────────────────────────────────────────────
def write_latest(rows, t, eurusd, fx_src, daily, now):
    ref = prev_day_prices(daily, now.strftime("%Y-%m-%d"))
    for r in rows:
        p0 = ref.get(f"{r['asset']}_price") if ref else None
        r["chg_day_pct"] = round((r["price"] - float(p0)) / float(p0) * 100, 2) if p0 else None
        r["updated"] = now.isoformat(timespec="minutes")
    save_json(LATEST_JSON, {
        "updated": now.isoformat(timespec="minutes"),
        "eurusd": round(eurusd, 4), "eurusd_src": fx_src,
        "totals": t,
        "assets": [{k: r.get(k) for k in LATEST_COLS + ["stale"]} for r in rows],
    })
    with open(LATEST_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LATEST_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ─── GIT ──────────────────────────────────────────────────────────────────────
def sh(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT)
    out = (p.stdout + p.stderr).strip()
    print(f"$ {cmd}" + (f"\n{out}" if out else ""))
    return p.returncode


def git_sync(now):
    if not os.environ.get("GITHUB_ACTIONS") or DRY_RUN:
        print("ℹ️ Не сме в GitHub Actions — пропускам git push.")
        return
    sh('git config user.name "github-actions[bot]"')
    sh('git config user.email "github-actions[bot]@users.noreply.github.com"')
    sh("git add docs/invest")
    if sh("git diff --staged --quiet") == 0:
        print("ℹ️ Няма промени.")
        return
    sh(f'git commit -m "invest: {now:%Y-%m-%d %H:%M} Sofia"')
    for i in range(1, 7):
        if sh("git push") == 0:
            print(f"✅ Push (опит {i})")
            return
        # чужд commit междувременно (garmin/dashboard) → rebase нашия отгоре
        sh("git pull --rebase origin main") == 0 or sh("git rebase --abort")
        time.sleep(random.randint(2, 6))
    raise SystemExit("❌ Push не успя след 6 опита")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    now = now_sofia()
    cfg = load_json(CFG_FILE, None)
    if not cfg:
        raise SystemExit(f"Няма {CFG_FILE}")
    state = load_json(STATE_FILE, {})
    assets = cfg["assets"]
    ids = [a["id"] for a in assets]
    print(f"🤖 Invest Tracker v6 · {now:%Y-%m-%d %H:%M} Sofia · dry={DRY_RUN} · tg={'да' if BOT_TOKEN else 'не'}")

    prices, eurusd, fx_src = collect_prices(assets, state)
    rows = build_rows(assets, prices)
    if not rows:
        raise SystemExit("❌ Нито една цена — нищо не записвам")
    t = totals(rows)
    for r in rows:
        print(f"  {r['asset']:<9} {r['price']:>12} {r['ccy']}  → €{r['value_eur']:>8}  [{r['src']}]")
    print(f"  ОБЩО €{t['total']} · инвестирано €{t['invested']} → €{t['value_invested']} · P&L {t['pnl']} ({t['pnl_pct']}%)")

    # snapshot на смисленото състояние (без кеша с цени), за да commit-ваме само при промяна
    core = lambda s: json.dumps({k: v for k, v in s.items() if k != "last_prices"}, sort_keys=True)
    before = core(state)

    hour_key = now.strftime("%Y-%m-%d %H")
    logged = state.get("last_hour_logged") != hour_key
    if logged:
        append_hourly(rows, eurusd, now)
        state["last_hour_logged"] = hour_key
        print(f"💾 Нов часов запис: {hour_key}")

    daily = rebuild_daily(ids)
    check_alerts(assets, rows, t, daily, cfg, state, now)
    scheduled_messages(rows, t, eurusd, daily, cfg, state, now)

    if logged or core(state) != before or not os.path.exists(LATEST_JSON):
        write_latest(rows, t, eurusd, fx_src, daily, now)
        save_json(STATE_FILE, state)
        git_sync(now)
    else:
        print("ℹ️ Същият час, без алерти — нищо за commit.")
    print("✅ Готово")


if __name__ == "__main__":
    main()
