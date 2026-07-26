#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diss_build.py — събира дисертационните MD файлове в docs/diss-data.json.

Папки (спрямо корена на репото):
  dissertation/График/          timeline.md (Gantt редове, Дедлайн), ansys.md (стъпки, правила, region таблица)
  dissertation/Глави/           Гл1.md, Гл2.md… — чернови (броят се думи) + checkbox статуси
  dissertation/Всички задачи/   произволни MD от сесии — checkbox задачи с глави

Формат на задачите:
  - [x] готово   - [~] в процес   - [ ] предстои   - [!] блокирано   бележка след ::
  Глава: от заглавие "## Гл. 4 …" над списъка или префикс "Гл. 4:" в реда.
  Мета: "ANSYS стъпка: 6", "Дедлайн: 2026-12-31".

Сливане: спрямо предишния diss-data.json ПО-НАПРЕДНАЛИЯТ статус печели
  (предстои < в процес < блокирано < готово). Ръчните отметки от уеб-а живеят
  в localStorage на браузъра и се сливат там по същото правило.

Пускане: python scripts/diss_build.py   (от корена на репото)
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D_DIR = os.path.join(ROOT, "dissertation")
OUT = os.path.join(ROOT, "docs", "diss-data.json")

RANK = {"todo": 0, "wip": 1, "block": 2, "done": 3}
GANTT_START = (2026, 5)  # май 2026
GANTT_MONTHS = 8

CHAPTER_ALIASES = [
    (r"увод|въведение", "Увод / Въведение"),
    (r"гл\.?\s*1|литератур", "Гл. 1 — Литературен обзор"),
    (r"гл\.?\s*2|описание на систем", "Гл. 2 — Описание на системата"),
    (r"гл\.?\s*3|теоретичен", "Гл. 3 — Теоретичен анализ"),
    (r"гл\.?\s*4|методолог", "Гл. 4 — Методология"),
    (r"ansys|cfd|fluent|mesh", "CFD — ANSYS Fluent"),
    (r"гл\.?\s*5|резултат", "Гл. 5 — Резултати"),
    (r"извод|препорък", "Изводи и препоръки"),
    (r"библиограф|приложени", "Библиография / Приложения"),
]
CHAPTER_ORDER = [name for _, name in CHAPTER_ALIASES] + ["Импортирани / Разни"]


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[„“\"'’`().,;:!?†*_\[\]#—-]", " ", s.lower())).strip()


def task_id(chapter, text):
    return hashlib.md5((chapter + "|" + norm(text)).encode()).hexdigest()[:10]


def find_chapter(hint):
    if not hint:
        return None
    h = hint.lower()
    for pat, name in CHAPTER_ALIASES:
        if re.search(pat, h):
            return name
    return None


def status_from_line(line):
    m = re.match(r"\s*[-*]\s*\[(.| )\]", line)
    if m:
        c = m.group(1).lower()
        return {"x": "done", "~": "wip", "/": "wip", "!": "block"}.get(c, "todo")
    n = norm(line)
    if re.search(r"✓|готово|решен|завършен|приключ|направен", n):
        return "done"
    if re.search(r"⛔|блокир|чака|спрян|изчаква", n):
        return "block"
    if re.search(r"⏳|в процес|частично|продължава|работя по", n):
        return "wip"
    return None


