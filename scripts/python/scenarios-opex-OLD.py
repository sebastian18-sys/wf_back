import re
import numpy as np
import pandas as pd
import cvxpy as cp
from pathlib import Path
from datetime import date, datetime
import os
import json
import sys

# BASE DIR
BASE_DIR = "./scripts/data/opex"

# File scenarios opex is the same folder
INPUT_XLSX = BASE_DIR + "/" + "Escenarios_OPEX.xlsx"
OUTPUT_XLSX = "Escenarios_out.xlsx" 

# Criterios de REDUCCIÓN (Δ área = ΣAcum) 
REDUCCION_BY_SHEET = {
    "Macro": 1_500_000,
    "Expansiones": 300_000,
    "Vulnerabilidad": 10_000,
    "Banda 3.5 GHZ": 469_000
}

ONLY_REDUCE = False  # True => no permitir Q > Q_base por (p,m).
BETA_S2 = 0.0        # suavidad temporal en S2 (0 desactiva)
LATE_BIAS_S3 = 1.0   # intensidad del sesgo hacia meses tardíos en S3
LAMBDA_S3 = 1e-2     # regularización para no alejarse demasiado de Q_base en S3
MONTH_PAT = re.compile(r"^(ene|feb|mar|abr|may|jun|jul|ago|set|sep|oct|nov|dic)", re.I)

# ======================= UTILS ========================= #
def clean_numeric(x):
    if pd.isna(x): return 0.0
    if isinstance(x, str):
        s = x.strip()
        if s in ("", "-"): return 0.0
        if s.endswith("%"):
            return float(s.replace("%","").replace(" ",""))/100.0
        return float(s.replace(",", ""))
    return float(x)

def _is_month_header(col) -> bool:
    if isinstance(col, (pd.Timestamp, datetime, date)): return True
    s = str(col).strip()
    if s.lower() in ("total", "tiempo"): return False
    return bool(MONTH_PAT.search(s))



def find_month_cols(df, driver_hint="driver"):
    cols = list(df.columns)
    month_cols = [c for c in cols if _is_month_header(c)]
    if len(month_cols) >= 12:
        ordered = [c for c in cols if c in month_cols][:12]
        return ordered
    # Fallback posicional
    drv_idx = None
    for i, c in enumerate(cols):
        if str(c).strip().lower().startswith(driver_hint):
            drv_idx = i; break
    if drv_idx is None:
        raise ValueError("No se encontró columna Driver.")
    cand = []
    for c in cols[drv_idx+1:]:
        s = str(c).strip().lower()
        if s in ("total","tiempo"): continue
        cand.append(c)
        if len(cand) == 12: break
    if len(cand) != 12:
        raise ValueError("No se detectan 12 columnas de meses (Ene..Dic).")
    return cand

def parse_sheet(df_raw):
    df = df_raw.copy()
    proj_col = next((c for c in df.columns if str(c).strip().lower().startswith("proyecto")), None)
    drv_col  = next((c for c in df.columns if str(c).strip().lower().startswith("driver")), None)
    inc_col  = next((c for c in df.columns if str(c).strip().lower().startswith("incidencia")), None)
    if proj_col is None or drv_col is None:
        raise ValueError("Faltan columnas 'Proyecto' o 'Driver Fcst'.")

    month_cols = find_month_cols(df)

    df = df[df[proj_col].notna()].copy()
    df = df[~df[proj_col].astype(str).str.upper().str.contains("TOTAL")]

    df[drv_col] = df[drv_col].apply(clean_numeric)
    if inc_col is None:
        df["__inc__"] = 1.0; inc_col = "__inc__"
    else:
        df[inc_col] = df[inc_col].apply(clean_numeric)
        df.loc[df[inc_col] > 1.0, inc_col] = df[inc_col] / 100.0

    for c in month_cols: df[c] = df[c].apply(clean_numeric)

    proyectos = df[proj_col].astype(str).tolist()
    drivers   = df[drv_col].astype(float).to_numpy()
    incidencia= df[inc_col].astype(float).to_numpy()
    drv_eff   = drivers * incidencia
    Q_base    = df[month_cols].astype(float).to_numpy()  # P×12
    meses     = [str(c) for c in month_cols]
    return proyectos, meses, Q_base, drivers, incidencia, drv_eff

