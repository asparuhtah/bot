flowchart TD

    %% --- Температури (BC) ---
    Thw_ret["Thw_ret_avg\nAreaAve(T, hw_ret)"]
    Thw_sup["Thw_sup_avg\nAreaAve(T, hw_sup)"]
    Tcw_ret["Tcw_ret_avg\nAreaAve(T, cw_ret)"]
    Tcw_sup["Tcw_sup_avg\nAreaAve(T, cw_sup)"]

    %% --- Масови дебити ---
    mdot_hw["mdot_hw = 0.694 kg/s"]
    mdot_cw["mdot_cw = 0.8056 kg/s"]

    %% --- Топлинни потоци ---
    Qgen["Qgen_CFD = mdot_hw·4182·(Thw_ret - Thw_sup)"]
    Qevap["Qevap_CFD = mdot_cw·4182·(Tcw_ret - Tcw_sup)"]

    %% --- Clamp и COP_expr ---
    Qgen_safe["Qgen_CFD_safe = MAX(Qgen_CFD, 8000 W)"]
    COPexpr["COP_expr\npiecewise(Thw_sup_avg)"]

    %% --- Target evaporator load ---
    Qevap_target["Qevap_target = COP_expr·Qgen_CFD_safe"]

    %% --- COP_CFD ---
    COP_CFD["COP_CFD = Qevap_CFD / Qgen_CFD_safe"]

    %% --- Source Terms ---
    ST_cw1["cw1 Energy Source\n-Qevap_target / 0.07999603 m³"]
    ST_hw1["hw1 Energy Source\n-Qgen_CFD_safe / 0.076104197 m³"]

    %% --- Connections ---
    Thw_ret --> Qgen
    Thw_sup --> Qgen
    mdot_hw --> Qgen

    Tcw_ret --> Qevap
    Tcw_sup --> Qevap
    mdot_cw --> Qevap

    Qgen --> Qgen_safe
    Thw_sup --> COPexpr

    Qgen_safe --> Qevap_target
    COPexpr --> Qevap_target

    Qevap --> COP_CFD
    Qgen_safe --> COP_CFD

    Qevap_target --> ST_cw1
    Qgen_safe --> ST_hw1

    %% --- Class assignment ---
    class Thw_ret,Thw_sup,Tcw_ret,Tcw_sup bc;
    class mdot_hw,Qgen,Qgen_safe,COPexpr,ST_hw1 hot;
    class mdot_cw,Qevap,Qevap_target,ST_cw1 cold;
    class COP_CFD neutral;

    %% --- Styles ---
    classDef hot fill=#ffcccc,stroke=#cc0000,stroke-width=2px;
    classDef cold fill=#cce5ff,stroke=#0056b3,stroke-width=2px;
    classDef bc fill=#e6ffe6,stroke=#339933,stroke-width=2px;
    classDef source fill=#ffe5cc,stroke=#ff8800,stroke-width=2px;
    classDef neutral fill=#f2f2f2,stroke=#666666,stroke-width=2px;

    %% Mark source nodes explicitly
    class ST_cw1,ST_hw1 source;
