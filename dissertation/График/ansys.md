# ANSYS Fluent — работен план

Текуща стъпка: 5

1. Лиценз грешка → решена :: Рано сутринта / университетски сървър уикенд
2. Fault-Tolerant workflow → установен :: Standalone Fluent Meshing, НЕ от Workbench
3. Overlapping (100, 2851, 1650) → решен :: Фантомни Curves изтрити → Geom_clean.dsco
4. Surface Mesh — 0 skewed cells :: Skewness 0.155 · 16 968 faces · отличен резултат
5. Overlapping (196, 2727, 1668) → в прогрес :: Discovery: измести HWreturn_HeatExchanger 1–2mm навътре → Geom_clean2.dsco → нов mesh
6. Volume Mesh → генерирай :: hexcore, Add BL: No, Use Size Field: No
7. Fluent Setup → 9 режима :: 14 BC дефинирани ✓ — готови за конфигурация
8. CFD runs + post-processing :: Резултати → Гл. 5 Резултати и обсъждане

## Правила (НИКОГА не нарушавай)
Add Boundary Layers → ВИНАГИ No · Capping стъпката → ПРОПУСНИ винаги · Use Size Field → No · Зареждай Geom_clean2.dsco (не оригинала) · Изтрий FM_Parapanov папката преди всеки старт

## Region settings
| Обект | Type | Extraction | Volume Fill |
| chilledwater_in | fluid | wrap | hexcore |
| chilledwater_out | fluid | wrap | hexcore |
| fluid-region-1 | fluid | wrap | hexcore |
| geom_clean2 | void | none | none |
| hw_heatexchanger | void | none | none |
| hwin_adsorption_chiller | void | none | none |
| hwreturn_adsorbtionchiller | void | none | none |
| hwreturn_heatexchanger | void | none | none |
| recool_in | fluid | wrap | hexcore |
| recool_out | fluid | wrap | hexcore |
| water_volume | fluid | wrap | hexcore |