def montos_y_acums(Q, drv_eff):
    Q = np.asarray(Q, float); drv_eff = np.asarray(drv_eff, float).reshape(-1)
    P, M = Q.shape
    if M != 12: raise ValueError("Se esperan 12 meses.")
    if drv_eff.shape[0] != P: raise ValueError("drv_eff debe tener longitud P.")
    m = (Q.T * drv_eff).T.sum(axis=0)      # montos por mes
    L = np.tril(np.ones((12,12)))
    A = L @ m                              # acumulado por mes
    return m, A


def integerize_Q(Q_float, row_totals_int):
    Qf = np.asarray(Q_float, float)
    P, M = Qf.shape
    Qt = np.floor(Qf + 0.5).astype(int)       # round half-up
    frac = Qf - np.floor(Qf)                  # para repartir el residuo si hiciera falta
    for p in range(P):
        target = int(row_totals_int[p])
        diff = target - int(Qt[p].sum())
        if diff > 0:
            order = np.argsort(frac[p])[::-1]
            for j in order[:diff]:
                Qt[p, j] += 1
        elif diff < 0:
            order = np.argsort(frac[p])
            need = -diff
            for j in order:
                take = min(need, Qt[p, j])
                Qt[p, j] -= take
                need -= take
                if need == 0:
                    break
        Qt[p] = np.maximum(Qt[p], 0)
    return Qt


# ======================= SCENARIOS ========================= #
def escenario1_proporcional_tardio(Q_base, backload_ratio=0.25):
    P, M = Q_base.shape
    Q = Q_base.copy().astype(float); H = M//2
    for p in range(P):
        early = Q[p,:H].sum(); move = early*backload_ratio
        if early > 0 and move > 0:
            frac_e = Q[p,:H]/early
            Q[p,:H] -= move*frac_e
            late = Q[p,H:].sum()
            frac_l = (Q[p,H:]/late) if late>0 else np.ones(M-H)/(M-H)
            Q[p,H:] += move*frac_l
    return np.maximum(Q, 0.0)
    

def solve_q_with_constraints(Q_base, drv_eff, area_obj=None,
                             objective_kind="shape", beta=0.0,
                             late_bias=1.0, lam_reg=1e-2, only_reduce=False):
    P, M = Q_base.shape
    Q = cp.Variable((P, M), nonneg=True)
    totals = Q_base.sum(axis=1)
    cons = [cp.sum(Q[p,:]) == totals[p] for p in range(P)]
    if only_reduce: cons += [Q <= Q_base]

    m = cp.sum(cp.multiply(Q, drv_eff[:,None]), axis=0)
    L = np.tril(np.ones((M,M)))
    A = L @ m
    A_base = L @ ((Q_base.T * drv_eff).T.sum(axis=0))

    if objective_kind in ("shape","late_cost"):
        if area_obj is None: raise ValueError("area_obj requerido.")
        cons += [cp.sum(A) == area_obj]

    if objective_kind == "shape":
        obj = cp.Minimize(cp.sum_squares(A - A_base) + beta*cp.sum_squares(Q[:,1:] - Q[:,:-1]))
    elif objective_kind == "late_cost":
        w_month = cp.Parameter(M, value=np.linspace(1.0, 2.0, M))
        obj = cp.Minimize(late_bias*(w_month @ m) + lam_reg*cp.sum_squares(Q - Q_base))
    elif objective_kind == "min_area":
        obj = cp.Minimize(cp.sum(A))
    else:
        raise ValueError("objective_kind inválido.")

    prob = cp.Problem(obj, cons)
    solved = False
    for solver in [cp.OSQP, cp.ECOS, cp.SCS]:
        try:
            prob.solve(solver=solver, verbose=False)
            if prob.status in ("optimal","optimal_inaccurate"): solved=True; break
        except Exception: pass
    if not solved or Q.value is None:
        return None, None, prob.status

    Q_opt = np.array(Q.value, float)
    area  = float(np.sum(L @ ((Q_opt.T * drv_eff).T.sum(axis=0))))
    return Q_opt, area, prob.status


