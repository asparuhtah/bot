# Fluent Meshing — Работен дневник
**Проект:** Дисертация — Слънчево адсорбционно охлаждане  
**Обект:** InvenSor LTC 10 plus  
**Геометрия:** `Geom.scdocx` / `Geom.dsco` — 10 тела, 14 Flow граници  
**Софтуер:** ANSYS 2025 R2 Student (лимит 512k клетки)  
**Работна папка:** `C:\Users\aspar\Documents\Rocky\20260426_files\`

---

## Хронология на сесиите

| Дата | Статус | Основен резултат |
|------|--------|-----------------|
| 26.04.2026 | ✗ | License error — лицензът е изтекъл в 19:28:44 |
| 14.05.2026 | ⚠️ | Surface mesh ✓ (576k faces, skewness 0.46) — Volume mesh БЛОКИРАН |
| 17.05.2026 | ⚠️ | Watertight изпробван (Join-Intersect + Interface Connect) — SIGSEGV. Истинска причина открита: фантомни скици в Water Volume около коляното на Recool |

---

## Геометрия — референция

### Компоненти
| Компонент | Описание | Роля |
|-----------|----------|------|
| Adsorbtion chiller | InvenSor LTC 10 plus | Основен обект |
| RecoolingMachine | Сух охладител | Граница на топлоотдаване |
| Heat Exchanger | Пластинчат топлообменник B25x52 | Интерфейс солар/чилър |
| HWreturn_HeatExchanger | Обратен кръг | Горещ кръг вход |
| part1–part10 bodies | 10 геометрични тела | Fluid/Solid домейни |

### Именовани граници (14 Flow BC в SpaceClaim)
| Граница | Тип BC | T [°C] | Дебит |
|---------|--------|--------|-------|
| Flow Inlet 1 | velocity-inlet | 72 | 2500 l/h — Drive кръг III |
| Flow Outlet 2 | pressure-outlet | 66 | Изход Drive |
| Flow Outlet 3 | pressure-outlet | — | Вторичен изход |
| Flow Inlet 4 | velocity-inlet | 27 | 5100 l/h — Recooling кръг IV |
| Flow Outlet 5 | pressure-outlet | 31.5 | Изход Recooling |
| Flow Inlet 6 | velocity-inlet | 18 | 2900 l/h — Chilled кръг V |
| Flow Outlet 7 | pressure-outlet | 15 | Изход Chilled |
| Flow Inlet 8, 9 | velocity-inlet | 70–75 | Слънчев кръг I/II |
| Flow Outlet 10–14 | pressure-outlet | — | Останали изходи |

### Гранични условия (скорости)
| Кръг | T вход [°C] | v [m/s] | T изход [°C] | BC тип |
|------|-------------|---------|--------------|--------|
| Drive (III) — hwreturn | 72 | 0.398 | 66 | velocity-inlet / pressure-outlet |
| Recooling (IV) — recool | 27 | 0.811 | 31.5 | velocity-inlet / pressure-outlet |
| Chilled (V) — chilledwater | 18 | 0.461 | 15 | velocity-inlet / pressure-outlet |

---

## Сесия 26.04.2026 — License Error

### Проблем
```
Unexpected license problem; exiting.
```
Fluent стартирал успешно, свързал се с лиценз сървъра, но лицензът е изтекъл/зает от друг процес в **19:28:44 на 26.04.2026**.

### Причина
Университетски лиценз — пиков час. НЕ е проблем с геометрията.

### Решение
- Работи в непикови часове (рано сутринта, събота/неделя)
- Workbench → Help → About → License Manager за проверка
- При нужда: свържи се с IT на ТУ-София

---

## Сесия 14.05.2026 — Overlapping Faces

### Workflow използван
**Fault-Tolerant Meshing** (Standalone Fluent Launcher → Meshing Mode)

### Установен работещ workflow (стъпка по стъпка)
1. Standalone Fluent Launcher → Meshing mode → зареди `Geom.scdocx`
2. **Describe Geometry** → `Internal flow through the object` | Create large caps: `Yes`
3. **Enclose Fluid Regions (Capping)** → **ПРОПУСКА СЕ** (не е необходима)
4. **Identify Regions** → само `water_volume` → fluid-region-1
5. **Define Leakage Threshold** → `No`
6. **Update Region Settings** → 7 fluid, 3 void (виж таблица)
7. **Generate Surface Mesh** → skewness threshold `0.8`
8. **Add Boundary Layers** → **NO** ← задължително, иначе baffle грешка
9. **Generate Volume Mesh** → tet | 20 mm | Use Size Field: `No`

### Update Region Settings — правилна конфигурация
| Обект | Type | Extraction | Volume Fill |
|-------|------|------------|-------------|
| chilledwater_in | fluid | wrap | hexcore |
| chilledwater_out | fluid | wrap | hexcore |
| fluid-region-1 | fluid | wrap | hexcore |
| geom | void | none | none |
| hw_heatexchanger | void | none | none |
| hwin_adsorption_chiller | void | none | none |
| hwreturn_adsorbtionchiller | fluid | wrap | hexcore |
| hwreturn_heatexchanger | fluid | wrap | hexcore |
| recool_in | fluid | wrap | hexcore |
| recool_out | fluid | wrap | hexcore |
| water_volume | fluid | wrap | hexcore |

### Постигнато
- ✅ Surface Mesh: **576 260 faces**, averaged-skewness **0.46**, max 0.99, **0 skewed cells**
- ✅ Всички 10 fluid зони разпознати коректно
- ✅ Overlapping точката локализирана: `(100.118967, 2851.562650, 1650.617237) mm`

### Грешка — непреодоляна
```
Found overlapping faces sharing edge bn64081-bn64096 (100.118967 2851.562650 1650.617237).
Error at Node 0: Fix the overlaps along multi-connections at (100.118967 2851.562650 1650.617237) and try again.
Volume mesh failed.
```

**Диагноза:**
- Зоната е **Water Recool IN / Water Recool OUT** при сухия охладител (Ø35 mm тръби, разстояние ~100 mm)
- Node numbers се менят между сесиите — **координатата е винаги една и съща**
- SpaceClaim → Проверка: **"Не са намерени проблеми"** — геометрията е OK
- Проблемът е в **wrapping алгоритъма** — генерира overlapping node при тесен wrapping около Recool тръбите

---

## ⚠️ КРИТИЧНО ОТКРИТИЕ — 17.05.2026 — Истинската причина за overlapping

> **Геометрията е SACRED — не се пипа!**

### Диагноза (открита самостоятелно на 17.05)
Координатата `(100.118967, 2851.562650, 1650.617237) mm` **е вътре във водния обем**, много близо до **коляното на Recool тръбата**. Няма геометричен проблем с тръбите — те не се пресичат и не се докосват.

**Истинската причина:** В тази точка вероятно има **остатъчни "фантомни" скици или помощни чертички** от моделирането в Discovery — **не се виждат визуално**, но Fluent Meshingги засича като mesh entity и се обърква при wrapping/topology операции.

### Последствия
- Fault-Tolerant wrapping → overlapping faces грешка на тази точка
- Watertight Join-Intersect → безкрайно зациклане + SIGSEGV
- Watertight Interface Connect → SIGSEGV segmentation violation
- SpaceClaim Geometry Check → **"Не са намерени проблеми"** (фантомните обекти не се засичат)

### Следващи стъпки за почистване
1. Отвори `Geom.dsco` в **Discovery**
2. В дървото → разгъни `Water Volume` → провери дали има скрити скици/curves/planes в зона `(100, 2851, 1650)`
3. В Discovery: **Inspect → Show Hidden** или **View → Show All**
4. Провери `Curves` обекта в дървото на SpaceClaim — видя се при предишно отваряне
5. Изтрий всички помощни скици и curves в проблемната зона
6. Запази като нов файл `Geom_clean.dsco`

---

## Сесия 17.05.2026 — Опити за решение на overlapping

### Важни бележки преди старт (всяка сесия)
> ⚠️ Изтрий `FM_Parapanov_XXXXX` от `dp0\Geom\DM\` преди всеки старт!

| Правило | Стойност |
|---------|----------|
| Add Boundary Layers | ВИНАГИ **No** |
| Use Size Field | **No** в Generate Volume Mesh |
| Capping стъпката | ВИНАГИ се пропуска |
| Лиценз | Университетски сървър — работи рано сутринта / събота / неделя |

---

### Опция А — По-фин Surface Mesh (Min Size / Size Ratio)
**Идея:** По-финото discretization при wrapping може да елиминира overlapping node.  
**Стъпки:**
- Generate Surface Mesh → Advanced Options
- Намали Octree/Boundary Size Ratio от `2.5` на `1.0`
- Или намали Min Size

**Резултат (14.05):** — не е изпробвана  
**Резултат (17.05):** —

---

### Опция Б — Local Sizing около проблемната зона
**Идея:** Принуди по-фин mesh точно в координата `(100, 2851, 1650)`.  
**Стъпки:**
- Add Local Sizing → Body of Influence
- Избери обем около координатата
- Target Size: `3 mm`

**Резултат (14.05):** — не е изпробвана  
**Резултат (17.05):** —

---

### Опция В — Gap Fill Factor в Describe Geometry
**Идея:** Намали агресивността на wrapping около тесни пролуки.  
**Стъпки:**
- Describe Geometry → Gap Fill Factor: `0.5` → `0.1`

**Резултат (14.05):** — не е изпробвана  
**Резултат (17.05):** —

---

### Опция Г — Геометрична корекция в SpaceClaim
**Идея:** Ако Recool тръбите се докосват или имат касаещи се faces, wrapping-ът се обърква.  
**Стъпки:**
- Отвори `Geom.scdocx` в SpaceClaim
- Измери разстоянието между Recool IN и Recool OUT тръбите в зона `(100, 2851, 1650)`
- Ако < 5 mm: раздалечи тръбите с 5–10 mm
- Провери Share Topology → Merge между телата в проблемната зона

**Резултат (14.05):** — не е изпробвана  
**Резултат (17.05):** —

---

### Опция Д — Watertight Geometry Workflow
**Идея:** Watertight workflow не използва wrapping алгоритъм — елиминира причината за overlapping-а директно.  
**Изисквания:** Named Selections трябва да са дефинирани в SpaceClaim (Groups панел — 14-те Flow граници).

**Резултат (17.05):** ✗ FAIL
- SpaceClaim Groups панел е празен — няма Named Selections
- Discovery `.dsco` файлът носи материалите но не и Named Selections на faces
- Join-Intersect → безкрайно зациклане (20+ мин) + `zone recool_out-11 connected to a volume mesh` грешка
- Interface Connect → SIGSEGV segmentation violation
- Apply Share Topology е **задължителна** стъпка в Watertight — не може да се пропусне

---

### ⭐ КРИТИЧНО ОТКРИТИЕ — Фантомни скици (17.05)

**Геометрията е SACRED — не се пипа!**

Координатата `(100.118967, 2851.562650, 1650.617237) mm` е вътре във водния обем, много близо до коляното на Recool тръбата. В `Geom.dsco` имаше **`Curves` обект** в дървото на Discovery — остатъчни фантомни скици от моделирането. SpaceClaim Geometry Check не ги засича, но Fluent Meshing се обърква при wrapping/topology операции.

**Действие:** Изтрити всички Curves → запазено като `Geom_clean.dsco`

**Резултат:** Overlapping на `(100, 2851, 1650)` изчезна! ✅

---

### Опция Е — Fault-Tolerant с `Geom_clean.dsco` + коригирани Region Settings

**Ключово откритие за геометрията:**
Геометрията е **опростена** — няма детайлни канали на топлообменника. Всички корпуси (топлообменници, чилър, сух охладител) са solid кутии. Водните обеми опират до стените им. Следователно само водните обеми трябва да са `fluid` — всичко останало е `void`.

**Правилна конфигурация Update Region Settings:**
| Обект | Type | Extraction | Volume Fill |
|-------|------|------------|-------------|
| chilledwater_in | fluid | wrap | hexcore |
| chilledwater_out | fluid | wrap | hexcore |
| fluid-region-1 | fluid | wrap | hexcore |
| geom_clean | void | none | none |
| hw_heatexchanger | void | none | none |
| hwin_adsorption_chiller | void | none | none |
| hwreturn_adsorbtionchiller | void | none | none |
| hwreturn_heatexchanger | void | none | none |
| recool_in | fluid | wrap | hexcore |
| recool_out | fluid | wrap | hexcore |
| water_volume | fluid | wrap | hexcore |

**Surface Mesh резултат:**
- ✅ 0 skewed cells
- ✅ Averaged skewness: **0.155** — най-добрият досега
- ✅ 16 968 faces

**Volume Mesh резултат:** ✗ FAIL — нова overlapping грешка:
```
Found overlapping faces sharing edge bn61412-bn61433 (196.038077 2727.013145 1668.109319)
```
Зоната е при **`HWreturn_HeatExchanger`** — водният обем се допира нулево до стената на топлообменника.

**Следваща стъпка:** В Discovery → избери `HWreturn_HeatExchanger` → Pull → измести с **1-2 mm** навътре → запази като `Geom_clean2.dsco`

---

## Чести проблеми и решения (обобщение)

| Проблем | Причина | Решение |
|---------|---------|---------|
| License error | Изтекъл/зает лиценз | Работи рано сутринта или уикенд |
| Overlapping faces @ (100, 2851, 1650) | Fault-Tolerant wrapping около Recool тръби | Виж Опции А–Д по-горе |
| Baffle грешка при Volume Mesh | Add Boundary Layers = Yes | Задължително **No** |
| Divergence след 10–20 iter. | Лоши BC или лош mesh | Намали URF на Pressure до 0.2 |
| Energy не конвергира | Лош mesh до стените | Провери inflation layers — y+ < 5 |
| Free faces в mesh | Непокриващи се части | Share Topology в SpaceClaim |
| Memory error | Твърде много клетки (>512k) | Увеличи Max Size с 30% |
| T outlet = T inlet | Energy model е OFF | Models → Energy → ON |
| Backflow warning | Рекапиция на поток | Добави 0.5D extension tube на outlet-ите |

---

## Следващи стъпки след успешен Volume Mesh

1. **Fluent Setup** → Solver: Pressure-Based | Steady | Energy: ON | k-ω SST
2. **Материали:** Water (65°C, 27°C, 15°C), Steel, Силикагел
3. **Boundary Conditions:** 14 именовани граници → velocity-inlet / pressure-outlet
4. **Monitors:** T_outlet_drive, T_outlet_recool, T_outlet_chilled, COP
5. **Валидация с Excel:** Qgen=16.67 kW, Qabs=26.65 kW, Qevap=10.00 kW, COP=0.60
6. **Параметричен анализ:** T_inlet_drive от 60 до 85°C → COP крива
7. **Mesh Independence Study** (изисква се за публикация)

---

*ТУ-София · Дисертация — Слънчево адсорбционно охлаждане · 2026*  
*Последна актуализация: 17.05.2026*
