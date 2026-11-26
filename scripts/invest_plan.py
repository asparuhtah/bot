"""
Invest Plan v1 — правилата от „Инвестиционен план 12 месеца (дек 2026 – ное 2027)“
===================================================================================
Чист модул без мрежа и без Telegram: получава редовете на портфейла от
invest_tracker.py и връща (а) обобщение по кофи, (б) алерти по правилата,
(в) текст за сутрешния/дневния отчет. Цялото състояние е в state["plan"].

Кофи: safe (сигурна) · core (ядро) · risky (рискова). Всяко assets[] в
portfolio.json може да има "bucket"; иначе: cash→safe, crypto→risky, stocks→core.

Ботът САМО сигнализира. Сделките се правят ръчно в Revolut.
"""

from datetime import date, datetime, timedelta

BUCKETS = ("safe", "core", "risky")            # по подразбиране; реално = ключовете на plan["targets"]
LABEL = {"safe": "🛡 Сигурна", "core": "🧱 Ядро", "risky": "🎲 Рискова",
         "bonds": "📜 Облигации", "gold": "🥇 Злато"}
DEFAULT_BUCKET = {"cash": "safe", "crypto": "risky", "stocks": "core"}


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _eur(x):
    return f"€{x:,.2f}".replace(",", " ")


def _pct(x):
    return f"{'+' if x >= 0 else '−'}{abs(x):.1f}%"


def bucket_of(a):
    return a.get("bucket") or DEFAULT_BUCKET.get(a.get("group"), "core")


def buckets_of(plan):
    return list(plan.get("targets") or {k: 0 for k in BUCKETS})


def active_plan(plan, today):
    """Фазите от стратегията до 2030: последната с from ≤ днес презаписва цели, лимити, вноска."""
    if not plan:
        return plan
    out = {k: v for k, v in plan.items() if k != "phases"}
    phase, nxt = None, None
    for ph in sorted(plan.get("phases", []), key=lambda x: x["from"]):
        if _d(ph["from"]) <= today:
            if ph.get("enabled", True):          # фаза с enabled:false чака одобрение след преглед
                phase = ph
            elif not nxt:
                nxt = ph
        elif not nxt:
            nxt = ph
    if nxt:
        out["next_phase"] = {"name": nxt.get("name"), "from": nxt["from"], "enabled": nxt.get("enabled", True)}
    if phase:
        out.update({k: v for k, v in phase.items() if k not in ("from", "name")})
        out["phase"] = phase.get("name", phase["from"])
        out["phase_from"] = phase["from"]
    return out


def missing_instruments(assets, plan):
    """Инструменти по стратегията (plan.strategy_instruments), които още не се държат."""
    held = {a["id"] for a in assets if not a.get("closed") and ((a.get("qty") or 0) > 0 or a.get("value_eur"))}
    return [(b, i) for b, ids in (plan.get("strategy_instruments") or {}).items() for i in ids if i not in held]


# ─── ОБОБЩЕНИЕ ────────────────────────────────────────────────────────────────
def summarize(assets, rows, plan):
    cfg_by_id = {a["id"]: a for a in assets}
    bks = buckets_of(plan)
    val = {b: 0.0 for b in bks}
    inv = {b: 0.0 for b in bks}
    for r in rows:
        b = bucket_of(cfg_by_id.get(r["asset"], {}))
        if b not in val:                      # кофа без цел в текущата фаза → към ядрото
            b = "core" if "core" in val else bks[0]
        val[b] += r["value_eur"] or 0
        inv[b] += r["invested_eur"] or 0
    total = sum(val.values())
    targets = plan.get("targets", {})
    out = {"total": round(total, 2), "buckets": {}}
    for b in bks:
        pct = val[b] / total * 100 if total else 0
        tgt = float(targets.get(b, 0)) * 100
        out["buckets"][b] = {"value": round(val[b], 2), "invested": round(inv[b], 2),
                             "pct": round(pct, 1), "target_pct": round(tgt, 1),
                             "dev_pp": round(pct - tgt, 1)}
    rk = out["buckets"].setdefault("risky", {"value": 0, "invested": 0, "pct": 0, "target_pct": 0, "dev_pp": 0})
    rk["drawdown_pct"] = round((rk["value"] / rk["invested"] - 1) * 100, 1) if rk["invested"] else 0.0
    return out