def procesa_hoja(sheet_name, df_raw, reduccion_obj):
    try:
        # Parseo base
        proyectos, meses, Q_base, drivers, incidencia, drv_eff = parse_sheet(df_raw)
        m_base, A_base = montos_y_acums(Q_base, drv_eff)
        area_base = float(A_base.sum())
        area_obj  = max(0.0, area_base - float(reduccion_obj))
        row_totals_int = np.rint(Q_base.sum(axis=1)).astype(int)

        # S1 (heurístico)
        Q_s1 = escenario1_proporcional_tardio(Q_base, backload_ratio=0.25)
        Q_s1_i   = integerize_Q(Q_s1,   row_totals_int)
        m_s1, A_s1 = montos_y_acums(Q_s1_i, drv_eff)

        # Smax (límite)
        Q_smax, area_min, _ = solve_q_with_constraints(
            Q_base, drv_eff, area_obj=None, objective_kind="min_area", only_reduce=ONLY_REDUCE
        )
        if Q_smax is None: Q_smax, area_min = Q_base.copy(), area_base

        # Target (si pides más que el máximo reducible, usar límite)
        area_target = area_obj if area_obj >= area_min - 1e-3 else area_min

        # S2 (forma)
        Q_s2, _, _ = solve_q_with_constraints(
            Q_base, drv_eff, area_obj=area_target, objective_kind="shape",
            beta=BETA_S2, only_reduce=ONLY_REDUCE
        )
        if Q_s2 is None: Q_s2 = Q_s1.copy()
        Q_s2_i = integerize_Q(Q_s2,   row_totals_int)
        m_s2, A_s2 = montos_y_acums(Q_s2_i, drv_eff)

        # S3 (tardío+costo)
        Q_s3, _, _ = solve_q_with_constraints(
            Q_base, drv_eff, area_obj=area_target, objective_kind="late_cost",
            late_bias=LATE_BIAS_S3, lam_reg=LAMBDA_S3, only_reduce=ONLY_REDUCE
        )
        if Q_s3 is None: Q_s3 = Q_s1.copy()
        Q_s3_i   = integerize_Q(Q_s3,   row_totals_int)
        m_s3, A_s3 = montos_y_acums(Q_s3_i, drv_eff)


        

        # Enterizar todos los Q antes de calcular montos/acumulados y exportar
        Q_base_i = integerize_Q(Q_base, row_totals_int)  # por si en base hubiera floats
        # Q_s1_i   = integerize_Q(Q_s1,   row_totals_int)
        # Q_s2_i   = integerize_Q(Q_s2,   row_totals_int)
        # Q_s3_i   = integerize_Q(Q_s3,   row_totals_int)

        # Acumulados de cantidades (Fig. 1)
        # def acc_from_df(df):
        #     return np.cumsum(df.sum(axis=0).to_numpy()).astype(int)

        def acc_counts(Q_int):
            qtot = Q_int.sum(axis=0)          # ya es entero
            acc  = np.cumsum(qtot).astype(int)
            acc[-1] = int(qtot.sum())         # por si acaso
            return acc

        idx = pd.Index(proyectos, name="Proyecto")
        # df_Q_base = pd.DataFrame(Q_base, index=idx, columns=meses)
        # df_Q_s1   = pd.DataFrame(np.round(Q_s1,2), index=idx, columns=meses)
        # df_Q_s2   = pd.DataFrame(np.round(Q_s2,2), index=idx, columns=meses)
        # df_Q_s3   = pd.DataFrame(np.round(Q_s3,2), index=idx, columns=meses)

        # Montos y acumulados SIEMPRE con enteros
        # m_base, A_base = montos_y_acums(Q_base_i, drv_eff)
        # m_s1,   A_s1   = montos_y_acums(Q_s1_i,   drv_eff)
        # m_s2,   A_s2   = montos_y_acums(Q_s2_i,   drv_eff)
        # m_s3,   A_s3   = montos_y_acums(Q_s3_i,   drv_eff)
        
        # Tablas de detalle (escenarios) con enteros
        df_Q_base = pd.DataFrame(Q_base_i, index=idx, columns=meses)
        df_Q_s1   = pd.DataFrame(Q_s1_i,   index=idx, columns=meses)
        df_Q_s2   = pd.DataFrame(Q_s2_i,   index=idx, columns=meses)
        df_Q_s3   = pd.DataFrame(Q_s3_i,   index=idx, columns=meses)


        Qacc_base = acc_counts(Q_base_i)
        Qacc_s1   = acc_counts(Q_s1_i)
        Qacc_s2   = acc_counts(Q_s2_i)
        Qacc_s3   = acc_counts(Q_s3_i)

        # df_Q_acc = pd.DataFrame({
        #     "Mes": meses,
        #     "Inicial": acc_from_df(df_Q_base),
        #     "Escenario 1": acc_from_df(df_Q_s1),
        #     "Escenario 2": acc_from_df(df_Q_s2),
        #     "Escenario 3": acc_from_df(df_Q_s3),
        # })

        df_Q_acc = pd.DataFrame({
            "Mes": meses,
            "Inicial": Qacc_base,
            "Escenario 1": Qacc_s1,
            "Escenario 2": Qacc_s2,
            "Escenario 3": Qacc_s3,
        })

        # Detalle (Fig. 3)
        detalle = {
            "Inicial": df_Q_base,
            "Escenario 1": df_Q_s1,
            "Escenario 2": df_Q_s2,
            "Escenario 3": df_Q_s3,
        }

        # Montos totales anuales (Fig. 2)
        area_totales = {
            "Inicial": int(A_base.sum()),
            "Escenario 1": int(A_s1.sum()),
            "Escenario 2": int(A_s2.sum()),
            "Escenario 3": int(A_s3.sum()),
        }
    
        return {
            "meses": meses,
            "Q_acc": df_Q_acc,
            "detalle": detalle,
            "areas_totales": area_totales,   # <--- antes era montos_totales
        }

    except Exception as e:
        # Nunca retornar None: entrega un paquete vacío para que el main lo salte
        print(f"[{sheet_name}] ERROR en procesa_hoja: {e}")
        return {}


