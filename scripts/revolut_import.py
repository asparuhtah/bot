#!/usr/bin/env python3
"""
Revolut import — чете извлеченията на Revolut и обновява docs/invest/portfolio.json
================================================================================
Поддържани файлове (CSV, експорт от приложението):
  • „trading-account-statement_….csv“ — пълен списък сделки (BUY/SELL, DIVIDEND,
    CASH TOP-UP). От него се смятат ТОЧНИТЕ позиции: qty, вложено в EUR
    (по курса от деня на сделката, метод „средна цена“), кеш в брокерската сметка.
  • Brokerage „Profit and loss statement“ — секции „Income from Sells“ и
    „Other income & fees“ (продажби и дивиденти).
  • Crypto „tax / P&L statement“ — „Crypto Summaries“ (продажби, разходи, такси,
    нетна печалба, Learn & Earn, Staking).

Какво записва в portfolio.json (САМО ЧИСЛА — без име, сметка, IBAN):
  • realized[]  — продажби (по сделка за акции, годишно обобщение за крипто)
  • income[]    — дивиденти, Learn & Earn, staking
  • при --positions (само с trading-account-statement): презаписва qty и
    invested_eur на акциите/ETF-ите и кеша в брокерската сметка (CASH), и
    слага positions_as_of = датата на последната сделка.
  • при --apply-sells: намалява qty и invested_eur на продадените позиции
    пропорционално на продаденото количество — само за продажби СЛЕД
    positions_as_of (датата, към която qty в portfolio.json е сверено с Revolut).

Употреба:
  python scripts/revolut_import.py файл1.csv [файл2.csv …]            # само показва
  python scripts/revolut_import.py файл1.csv … --write                 # записва
  python scripts/revolut_import.py файл1.csv … --write --apply-sells   # + коригира позиции
  python scripts/revolut_import.py trading-account-statement.csv --write --positions   # точни позиции

Импортът е идемпотентен: повторно пускане на същия файл не дублира редове.
⚠️ Repo-то е публично — не commit-вай самите извлечения (statements/ е в .gitignore).
"""

import csv
import io
import json
import os
import re
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_FILE = os.path.join(ROOT, "docs", "invest", "portfolio.json")
DAILY_CSV = os.path.join(ROOT, "docs", "invest", "daily.csv")

# '€' (E2 82 AC), прочетено като GBK/cp1252 → тези боклуци
MOJIBAKE = {"鈧�": "€", "鈧": "€", "â‚¬": "€", "�": ""}


# ─── ЧЕТЕНЕ ───────────────────────────────────────────────────────────────────
def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    for bad, good in MOJIBAKE.items():
        txt = txt.replace(bad, good)
    return txt


def num(s):
    """'€111.70' / '-$66.58' / '0.14' / '1,234.5' / '' → float или None."""
    if s is None:
        return None
    s = str(s).strip().replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-") or s.startswith("(")
    s = re.sub(r"[^\d.,]", "", s)
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def rows_of(txt):
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(txt))]


def nonempty(r):
    return [c for c in r if c != ""]