# ─── СЪБИТИЯ И ВНОСКИ ─────────────────────────────────────────────────────────
def upcoming_events(plan, today, days):
    ev = []
    for e in plan.get("events", []):
        d = _d(e["date"])
        if today <= d <= today + timedelta(days=days):
            ev.append({**e, "d": d})
    return sorted(ev, key=lambda e: e["d"])


def shift_for_blackout(d, plan):
    """Вноска не пада 'blackout' дни преди събитие и до 1 ден след него → мести се на ден+2."""
    bl = int(plan.get("rules", {}).get("event_blackout_days", 2))
    for _ in range(10):
        moved = False
        for e in plan.get("events", []):
            if e.get("ticker"):           # отчет на компания не спира вноската в ядрото
                continue
            ed = _d(e["date"])
            if ed - timedelta(days=bl) <= d <= ed + timedelta(days=1):
                d, moved = ed + timedelta(days=2), True
        if not moved:
            return d
    return d


def next_contribution(plan, today):
    day = int(plan.get("contribution_day", 23))
    y, m = today.year, today.month
    try:
        d = date(y, m, day)
    except ValueError:
        d = date(y, m, 28)
    if d < today:
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        d = date(y, m, min(day, 28))
    return shift_for_blackout(d, plan)


def frozen_until(state):
    s = state.get("plan", {}).get("risky_frozen_until")
    return _d(s) if s else None


def where_next(summary, plan, state, today):
    """Най-изостаналата кофа; рисковата отпада, ако е замразена или над лимита."""
    b = summary["buckets"]
    cap = float(plan.get("cap_risky_invested_eur", 2000))
    fz = frozen_until(state)
    cands = [k for k in b
             if not (k == "risky" and (b["risky"]["invested"] >= cap or (fz and fz >= today)))]
    k = min(cands, key=lambda x: b[x]["dev_pp"])
    return k, plan.get("instruments", {}).get(k, k)


# ─── ЕТАЛОН ───────────────────────────────────────────────────────────────────
def update_benchmark(assets, rows, plan, state, today):
    """
    Еталон = същите вноски, но в индекс: вноските в safe кофата → XEON-лихва,
    всички останали (ядро + рискова) → VWCE. Сравнява се само инвестираната част
    (без кеш), защото кешът е еднакъв и в двата случая.
    """
    bm = plan.get("benchmark", {})
    ref_id = bm.get("asset", "VWCE")
    ref = next((r for r in rows if r["asset"] == ref_id), None)
    if not ref:
        return None
    cfg_by_id = {a["id"]: a for a in assets}
    inv_safe = sum(r["invested_eur"] or 0 for r in rows
                   if r["invested_eur"] is not None and bucket_of(cfg_by_id.get(r["asset"], {})) == "safe")
    inv_rest = sum(r["invested_eur"] or 0 for r in rows
                   if r["invested_eur"] is not None and bucket_of(cfg_by_id.get(r["asset"], {})) != "safe")
    val_inv = sum(r["value_eur"] or 0 for r in rows if r["invested_eur"] is not None)
    val_safe = sum(r["value_eur"] or 0 for r in rows
                   if r["invested_eur"] is not None and bucket_of(cfg_by_id.get(r["asset"], {})) == "safe")
    rate = float(bm.get("safe_rate_pct", 2.5)) / 100
    price = ref["price_eur"]

    p = state.setdefault("plan", {})
    b = p.get("bench")
    if not b:
        b = {"start": today.isoformat(), "units": (val_inv - val_safe) / price, "safe": val_safe,
             "inv_safe": inv_safe, "inv_rest": inv_rest, "day": today.isoformat(),
             "port_start_value": round(val_inv, 2), "start_invested": round(inv_safe + inv_rest, 2)}
        p["bench"] = b
    last = _d(b["day"])
    if today > last:                                   # лихва за изминалите дни
        b["safe"] *= (1 + rate) ** ((today - last).days / 365)
        b["day"] = today.isoformat()
    d_rest, d_safe = inv_rest - b["inv_rest"], inv_safe - b["inv_safe"]
    if abs(d_rest) >= 0.01:
        b["units"] += d_rest / price
        b["inv_rest"] = inv_rest
    if abs(d_safe) >= 0.01:
        b["safe"] += d_safe
        b["inv_safe"] = inv_safe
    b["units"], b["safe"] = round(b["units"], 9), round(b["safe"], 4)

    # база = стойността в деня на старта + нетните вноски след това (еднаква за двете страни)
    bench_val = b["units"] * price + b["safe"]
    base = b["port_start_value"] + (inv_safe + inv_rest) - b["start_invested"]
    port_ret = (val_inv / base - 1) * 100 if base else 0
    bench_ret = (bench_val / base - 1) * 100 if base else 0
    return {"since": b["start"], "port_value": round(val_inv, 2), "bench_value": round(bench_val, 2),
            "port_ret": round(port_ret, 2), "bench_ret": round(bench_ret, 2),
            "diff_pp": round(port_ret - bench_ret, 2)}