def parse_tasks(text, default_chapter=None):
    """Връща (tasks, meta): tasks=[(chapter, text, status, note)], meta={ansysStep, deadline}."""
    tasks, meta = [], {}
    ctx = default_chapter
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        h = re.match(r"^#{1,4}\s+(.*)", line)
        if h:
            ch = find_chapter(h.group(1))
            if ch:
                ctx = ch
            continue
        m = re.search(r"ansys\s*стъпка[:\s]+(\d+)", line, re.I)
        if m:
            meta["ansysStep"] = int(m.group(1))
            continue
        m = re.search(r"дедлайн[:\s]+(\d{4}-\d{2}-\d{2})", line, re.I)
        if m:
            meta["deadline"] = m.group(1)
            continue

        is_cb = bool(re.match(r"^\s*[-*]\s*\[.?\]", line))
        st = status_from_line(line)
        if st is None and not is_cb:
            continue
        if not is_cb and not re.match(r"^[-*•]", line):
            continue

        body = re.sub(r"^\s*[-*•]\s*(\[.?\]\s*)?", "", line)
        note = ""
        if "::" in body:
            body, note = body.split("::", 1)
            body, note = body.strip(), note.strip()
        body = re.sub(r"[✓⏳⛔✅]", "", body).strip()

        ch = ctx
        pref = re.match(r"^([^:]{2,45}):\s+(.*)", body)
        if pref and find_chapter(pref.group(1)):
            ch, body = find_chapter(pref.group(1)), pref.group(2).strip()
        if not ch:
            ch = find_chapter(body) or "Импортирани / Разни"
        if body:
            tasks.append((ch, body, st or "todo", note))
    return tasks, meta


def count_words(text):
    """Думи в прозата (без checkbox редове, заглавия, мета редове)."""
    words = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or re.match(r"^\s*[-*]\s*\[.?\]", s):
            continue
        if re.match(r"^(цел|дедлайн|ansys)", s, re.I):
            continue
        words += len(re.findall(r"[\wа-яА-Я]+", s))
    return words


def parse_date_offset(s):
    """'2026-06' или '2026-06-15' → месечен offset спрямо GANTT_START."""
    m = re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?", s.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    return (y - GANTT_START[0]) * 12 + (mo - GANTT_START[1]) + (d - 1) / 30.0


def parse_timeline(text):
    """Редове: '- Име :: 2026-05 → 2026-06-07 :: критичен'  (тип: критичен|процес|план|готово)."""
    colors = {"критичен": "#f85149", "процес": "#d29922", "план": "#58a6ff", "готово": "#3fb950"}
    rows, deadline = [], None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.search(r"дедлайн[:\s]+(\d{4}-\d{2}-\d{2})", line, re.I)
        if m:
            deadline = m.group(1)
            continue
        if not line.startswith(("-", "*")):
            continue
        parts = [p.strip() for p in re.sub(r"^[-*]\s*", "", line).split("::")]
        if len(parts) < 2 or "→" not in parts[1] and "->" not in parts[1]:
            continue
        se = re.split(r"→|->", parts[1])
        start, end = parse_date_offset(se[0]), parse_date_offset(se[1])
        if start is None or end is None:
            continue
        kind = parts[2].lower() if len(parts) > 2 else "план"
        rows.append({
            "name": parts[0],
            "start": round(start, 2), "end": round(end, 2),
            "col": colors.get(kind, "#58a6ff"),
            "crit": kind == "критичен",
            "ch": find_chapter(parts[0]),
        })
    return rows, deadline


def parse_ansys(text):
    """'Текуща стъпка: N', номериран списък 'N. Title :: note', '## Правила' текст, '## Region' таблица."""
    ansys = {"currentStep": 1, "steps": [], "rules": "", "regions": []}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.search(r"текуща\s*стъпка[:\s]+(\d+)", line, re.I)
        if m:
            ansys["currentStep"] = int(m.group(1))
            continue
        h = re.match(r"^#{1,4}\s+(.*)", line)
        if h:
            t = h.group(1).lower()
            section = "rules" if "правил" in t else "regions" if "region" in t else None
            continue
        m = re.match(r"^(\d+)\.\s+(.*)", line)
        if m and section is None:
            body = m.group(2)
            note = ""
            if "::" in body:
                body, note = [x.strip() for x in body.split("::", 1)]
            ansys["steps"].append({"title": body, "note": note})
            continue
        if section == "rules" and line:
            ansys["rules"] += (line + "\n")
        elif section == "regions" and line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            ansys["regions"].append(cells)
    ansys["rules"] = ansys["rules"].strip()
    return ansys


def chapter_from_filename(fn):
    base = os.path.splitext(os.path.basename(fn))[0]
    return find_chapter(base)


