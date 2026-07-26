# Дисертация — Соларно адсорбционно охлаждане
**Статус към: 08.07.2026**

---

## 1. Обща информация

| | |
|---|---|
| **Докторант** | Асп. Парапанов |
| **Катедра** | Топло- и ядрена енергетика, ТУ-София |
| **Тема** | Соларно адсорбционно охлаждане |
| **Научен ръководител** | доц. Росен Цеков (r.tsekov@tu-sofia.bg) |
| **Краен срок на дисертацията** | Декември 2026 |
| **Следваща цел** | Article 1 — BULEF конференция, краен срок средата на юли 2026 |

---

## 2. Описание на системата

**Компоненти:**
- 20 плоски соларни колектора (~10 kW инсталирана мощност)
- Топлообменник SWEP B25×52 (интерфейс солар/чилър)
- 1000 L буфер за стратификация (два цилиндрични съда — hot buffer / cold buffer в новата CFD геометрия)
- Адсорбционен чилър InvenSor LTC 10 plus (10 kW, COP = 0.60 номинално, зеолит–вода)
- Сух охладител (recooling machine) — **предстои закупуване на нов**

**Три хидравлични кръга:**

| Кръг | T вход [°C] | T изход [°C] | v [m/s] |
|---|---|---|---|
| Задвижващ (Drive, III) | 72 | 66 | 0.398 |
| Рекулерен (Recooling, IV) | 27 | 31.5 | 0.811 |
| Охладен (Chilled, V) | 18 | 15 | 0.461 |

**Топлинни товари:**
- Q_gen = 16.67 kW
- Q_abs = 26.65 kW
- Q_evap = 10.00 kW

---

## 3. Експериментален план (уточнен с доц. Цеков)

- **3 нива на подаване на топла вода към буфера** (3 холендъра без най-горния)
- **× 3 дебита**
- = **9 режима** общо

**Цел:** влияние на стратификацията в топлия буфер върху COP, температури и дебити.

---

## 4. Дисертационна структура

| Статия | Съдържание | Статус | Срок |
|---|---|---|---|
| **Article 1** | Математичен модел | **Приоритет — draft завършен** | Средата на юли 2026 (BULEF) |
| **Article 2** | CFD виртуален прототип | Преместена | Декември 2026 |

Article 2 е преместена за декември, тъй като реалните измервания изискват нов сух охладител, който все още не е закупен.

---

## 5. Article 1 — статус

- ✅ Завършен draft: 6 секции, 7 референции, BULEF формат
- ✅ Прилагани корекции: терминологично несъответствие η₀/η_c, грешен subscript Q_solar, нотация на площ A_c
- 📄 Изходен файл: `Article1_Solar_Adsorption_Cooling_CORRECTED.docx`
- **Оставащо:** финална проверка преди подаване към BULEF (срок средата на юли — **спешно, до 1-2 седмици**)

---

## 6. CFD проект — 2-buffer stratification модел

### 6.1 Обща информация

- **Стартиран:** 03.07.2026, заменя всички по-стари геометрии (старата 10-телесна `Geom.scdocx` е архивирана, не се използва)
- **Геометрия:** Две цилиндрични буферни тела в SpaceClaim — HOT buffer (десен), COLD buffer (ляв)
- **Активен файл:** `Asparuh_extendedIN_OUTlets.scdocx`
- **Работна папка:** `C:/Users/aspar/Documents/Rocky/20260629/`
- **Fluid зони:** `hw`, `cw`
- **8 гранични зони:**

| Зона | Тип | Позиция | Роля |
|---|---|---|---|
| `hw_ret` | velocity-inlet | горе | от генератора на чилъра |
| `hw_sup` | pressure-outlet | долу | към генератора |
| `down_inlet` / `mid_inlet` / `up_inlet` | velocity-inlet | странично, 3 нива | соларно зареждане |
| `cw_ret` | velocity-inlet | горе | от изпарителя |
| `cw_sup` | pressure-outlet | долу | към изпарителя |
| `cw_outlet` | pressure-outlet | странично | към консуматора |

### 6.2 Хронология на CFD работата

**03–06.07.2026 — Първи mesh цикъл (291,078 клетки)**
- Local sizing (boi-1, 3mm/1.2 growth на hotbuffersupply) реши min quality от 0.020 → 0.762
- Fluent Setup завършен: Transient, Energy ON, k-ω SST, water-liquid
- Всички Named Expressions дефинирани (виж т. 6.4)
- Run 7200s — идентифицирани критични проблеми:
  - Uniform 300K initial conditions (Patch не приложен)
  - Нулев mass flow на всички solar charging inlets
  - **Материал зададен като air вместо water-liquid** → 800× грешка в mass flow
  - COP начална стойност -0.246 (артефакт на екстраполация извън дефинирания обхват)