def _too_old(r, now, max_age):
    """Стара цена (⏳) се приема до max_age; по-стара не задейства правила."""
    if not r.get("stale"):
        return False
    try:
        return now - datetime.fromisoformat(r.get("stale_at") or "") > max_age
    except ValueError:
        return True


# ─── АЛЕРТИ ПО ПРАВИЛАТА ──────────────────────────────────────────────────────
def check_plan(assets, rows, summary, plan, state, now):
    today = now.date()
    rules = plan.get("rules", {})
    p = state.setdefault("plan", {})
    zones = p.setdefault("zones", {})
    peaks = p.setdefault("peaks", {})
    flags = p.setdefault("flags", {})
    cfg_by_id = {a["id"]: a for a in assets}
    caps = plan.get("position_caps_eur", {})
    no_stop = set(plan.get("no_stop", ["BTC"]))
    msgs = []

    tp = float(rules.get("take_profit_pct", 50))
    sl = float(rules.get("stop_loss_pct", -30))
    arm = float(rules.get("trailing_arm_pct", 30))
    trail = float(rules.get("trailing_stop_pct", -20))

    # 1) правила по позиция (само рискова кофа + лимити за всички с cap)
    max_age = timedelta(days=int(rules.get("stale_ok_days", 3)))
    for r in rows:
        a = cfg_by_id.get(r["asset"], {})
        aid, b = r["asset"], bucket_of(a)
        if r["invested_eur"] is None or _too_old(r, now, max_age):
            continue
        zone = "ok"
        pct = r["pnl_pct"]
        if b == "risky" and pct is not None:
            if pct >= arm:
                peaks[aid] = max(peaks.get(aid, 0), r["price_eur"])
            pk = peaks.get(aid)
            if aid not in no_stop and pct <= sl:
                zone = "sl"
            elif pk and r["price_eur"] <= pk * (1 + trail / 100):
                zone = "trail"
            elif pct >= tp:
                zone = "tp"
        cap = caps.get(aid)
        if zone == "ok" and cap and r["value_eur"] > float(cap):
            zone = "cap"
        if zone != zones.get(aid, "ok"):
            n = f"<b>{r['name']}</b>"
            if zone == "sl":
                msgs.append(f"🛑 {n} е на {_pct(pct)} от вложеното (≤ {sl:.0f}%). "
                            f"По правилото за стоп-загуба: продай и прехвърли сумата в ядрото.")
            elif zone == "trail":
                msgs.append(f"🛑 {n} падна {trail:.0f}% от върха след печалба. Плъзгащ стоп: продай останалото.")
            elif zone == "tp":
                msgs.append(f"💰 {n} е на {_pct(pct)}. Правило +{tp:.0f}%: продай половината → ядро (VWCE).")
            elif zone == "cap":
                msgs.append(f"📏 {n} е {_eur(r['value_eur'])} — над лимита {_eur(float(cap))}. Не добавяй.")
            elif zones.get(aid) in ("sl", "trail", "tp", "cap"):
                msgs.append(f"⬜ {n} излезе от зоната за действие ({_pct(pct or 0)}).")
            zones[aid] = zone
            if zone == "ok" and aid in peaks and (pct or 0) < arm:
                peaks.pop(aid, None)

    # 2) лимити и замразяване на рисковата кофа
    rk = summary["buckets"]["risky"]
    cap_r = float(plan.get("cap_risky_invested_eur", 2000))
    over = rk["invested"] > cap_r
    if over != flags.get("risky_over_cap", False):
        msgs.append(f"🚫 Рисковата кофа: вложени {_eur(rk['invested'])} > лимит {_eur(cap_r)}. Без нови рискови покупки."
                    if over else f"✅ Рисковата кофа отново под лимита {_eur(cap_r)}.")
        flags["risky_over_cap"] = over
    fr = float(rules.get("risky_drawdown_freeze_pct", -30))
    fz = frozen_until(state)
    if rk["invested"] and rk["drawdown_pct"] <= fr and not (fz and fz >= today):
        until = today + timedelta(days=int(rules.get("freeze_days", 90)))
        p["risky_frozen_until"] = until.isoformat()
        msgs.append(f"🧊 Рисковата кофа е на {_pct(rk['drawdown_pct'])}. Нови рискови покупки спират до "
                    f"{until:%d.%m.%Y}; вноските отиват в ядрото.")

    cap_t = float(plan.get("cap_total_eur", 10000))
    over_t = summary["total"] >= cap_t
    if over_t != flags.get("total_over_cap", False):
        if over_t:
            msgs.append(f"🏁 Портфейлът достигна {_eur(summary['total'])} ≥ {_eur(cap_t)} — таванът на пробната година.")
        flags["total_over_cap"] = over_t

    # 3) отклонение на кофите
    band = float(plan.get("rebalance_band_pp", 5))
    for k in summary["buckets"]:
        bk = summary["buckets"][k]
        if not bk["target_pct"] and not bk["value"]:
            continue
        st = "low" if bk["dev_pp"] < -band else "high" if bk["dev_pp"] > band else "ok"
        key = f"dev_{k}"
        if st != flags.get(key, "ok") and st != "ok":
            msgs.append(f"⚖️ {LABEL.get(k, k)}: {bk['pct']:.0f}% при цел {bk['target_pct']:.0f}% "
                        f"({'+' if bk['dev_pp'] > 0 else ''}{bk['dev_pp']:.0f} п.п.). "
                        + ("Насочи следващите вноски тук." if st == "low" else "Спри вноските тук, без да продаваш."))
        flags[key] = st

    # 4) купуване при спад на ядрото (VWCE)
    dip_id = plan.get("dip_buy_asset", "VWCE")
    r = next((x for x in rows if x["asset"] == dip_id and not _too_old(x, now, max_age)), None)
    if r:
        pk = max(p.get("dip_peak", 0), r["price_eur"])
        if pk > p.get("dip_peak", 0):
            p["dip_peak"], p["dip_level"] = pk, 0
        dd = (r["price_eur"] / pk - 1) * 100
        levels = sorted(rules.get("dip_buy_vwce_pct", [-10, -15, -20]), reverse=True)
        hit = sum(1 for lv in levels if dd <= lv)
        if hit > p.get("dip_level", 0):
            msgs.append(f"🟢 <b>{r['name']}</b> е {_pct(dd)} от върха {_eur(pk)}. "
                        f"Ниво {hit}/{len(levels)}: купи с 1/3 от резерва за спад в сигурната кофа.")
            p["dip_level"] = hit

    # 5) без добавяне (no_add): количеството в portfolio.json се е увеличило
    last_qty = p.setdefault("qty", {})
    for a in assets:
        q = a.get("qty")
        if q is None:
            continue
        if a["id"] in plan.get("no_add", []) and q > last_qty.get(a["id"], q) + 1e-9:
            msgs.append(f"✋ <b>{a['name']}</b> е в списъка „без добавяне“ — новите пари трябва да отидат в VWCE.")
        last_qty[a["id"]] = q

    # 6) отчети на компании: намали печеливша позиция седмица преди отчет
    trim = float(rules.get("pre_earnings_trim_pct", 30))
    sent = p.setdefault("event_sent", {})
    for e in upcoming_events(plan, today, 7):
        t = e.get("ticker")
        rr = next((x for x in rows if x["asset"] == t), None) if t else None
        k = f"trim:{e['date']}:{t}"
        if rr and (rr["pnl_pct"] or 0) >= trim and k not in sent:
            msgs.append(f"📅 {e['name']} на {e['d']:%d.%m}. {rr['name']} е на {_pct(rr['pnl_pct'])} → "
                        f"намали с 1/3 тази седмица. Не добавяй преди отчета.")
            sent[k] = today.isoformat()

    # 7) напомняне за макро събитие (3 дни напред), веднъж на събитие
    bl = int(rules.get("event_blackout_days", 2))
    for e in upcoming_events(plan, today, 3):
        k = f"ev:{e['date']}:{e['name']}"
        if k not in sent and not e.get("ticker"):
            end = e["d"] + timedelta(days=1)
            msgs.append(f"⚠️ {e['name']} на {e['d']:%d.%m}. Без нови покупки от "
                        f"{e['d'] - timedelta(days=bl):%d.%m} до {end:%d.%m} включително.")
            sent[k] = today.isoformat()
    # чистим стари ключове
    cutoff = (today - timedelta(days=60)).isoformat()
    for k in [k for k, v in sent.items() if v < cutoff]:
        sent.pop(k)
    return msgs