# HELPERS TO JSON
# -------- helpers de serialización --------
def to_json_safe(o):
    """Convierte numpy types a tipos nativos JSON."""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        # si es muy cercano a entero, redondear
        v = float(o)
        if abs(v - round(v)) < 1e-9:
            return int(round(v))
        return v
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    return str(o)

def force_int_if_numeric(s):
    """Castea a int toda columna numérica (sin tocar strings)."""
    if pd.api.types.is_numeric_dtype(s):
        # redondea a entero para evitar 63k vs 62.999, etc.
        return pd.to_numeric(s, errors="coerce").round().astype("Int64").astype(object).apply(lambda x: 0 if pd.isna(x) else int(x))
    return s

def df_to_records_int(df):
    # import pandas as pd, numpy as np
    dfx = df.copy()
    for c in dfx.columns:
        if pd.api.types.is_numeric_dtype(dfx[c]):
            dfx[c] = pd.to_numeric(dfx[c], errors="coerce").round().fillna(0).astype(int)
    if dfx.index.name or not isinstance(dfx.index, pd.RangeIndex):
        dfx = dfx.reset_index().rename(columns={"index": "Proyecto"} if "Proyecto" not in dfx.columns else {})
    return dfx.to_dict(orient="records")

# -------- ensamblador principal --------
def build_payload(q_acc_by_sheet, resumen_montos, detalles, tipo_resumen="montos"):
    # Q_Acumulado
    q_acc = []
    for prog, df in q_acc_by_sheet.items():
        cols = [c for c in ["Mes","Inicial","Escenario 1","Escenario 2","Escenario 3"] if c in df.columns]
        q_acc.append({"programa": prog, "filas": df_to_records_int(df[cols])})

    # Resumen
    # import pandas as pd
    df_res = pd.DataFrame(resumen_montos)
    if not df_res.empty:
        for c in df_res.columns:
            if c != "programa":
                df_res[c] = pd.to_numeric(df_res[c], errors="coerce").round().fillna(0).astype(int)
        if "Var_Esc1_vs_Base" not in df_res:
            df_res["Var_Esc1_vs_Base"] = df_res["inicial"] - df_res["escenario1"]
        if "Var_Esc2_vs_Base" not in df_res:
            df_res["Var_Esc2_vs_Base"] = df_res["inicial"] - df_res["escenario2"]
        if "Var_Esc3_vs_Base" not in df_res:
            df_res["Var_Esc3_vs_Base"] = df_res["inicial"] - df_res["escenario3"]
        resumen = {"tipo": tipo_resumen, "filas": df_to_records_int(df_res)}
    else:
        resumen = {"tipo": tipo_resumen, "filas": []}

    # Detalle_Proyectos
    det = []
    order = ("Inicial", "Escenario 1", "Escenario 2", "Escenario 3")
    for prog, scen_map in detalles.items():
        bloques = []
        for name in order:
            if name in scen_map:
                bloques.append({"nombre": name, "filas": df_to_records_int(scen_map[name])})
        det.append({"programa": prog, "escenarios": bloques})

    return {"Q_Acumulado": q_acc, "Resumen_Acumulados": resumen, "Detalle_Proyectos": det}