**07.07.2026 — Втори цикъл (944,756 клетки), решени критични проблеми**
- Геометрична поправка: `hw_sup` изходна тръба удължена с ~150mm (фикс за reversed flow)
- BL (12 слоя, aspect-ratio 5, growth 1.2) приложени само върху `hw` region
- Коригирани реални площи на зоните чрез Surface Integrals (номиналните диаметри по чертеж се оказаха ненадеждни, разлики до +24.5%)
- Коригирани типове на граници (bяха разменени спрямо плана)
- Финализирани BC стойности и Named Expressions за скорости

**08.07.2026 (сутрин) — Симулация 300 timesteps, диагностика**
- Открит критичен проблем: **zone 8601 = `cold_buffer` (SOLID)**, не fluid
- Mesh Quality: **Minimum Orthogonal Quality = 0.0753**, **Maximum Aspect Ratio = 106.0** (cell 12110, zone 8601)
- Contour на температура показа uniform тъмно поле (8–585K обхват) → Patch вероятно не е бил приложен правилно
- "temperature limited to 1.000000e+00" се повтаря на всеки timestep до края на 300s run — не преходен, а траен проблем

**08.07.2026 (следобед) — Mesh поправка на `cold_buffer`, множество опити**

| Опит | Настройки | Резултат |
|---|---|---|
| 1 | curvature-1 sizing, MinSize 3mm, MaxSize 59.23mm, приложен върху ВСИЧКИ 6 solid зони | ❌ 12,129,702 faces — license crash |
| 2 | Add Boundary Layers, Use Size Field = Yes | ❌ Пак license crash (node 3: 149,725 cells) |
| 3 | Use Size Field = No, Buffer Layers = 4 | ❌ Пак license crash (node 3: 149,659 cells) |
| 4 | Local sizing коригиран: MaxSize 10mm (вместо 59mm), scope 6-те solid зони | ✅ **Surface mesh: 915,540 faces, 0 skewed cells, max skewness 0.676; cold_buffer max skewness паднал от 0.799 → 0.468** |
| 5 | Volume mesh опит — открит дублиран BL (`aspect-ratio_1` + `aspect-ratio_2`, и двата на `cw`+`hw`) | ❌ Overflow, дублиране идентифицирано и премахнато |
| 6 | Volume mesh, Buffer Layers = 3, Octree/Boundary Ratio = 2.5 | ❌ License crash (node 3: 149,231 cells — почти идентично на опит 2/3) |
| 7 | Идентична конфигурация повторена | ❌ Идентичен резултат — настройките не се записват между опитите |

**Извод от следобедната сесия:** Surface mesh (915,540 faces) е валиден и запазен. Volume mesh overflow-ът произлиза от базовата hexcore плътност на `cw`+`hw` заедно с BL/Buffer Layers, не от local sizing-а на solid зоните, който вече е коригиран успешно.

### 6.3 Оставащо за следваща сесия (конкретен план)

1. Зареди запазения surface mesh (915,540 faces, потвърден чист)
2. В **Generate the Volume Mesh** панела:
   - Buffer Layers: **3 → 1**
   - Octree/Boundary Size Ratio: **2.5 → 4.0**
   - Натисни **Update** и потвърди стойностите са се записали, преди Generate
3. Ако пак overflow: раздели volume mesh генерирането — само `hw` първо (Enable Region Settings), провери cell count, после `cw` отделно
4. След успешен volume mesh под 1,048,576 клетки:
   - Mesh → Check → Quality на `cold_buffer` — цел: orthogonal quality >0.15–0.2, aspect ratio <20–30
5. Standard Initialization → Patch (hot buffer ~340K, cold buffer ~288K) **след** инициализация, не преди
6. Верификация чрез Temperature Contour — трябва ясно 340K/288K разделение, не uniform поле
7. Бърз тестов run (20–30 timesteps, 0.5s) за проверка дали "temperature limited... zone 8601" изчезва
8. При успех → пълен 9-режимен параметричен анализ (3 inlet нива × 3 дебита)

### 6.4 Named Expressions (потвърдени валидни)

```
pin_profile, tin_profile, tinlet_ramp (от модела на доц. Цеков)
Thw_sup_avg, Tcw_ret_avg
COP_expr — piecewise linear (InvenSor datasheet, Recooling=27°C):
  55°C→0.43, 60°C→0.55, 65°C→0.60, 70°C→0.60, 75°C→0.61
Qevap_expr = COP_expr × 16700[W]
Qgen_expr = Qevap_expr / COP_expr  (математически = const 16700W — декларирано допускане)
mdot_hw = 0.694[kg/s]
mdot_cw = 0.8056[kg/s]
v_hw_ret, v_cw_ret = mdot/(rho×реална_площ)
hw_ret_temp, cw_sup_temp — енергийни балансови формули
```

**Финални BC стойности:**
- `down_inlet`: v=0.398 m/s + T=tinlet_ramp; `mid_inlet`/`up_inlet`: v=0
- `hw_ret`: v=0.357 m/s, T=313.15K (40°C)
- `cw_ret`: v=0.414 m/s, T=288.15K (15°C)
- `hw_sup`: Gauge P=0, Backflow T≈333.15K (60°C)
- `cw_sup`: Gauge P=0, Backflow T≈288.15K (15°C)
- `cw_outlet`: Gauge P=0, Backflow T=293.15K (20°C)