# ─── ТЕКСТ ЗА ОТЧЕТИТЕ ────────────────────────────────────────────────────────
def plan_text(summary, bench, plan, state, now, assets=None):
    today = now.date()
    L = [f"<b>🧭 План</b>{' · ' + plan['phase'] if plan.get('phase') else ''}"]
    for k in summary["buckets"]:
        b = summary["buckets"][k]
        if not b["target_pct"] and not b["value"]:
            continue
        mark = "🟢" if abs(b["dev_pp"]) <= float(plan.get("rebalance_band_pp", 5)) else "🟠"
        L.append(f"{mark} {LABEL.get(k, k)}: {_eur(b['value'])} · {b['pct']:.0f}% (цел {b['target_pct']:.0f}%)")
    rk = summary["buckets"]["risky"]
    cap_r = float(plan.get("cap_risky_invested_eur", 2000))
    L.append(f"   рискова: вложени {_eur(rk['invested'])} / {_eur(cap_r)} · {_pct(rk['drawdown_pct'])}")
    fz = frozen_until(state)
    if fz and fz >= today:
        L.append(f"🧊 Рискови покупки замразени до {fz:%d.%m.%Y}")
    nd = next_contribution(plan, today)
    k, inst = where_next(summary, plan, state, today)
    amt = float(plan.get("monthly_contribution_eur", 500))
    L.append(f"📆 Следваща вноска {_eur(amt)}: {nd:%d.%m} → най-изостанала кофа {LABEL.get(k, k)} ({inst})")
    ev = upcoming_events(plan, today, 7)
    if ev:
        L.append("📅 " + " · ".join(f"{e['d']:%d.%m} {e['name']}" for e in ev))
    nx = plan.get("next_phase")
    if nx:
        L.append(f"🗓 Следваща фаза „{nx['name']}“ от {_d(nx['from']):%d.%m.%Y}"
                 + ("" if nx["enabled"] else " — чака одобрение (enabled: true след прегледа)"))
    miss = missing_instruments(assets or [], plan)
    if miss:
        L.append("🧩 Липсват по стратегия: " + ", ".join(f"{i} ({LABEL.get(b, b)})" for b, i in miss))
    if bench:
        sign = "🟢" if bench["diff_pp"] >= 0 else "🔴"
        L.append(f"{sign} Еталон от {_d(bench['since']):%d.%m.%Y}: портфейл {_pct(bench['port_ret'])} "
                 f"vs индекс {_pct(bench['bench_ret'])} ({'+' if bench['diff_pp'] >= 0 else ''}{bench['diff_pp']:.1f} п.п.)")
    return "\n".join(L)