# ======================= EXPORT A 3 HOJAS =======================
def main():
    book = pd.read_excel(INPUT_XLSX, sheet_name=None, engine="openpyxl")

    Q_ACC_BY_SHEET = {}
    RESUMEN_MONTOS = []
    DETALLES = {}
    
    for sheet_name, df_raw in book.items():
        if sheet_name not in REDUCCION_BY_SHEET:
            continue
    
        try:
            out = procesa_hoja(sheet_name, df_raw, REDUCCION_BY_SHEET[sheet_name])
        except Exception as e:
            print(f"[{sheet_name}] ERROR procesando hoja: {e}")
            continue
    
        if not isinstance(out, dict):
            print(f"[{sheet_name}] WARNING: procesa_hoja no retornó dict (recibido {type(out)}). Se omite.")
            continue
    
        # >>>>> CLAVES CORRECTAS AQUÍ <<<<<
        required = {"Q_acc", "detalle", "areas_totales"}
        if not required.issubset(out.keys()):
            print(f"[{sheet_name}] WARNING: salida incompleta: claves={list(out.keys())}")
            continue
    
        Q_ACC_BY_SHEET[sheet_name] = out["Q_acc"]
        DETALLES[sheet_name] = out["detalle"]
    
        # >>>>> USAR areas_totales (ΣAcum) <<<<<
        RESUMEN_MONTOS.append({
            "programa": sheet_name,
            "inicial":     out["areas_totales"].get("Inicial", 0),
            "escenario1": out["areas_totales"].get("Escenario 1", 0),
            "escenario2": out["areas_totales"].get("Escenario 2", 0),
            "escenario3": out["areas_totales"].get("Escenario 3", 0),
        })

    expected_cols = ["programa", "inicial", "escenario1", "escenario2", "escenario3"]
    df_res = pd.DataFrame(RESUMEN_MONTOS)
    for c in expected_cols:
        if c not in df_res.columns:
            df_res[c] = 0
    df_res = df_res[expected_cols].copy()
    num_cols = ["inicial", "escenario1", "escenario2", "escenario3"]
    df_res[num_cols] = df_res[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)
    if df_res.empty:
        print("WARNING: RESUMEN_MONTOS llegó vacío. Revisa si se procesaron hojas.")
        df_res.loc[0] = {"programa":"(sin datos)","inicial":0,"escenario1":0,"escenario2":0,"escenario3":0}
    totals = df_res[num_cols].sum().to_dict()
    df_res.loc[len(df_res)] = {"programa":"Total General", **totals}
    df_res["Var_Esc1_vs_Base"] = df_res["inicial"] - df_res["escenario1"]
    df_res["Var_Esc2_vs_Base"] = df_res["inicial"] - df_res["escenario2"]
    df_res["Var_Esc3_vs_Base"] = df_res["inicial"] - df_res["escenario3"]

    # # Escribir a Excel (3 hojas)
    # with pd.ExcelWriter(OUTPUT_XLSX, engine="xlsxwriter") as xw:
    #     # 1) Q_Acumulado (Fig.1)
    #     ws1 = xw.book.add_worksheet("Q_Acumulado")
    #     row = 0
    #     header_fmt = xw.book.add_format({"bold": True, "bg_color": "#0B4F9E", "font_color":"white", "align":"center"})
    #     title_fmt  = xw.book.add_format({"bold": True})
    #     num_fmt    = xw.book.add_format({"num_format": "#,##0", "align":"center"})
    #     for prog, df in Q_ACC_BY_SHEET.items():
    #         ws1.write(row, 0, prog, title_fmt); row += 1
    #         ws1.write_row(row, 0, df.columns, header_fmt); row += 1
    #         for _, r in df.iterrows():
    #             ws1.write(row, 0, r["Mes"])
    #             ws1.write_row(row, 1, r[1:].tolist(), num_fmt)
    #             row += 1
    #         row += 2  # separador

    #     # 2) Resumen_Montos (Fig.2)
    #     # df_res.to_excel(xw, sheet_name="Resumen_Montos", index=False)
    #     # ws2 = xw.sheets["Resumen_Montos"]
    #     # money_fmt = xw.book.add_format({"num_format": "#,##0"})
    #     # ws2.set_column(1, 7, 15, money_fmt)
    #     # ws2.set_column(0, 0, 24)
    #     df_res.to_excel(xw, sheet_name="Resumen_Acumulados", index=False)
    #     ws2 = xw.sheets["Resumen_Acumulados"]
    #     ws2.set_column(0, 0, 24)
    #     ws2.set_column(1, df_res.shape[1]-1, 16, xw.book.add_format({"num_format":"#,##0"}))

    #     # 3) Detalle_Proyectos (Fig.3)
    #     ws3 = xw.book.add_worksheet("Detalle_Proyectos")
    #     row = 0
    #     red_fill = xw.book.add_format({"bg_color":"#FCD5D5"})
    #     for prog, det in DETALLES.items():
    #         ws3.write(row, 0, prog, title_fmt); row += 1
    #         for scen_name, df in det.items():
    #             ws3.write(row, 0, scen_name, title_fmt); row += 1
    #             # escribe tabla
    #             ws3.write_row(row, 0, ["Proyecto"] + list(df.columns), header_fmt); row += 1
    #             base_df = det["Inicial"]  # para formato condicional
    #             for i, (proj, r) in enumerate(df.iterrows()):
    #                 ws3.write(row, 0, proj)
    #                 ws3.write_row(row, 1, r.values.tolist(), num_fmt)
    #                 row += 1
    #             # formato condicional: resaltar celdas donde este escenario < base
    #             nrows = df.shape[0]; ncols = df.shape[1]
    #             # rango de escenario
    #             first_row = row - nrows
    #             first_col = 1
    #             last_row  = row - 1
    #             last_col  = ncols
    #             # escribir base a una hoja oculta no es cómodo; usaremos fórmula con referencias absolutas vía datos en memoria
    #             # alternativa: añadimos (temporalmente) la base a la derecha invisible
    #             # (simple: no aplicamos formula condicional, pero dejamos el bloque listo por si lo activas)
    #             row += 1  # separador
    #         row += 1

    # print(f"BASE DIR: {BASE_DIR}")
    # print(f"Archivo generado: {OUTPUT_XLSX}")
    payload = build_payload(Q_ACC_BY_SHEET, RESUMEN_MONTOS, DETALLES, tipo_resumen="montos")
    # print(json.dumps(payload, ensure_ascii=False, default=to_json_safe))
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=to_json_safe))

if __name__ == "__main__":
    main()