---

## 7. Ключови уроци и принципи (кумулативни)

- **Material change изисква re-initialization:** смяна на cell zone материал само с Apply НЕ обновява density полето — задължителна повторна Standard Initialization
- **Qgen_expr математически се анулира** до константа 16700W независимо от COP — декларирано допускане за дисертацията
- **Fluent Named Expression синтаксис:** използвай `"Time"` (не "Flow Time"); композитни единици `[J/kg/K]` (не `[J/(kg K)]`); piecewise COP изисква `/1[K]` деление, не `[1/K]`
- **Reversed flow на pressure-outlets:** решава се с geometric extension ≈5×D в SpaceClaim
- **Student license лимит: 1,048,576 клетки/лица** (потвърдено, не 512k от стар документ)
- **Use Size Field = Yes** драстично увеличава cell count при широк local sizing scope — внимавай при комбиниране с местен sizing върху много зони
- **MaxSize ограничение е критично:** 59mm беше твърде хлабав таван, доведе до 12M+ faces; 10mm реши проблема при same MinSize/scope
- **Buffer Layers и Octree/Boundary Size Ratio** влияят директно на overflow дори без BL слоеве — базовата hexcore плътност на fluid зоните може сама да удари лимита
- **Дублирани BL definitions** (два aspect-ratio sub-tasks върху едни и същи региони) причиняват overflow — провери "Add in" scope-а на всяка BL стъпка внимателно
- **Fill tool е грешен метод** за извличане на fluid обеми от тръби — правилно: Pull → New Body
- **Старата 10-телесна геометрия (`Geom.scdocx`)** е архивирана — причина за overlapping faces бяха фантомни скици от Discovery моделиране, невидими за Geometry Check
- **Patch трябва да е СЛЕД Standard Initialization**, не преди — потвърждава се чрез Temperature Contour (ясно разделение 340K/288K очаквано, не uniform поле)

---

## 8. Актуализиран график

```
Юли 2026
├── 08–10 юли  │ Volume mesh фикс (Buffer Layers/Octree ratio настройка) — ПРИОРИТЕТ
├── 10–12 юли  │ Успешен volume mesh под лимита + quality проверка на cold_buffer
├── 12–14 юли  │ Correct Patch + инициализация + бърз тестов run (20-30 timesteps)
├── 14–15 юли  │ ⚠️ Article 1 финална проверка и подаване — BULEF СРОК
└── 15–31 юли  │ Начало на 9-режимния параметричен CFD анализ (ако mesh стабилен)

Август 2026
├── Пълни 9 параметрични run-а (3 inlet нива × 3 дебита)
├── Анализ на стратификация и влияние върху COP
└── Full-license лабораторна сесия (пълен тричивен модел, след 15 юли прозорец)

Септември 2026
├── Обработка на CFD резултати
├── Закупуване на нов сух охладител (административен процес, паралелно)
└── Начало на Article 2 draft (CFD резултати)

Октомври 2026
├── Реални измервания на площадката (след доставка на сух охладител)
└── Съпоставка CFD vs реални данни

Ноември 2026
├── Article 2 финализиране
└── Компилиране на дисертационен текст — всички глави

Декември 2026
├── Финална редакция на дисертацията
└── ⚠️ КРАЕН СРОК ЗА ДИСЕРТАЦИЯТА
```

**Критични рискове за графика:**
1. **BULEF срокът (средата на юли) е много близо** — volume mesh проблемът трябва да се реши до 1-2 дни, за да не отнеме време от финализирането на Article 1 (макар Article 1 да е математичен модел, независим от CFD статуса)
2. **Закупуването на сух охладител** е external dependency извън контрола на изследователския процес — трябва да стартира административно възможно най-рано, за да не блокира реалните измервания и Article 2
3. **Volume mesh overflow цикълът** (вече 7+ неуспешни опита) трябва да се разреши бързо, за да остане достатъчно време за пълния 9-режимен параметричен анализ преди август

---

## 9. Инструменти и ресурси

- **CFD:** ANSYS Fluent 2025 R2 (student license, лимит 1,048,576 клетки); SpaceClaim за геометрия; Fault-Tolerant Meshing workflow
- **Активни файлове:** `Asparuh_extendedIN_OUTlets.scdocx`; работна папка `C:/Users/aspar/Documents/Rocky/20260629/`
- **Референтен модел:** CFX стратификационен модел от доц. Цеков (6-годишен, само за топъл буфер — логиката се пренася, не геометрията)
- **Оборудване:** InvenSor LTC 10 plus datasheet (COP крива при Recooling=27°C)
- **Документи:** `Article1_Solar_Adsorption_Cooling_CORRECTED.docx`; `ResultsSIMULATION.xlsx`
- **Docx workflow:** `unzip` → `sed -i` на `word/document.xml` → `find -type l -delete` → `zip -Xr`; верификация с `pandoc -t markdown`

---

*Последна актуализация: 08.07.2026*