def load_previous():
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def read_dir(path):
    out = []
    if os.path.isdir(path):
        for fn in sorted(os.listdir(path)):
            if fn.lower().endswith((".md", ".markdown", ".txt")):
                with open(os.path.join(path, fn), encoding="utf-8") as f:
                    out.append((fn, f.read()))
    return out


def main():
    prev = load_previous()
    chapters = {}  # name -> {tasks: {id: task}, words, target, notes}

    def ch_bucket(name):
        return chapters.setdefault(name, {"tasks": {}, "words": 0, "target": None, "notes": []})

    # предишни задачи (за да не изчезват + за merge по статус)
    for ch in prev.get("chapters", []):
        b = ch_bucket(ch["name"])
        for t in ch.get("tasks", []):
            b["tasks"][t["id"]] = dict(t)

    def merge_task(ch_name, text, status, note):
        tid = task_id(ch_name, text)
        b = ch_bucket(ch_name)
        cur = b["tasks"].get(tid)
        if cur is None:
            b["tasks"][tid] = {"id": tid, "t": text, "s": status, "n": note}
        else:
            if RANK[status] > RANK.get(cur.get("s", "todo"), 0):
                cur["s"] = status
            if note:
                cur["n"] = note

    meta_all = {}

    # 1) Всички задачи/
    for fn, text in read_dir(os.path.join(D_DIR, "Всички задачи")):
        tasks, meta = parse_tasks(text)
        meta_all.update(meta)
        for ch, t, s, n in tasks:
            merge_task(ch, t, s, n)

    # 2) Глави/ — думи + статуси + бележки
    for fn, text in read_dir(os.path.join(D_DIR, "Глави")):
        if fn.lower().startswith("readme"):
            continue
        ch_name = chapter_from_filename(fn) or "Импортирани / Разни"
        b = ch_bucket(ch_name)
        b["words"] += count_words(text)
        m = re.search(r"цел[:\s]+(\d+)", text, re.I)
        if m:
            b["target"] = int(m.group(1))
        tasks, meta = parse_tasks(text, default_chapter=ch_name)
        meta_all.update(meta)
        for ch, t, s, n in tasks:
            merge_task(ch, t, s, n)
        for line in text.splitlines():
            s = line.strip()
            if s.lower().startswith(("статус:", "бележка:")):
                b["notes"].append(s.split(":", 1)[1].strip())

    # 3) График/
    gantt, ansys = prev.get("gantt", []), prev.get("ansys", {})
    deadline = meta_all.get("deadline") or prev.get("deadline", "2026-12-31")
    for fn, text in read_dir(os.path.join(D_DIR, "График")):
        if "ansys" in fn.lower():
            parsed = parse_ansys(text)
            if parsed["steps"]:
                ansys = parsed
            elif ansys:
                ansys["currentStep"] = parsed["currentStep"] or ansys.get("currentStep", 1)
        else:
            rows, dl = parse_timeline(text)
            if rows:
                gantt = rows
            if dl:
                deadline = dl
    if meta_all.get("ansysStep") and ansys:
        ansys["currentStep"] = meta_all["ansysStep"]

    # подреждане
    def order_key(name):
        return CHAPTER_ORDER.index(name) if name in CHAPTER_ORDER else 99

    out_chapters = []
    for name in sorted(chapters, key=order_key):
        b = chapters[name]
        out_chapters.append({
            "name": name,
            "words": b["words"],
            "target": b["target"],
            "notes": b["notes"],
            "tasks": list(b["tasks"].values()),
        })

    data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "deadline": deadline,
        "ganttMeta": {"startYear": GANTT_START[0], "startMonth": GANTT_START[1] - 1, "months": GANTT_MONTHS},
        "gantt": gantt,
        "chapters": out_chapters,
        "ansys": ansys,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    n_tasks = sum(len(c["tasks"]) for c in out_chapters)
    print(f"diss-data.json: {len(out_chapters)} глави, {n_tasks} задачи, "
          f"{sum(c['words'] for c in out_chapters)} думи, gantt {len(gantt)} реда")


if __name__ == "__main__":
    sys.exit(main())