# ─── EUR/USD за датата (от daily.csv на бота) ─────────────────────────────────
def fx_table():
    t = {}
    try:
        with open(DAILY_CSV, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("eurusd"):
                    t[r["date"]] = float(r["eurusd"])
    except FileNotFoundError:
        pass
    return t


def to_eur(amount, ccy, day, fx):
    if amount is None:
        return None
    if (ccy or "EUR").upper() == "EUR":
        return round(amount, 2)
    if ccy.upper() == "USD":
        rate = fx.get(day) or next((fx[d] for d in sorted(fx, reverse=True) if d <= day), None) \
            or (fx[max(fx)] if fx else 1.10)
        return round(amount / rate, 2)
    return None


# ─── ПАРСЕРИ ──────────────────────────────────────────────────────────────────
def parse_brokerage(rows, fx):
    sells, income, section, header = [], [], None, None
    for r in rows:
        ne = nonempty(r)
        if not ne:
            continue
        head = ne[0]
        if len(ne) == 1 and head in ("Income from Sells", "Other income & fees"):
            section, header = head, None
            continue
        if section and header is None and "Symbol" in r:
            header = r
            continue
        if not section or not header:
            continue
        if head in ("Income from Sells", "Other income & fees") or head.startswith("Summary"):
            section, header = None, None
            continue
        d = dict(zip(header, r))
        if section == "Income from Sells" and d.get("Date sold"):
            ccy = d.get("Currency", "EUR")
            day = d["Date sold"]
            cost, gross, pnl = num(d.get("Cost basis")), num(d.get("Gross proceeds")), num(d.get("Gross PnL"))
            sells.append({
                "date": day, "asset": d.get("Symbol"), "isin": d.get("ISIN"), "type": "sell",
                "date_acquired": d.get("Date acquired"), "qty": num(d.get("Quantity")),
                "ccy": ccy, "cost": cost, "proceeds": gross, "pnl": pnl,
                "cost_eur": to_eur(cost, ccy, day, fx), "proceeds_eur": to_eur(gross, ccy, day, fx),
                "pnl_eur": to_eur(pnl, ccy, day, fx), "source": "revolut-brokerage",
            })
        elif section == "Other income & fees" and d.get("Date"):
            ccy = d.get("Currency", "EUR")
            name = d.get("Security name", "")
            kind = "dividend" if "dividend" in name.lower() else "fee" if "fee" in name.lower() else "other"
            income.append({
                "date": d["Date"], "asset": d.get("Symbol"), "type": kind, "ccy": ccy,
                "gross": num(d.get("Gross amount")), "wht": num(d.get("Withholding tax")) or 0.0,
                "net": num(d.get("Net Amount")), "net_eur": to_eur(num(d.get("Net Amount")), ccy, d["Date"], fx),
                "source": "revolut-brokerage",
            })
    return sells, income


def parse_crypto(rows, year):
    """Ключ-стойност редове: "Gross sales value",€111.70,"$122.05","Tax withheld…",€0.00,…"""
    kv = {}
    for r in rows:
        ne = nonempty(r)
        for i in range(0, len(ne) - 1):
            k, v = ne[i], ne[i + 1]
            if k and not k.startswith(("€", "$", "-")) and (v.startswith(("€", "-€"))):
                kv[k] = num(v)
    if "Gross sales value" not in kv:
        return [], []
    realized = [{
        "date": f"{year}-12-31", "year": year, "asset": "CRYPTO", "type": "crypto_summary",
        "proceeds_eur": kv.get("Gross sales value"), "cost_eur": kv.get("Cost of purchase"),
        "fees_eur": kv.get("Fees and other charges"), "pnl_eur": kv.get("Net capital gains income"),
        "tax_withheld_eur": (kv.get("Tax withheld on sales") or 0) + (kv.get("Tax withheld on purchase") or 0),
        "source": "revolut-crypto", "note": f"обобщение за {year} от Revolut (към датата на извлечението)",
    }]
    income = []
    for key, kind in (("Income from L&E activities", "learn_earn"), ("Income from Staking", "staking")):
        v = kv.get(key)
        if v:
            income.append({"date": f"{year}-12-31", "year": year, "asset": "CRYPTO", "type": kind,
                           "ccy": "EUR", "net": v, "net_eur": v, "source": "revolut-crypto"})
    return realized, income


TX_HEADER = ["Date", "Ticker", "Type", "Quantity", "Price per share", "Total Amount", "Currency", "FX Rate"]


def parse_transactions(rows):
    """trading-account-statement → (sells, income, positions, cash) или None, ако не е този формат."""
    if not rows or [c.strip() for c in rows[0][:8]] != TX_HEADER:
        return None
    pos, cash, sells, income = {}, {}, [], []
    last_day = ""
    for r in rows[1:]:
        if len(r) < 8 or not r[0]:
            continue
        d = dict(zip(TX_HEADER, r))
        day, tk, typ = d["Date"][:10], d["Ticker"], d["Type"].upper()
        ccy = d["Currency"] or "EUR"
        qty, price, total = num(d["Quantity"]), num(d["Price per share"]), num(d["Total Amount"]) or 0.0
        fx = num(d["FX Rate"]) or 1.0                     # USD за 1 EUR
        eur = total / fx if ccy == "USD" else total
        last_day = max(last_day, day)
        cash[ccy] = cash.get(ccy, 0.0)
        if typ.startswith("CASH TOP-UP"):
            cash[ccy] += total
        elif typ.startswith("CASH WITHDRAWAL"):
            cash[ccy] -= abs(total)
        elif typ.startswith("BUY"):
            p = pos.setdefault(tk, {"qty": 0.0, "invested_eur": 0.0, "ccy": ccy})
            p["qty"] += qty
            p["invested_eur"] += eur
            cash[ccy] -= total
        elif typ.startswith("SELL"):
            p = pos.setdefault(tk, {"qty": 0.0, "invested_eur": 0.0, "ccy": ccy})
            share = qty / p["qty"] if p["qty"] else 0
            cost_eur = p["invested_eur"] * share
            p["qty"] -= qty
            p["invested_eur"] -= cost_eur
            cash[ccy] += total
            gross = qty * price if (qty and price) else None
            fee = round(gross - total, 2) if gross is not None and gross - total > 0.005 else 0.0
            sells.append({"date": day, "asset": tk, "type": "sell", "qty": qty, "ccy": ccy,
                          "proceeds": round(total, 2), "proceeds_eur": round(eur, 2),
                          "cost_eur": round(cost_eur, 2), "pnl_eur": round(eur - cost_eur, 2),
                          "fee": fee, "fee_eur": round(fee / fx if ccy == "USD" else fee, 2),
                          "source": "revolut-transactions"})
        elif typ.startswith("DIVIDEND"):
            cash[ccy] += total
            income.append({"date": day, "asset": tk, "type": "dividend", "ccy": ccy, "gross": total,
                           "wht": 0.0, "net": total, "net_eur": round(eur, 2), "source": "revolut-transactions"})
        elif "FEE" in typ:
            cash[ccy] -= abs(total)
            income.append({"date": day, "asset": tk or "FEE", "type": "fee", "ccy": ccy,
                           "net": -abs(total), "net_eur": -round(abs(eur), 2), "source": "revolut-transactions"})
        else:
            print(f"  ? непознат тип „{d['Type']}“ на {day} — пропускам")
    for p in pos.values():
        p["qty"] = round(p["qty"], 9)
        p["invested_eur"] = round(p["invested_eur"], 2)
    return sells, income, {k: v for k, v in pos.items() if v["qty"] > 1e-9}, \
        {k: round(v, 2) for k, v in cash.items()}, last_day


def detect_year(rows, sells, income):
    for x in sells + income:
        return int(x["date"][:4])
    for r in rows:
        for c in r:
            m = re.match(r"(\d{2})\.(\d{2})\.(\d{2,4})$", c)
            if m:
                y = int(m.group(3))
                return y + 2000 if y < 100 else y
    return date.today().year


def parse_file(path, fx):
    rows = rows_of(read_text(path))
    tx = parse_transactions(rows)
    if tx:
        sells, income, positions, cash, last_day = tx
        return sells, income, {"positions": positions, "cash": cash, "as_of": last_day}
    sells, income = parse_brokerage(rows, fx)
    year = detect_year(rows, sells, income)
    c_real, c_inc = parse_crypto(rows, year)
    return sells + c_real, income + c_inc, None


# ─── СЛИВАНЕ В portfolio.json ────────────────────────────────────────────────
def key_of(x):
    if x.get("type") == "crypto_summary":
        return ("crypto_summary", x["year"])
    if x.get("asset") == "CRYPTO":
        return ("crypto_income", x.get("type"), x.get("year"))
    if x.get("type") == "sell":
        return ("sell", x.get("date"), x.get("asset"), round(x.get("qty") or 0, 8))
    return (x.get("type"), x.get("date"), x.get("asset"))


def merge(cfg, realized, income, apply_sells):
    log = []
    cfg.setdefault("realized", [])
    cfg.setdefault("income", [])
    years_with_summary = {x["year"] for x in realized if x.get("type") == "crypto_summary"}
    crypto_ids = {a["id"] for a in cfg["assets"] if a.get("group") == "crypto"}

    # ръчните крипто редове за година с официално обобщение отпадат (иначе двойно броене)
    before = len(cfg["realized"])
    cfg["realized"] = [x for x in cfg["realized"]
                       if not (x.get("asset") in crypto_ids and not x.get("source")
                               and int(str(x.get("date", "0000"))[:4]) in years_with_summary)]
    if len(cfg["realized"]) < before:
        log.append(f"− махнати {before - len(cfg['realized'])} ръчни крипто реда (заменени от обобщението на Revolut)")

    for lst_name, new in (("realized", realized), ("income", income)):
        lst = cfg[lst_name]
        idx = {key_of(x): i for i, x in enumerate(lst)}
        for x in new:
            k = key_of(x)
            if k in idx:
                old = lst[idx[k]]
                # P&L statement е по-точен (цена на придобиване от Revolut) → не го презаписваме,
                # само допълваме липсващи полета (напр. таксата от списъка сделки)
                add = {f: v for f, v in x.items() if old.get(f) is None and v is not None}
                if x.get("source") != "revolut-transactions":
                    add.update({f: v for f, v in x.items() if old.get(f) != v})
                if add:
                    old.update(add)
                    log.append(f"↻ {lst_name}: {x['asset']} {x['date']} ({', '.join(sorted(add))})")
            else:
                lst.append(x)
                idx[k] = len(lst) - 1
                log.append(f"+ {lst_name}: {x.get('type')} {x['asset']} {x['date']} "
                           f"{x.get('pnl_eur', x.get('net_eur'))} €")
                if apply_sells and lst_name == "realized" and x.get("type") == "sell":
                    log += apply_sell(cfg, x)
        lst.sort(key=lambda x: x.get("date", ""))
    return log


def apply_sell(cfg, s):
    a = next((a for a in cfg["assets"] if a.get("id") == s["asset"] or a.get("symbol") == s["asset"]), None)
    if not a or a.get("qty") is None or not s.get("qty"):
        return [f"  ! {s['asset']}: няма позиция в конфигурацията — пропускам корекцията"]
    applied = cfg.setdefault("_applied_sells", [])
    k = f"{s['date']}:{s['asset']}:{s['qty']}"
    if k in applied:
        return []
    asof = cfg.get("positions_as_of", "")
    if s["date"] <= asof:
        return [f"  = {a['id']}: продажбата е от {s['date']} ≤ positions_as_of {asof} — qty вече я съдържа"]
    q0, inv0 = float(a["qty"]), float(a.get("invested_eur") or 0)
    if q0 - s["qty"] < -1e-9:
        return [f"  ! {s['asset']}: продадено {s['qty']} > qty {q0} — вероятно вече е коригирано ръчно"]
    share = s["qty"] / q0 if q0 else 0
    a["qty"] = round(q0 - s["qty"], 9)
    a["invested_eur"] = round(inv0 * (1 - share), 2)
    applied.append(k)
    return [f"  → {a['id']}: qty {q0} → {a['qty']}, вложено €{inv0} → €{a['invested_eur']}"]


def apply_positions(cfg, snap, fx):
    log = []
    by_key = {}
    for a in cfg["assets"]:
        by_key[a["id"]] = a
        if a.get("symbol"):
            by_key[a["symbol"].split(".")[0]] = a
    for tk, p in sorted(snap["positions"].items()):
        a = by_key.get(tk)
        if not a:
            log.append(f"  ! {tk}: няма го в portfolio.json — добави актив (id, symbol, bucket), после пусни отново")
            continue
        if (a.get("qty"), a.get("invested_eur")) != (p["qty"], p["invested_eur"]):
            log.append(f"  → {a['id']}: qty {a.get('qty')} → {p['qty']}, вложено €{a.get('invested_eur')} → €{p['invested_eur']}")
            a["qty"], a["invested_eur"] = p["qty"], p["invested_eur"]
    held = set(snap["positions"])
    for a in cfg["assets"]:
        if a.get("source") == "yahoo" and not a.get("closed") and a["id"] not in held \
                and (a.get("symbol") or "").split(".")[0] not in held:
            log.append(f"  ! {a['id']}: го няма в извлечението — продаден ли е? (сложи closed: true)")
    cash = snap["cash"]
    rate = fx[max(fx)] if fx else 1.10
    cash_eur = round(cash.get("EUR", 0) + cash.get("USD", 0) / rate, 2)
    c = next((a for a in cfg["assets"] if a["id"] == "CASH"), None)
    if c is not None and c.get("value_eur") != cash_eur:
        log.append(f"  → CASH (брокерска): €{c.get('value_eur')} → €{cash_eur} "
                   f"({', '.join(f'{v} {k}' for k, v in cash.items())})")
        c["value_eur"] = cash_eur
    if snap["as_of"] and cfg.get("positions_as_of", "") != snap["as_of"]:
        log.append(f"  → positions_as_of: {cfg.get('positions_as_of')} → {snap['as_of']}")
        cfg["positions_as_of"] = snap["as_of"]
    return log


def report(cfg):
    out = []
    by_year = {}
    for x in cfg.get("realized", []):
        y = str(x.get("year") or x.get("date", "")[:4])
        b = by_year.setdefault(y, {"pnl": 0.0, "fees": 0.0, "n": 0, "unknown": 0})
        if x.get("pnl_eur") is not None:
            b["pnl"] += x["pnl_eur"]
        elif x.get("proceeds_eur") is not None and x.get("cost_eur") is not None:
            b["pnl"] += x["proceeds_eur"] - x["cost_eur"]
        else:
            b["unknown"] += 1
        b["fees"] += x.get("fees_eur") or 0
        b["n"] += 1
    for y, b in sorted(by_year.items()):
        out.append(f"{y}: {b['n']} реда реализирано · P&L {b['pnl']:+.2f} € · такси {b['fees']:.2f} €"
                   + (f" · {b['unknown']} непълни" if b["unknown"] else ""))
    inc = {}
    for x in cfg.get("income", []):
        y = str(x.get("year") or x.get("date", "")[:4])
        inc[y] = inc.get(y, 0) + (x.get("net_eur") or 0)
    for y, v in sorted(inc.items()):
        out.append(f"{y}: доходи (дивиденти, L&E, staking) {v:+.2f} €")
    return out


def main(argv):
    files = [a for a in argv if not a.startswith("--")]
    write, apply_sells, positions = "--write" in argv, "--apply-sells" in argv, "--positions" in argv
    if not files:
        print(__doc__)
        return 1
    fx = fx_table()
    realized, income, snaps = [], [], []
    for f in files:
        r, i, snap = parse_file(f, fx)
        print(f"📄 {os.path.basename(f)}: {len(r)} реализирани, {len(i)} доходи"
              + (f", {len(snap['positions'])} позиции към {snap['as_of']}" if snap else ""))
        realized += r
        income += i
        if snap:
            snaps.append(snap)
    with open(CFG_FILE, encoding="utf-8") as fh:
        cfg = json.load(fh)
    log = merge(cfg, realized, income, apply_sells and not snaps)
    if snaps and positions:
        log += apply_positions(cfg, max(snaps, key=lambda s: s["as_of"]), fx)
    elif snaps:
        print("ℹ️ Списък сделки — добави --positions, за да обновиш qty/вложено/кеш:")
        for tk, p in sorted(max(snaps, key=lambda s: s["as_of"])["positions"].items()):
            print(f"   {tk:<6} qty {p['qty']:<12} вложено €{p['invested_eur']}")
    print("\n".join(log) if log else "ℹ️ Нищо ново — всичко вече е импортирано.")
    print("\n".join(report(cfg)))
    if write and log:
        tmp = CFG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, CFG_FILE)
        print(f"💾 Записано: {os.path.relpath(CFG_FILE, ROOT)}")
    elif log:
        print("ℹ️ Пробно пускане — добави --write, за да запишеш.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
