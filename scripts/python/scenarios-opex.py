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


def build_df_from_block(block):
    """
    block: lista de objetos del mismo programa, con keys:
      - programa
      - proyecto
      - incidencia
      - driver
      - meses: { 'Ene-26', 'Feb-26', ..., 'total', 'sumTotal' }

    Devuelve df_raw en el formato esperado por tu lógica de procesado
    (similar a la hoja de Excel original).
    """
    rows = []
    for item in block:
        meses = item.get("meses", {})

        row = {
            "Proyecto": item.get("proyecto"),
            "Incidencia": float(item.get("incidencia", 1)) if item.get("incidencia") not in (None, "") else 1,
            "Driver Fcst": float(item.get("driver", 0)) if item.get("driver") not in (None, "") else 0,
        }

        # añadimos columnas de meses tal cual vienen
        for k, v in meses.items():
            row[k] = v

        rows.append(row)

    return pd.DataFrame(rows)


def get_reduccion_from_block(block):
    """
    Usa SOLO el primer registro del bloque para obtener el monto a reducir,
    ignorando los demás (que vienen repetidos).

    Campo esperado: 'montoReducirInput'
    """
    if not block:
        return 0.0

    first = block[0]
    value = (
        first.get("montoReducirInput")
        or first.get("montoReducir")
        or first.get("monto_reducir")
    )

    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0



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

        def acc_counts(Q_int):
            qtot = Q_int.sum(axis=0)          # ya es entero
            acc  = np.cumsum(qtot).astype(int)
            acc[-1] = int(qtot.sum())         # por si acaso
            return acc

        idx = pd.Index(proyectos, name="Proyecto")

        # Tablas de detalle (escenarios) con enteros
        df_Q_base = pd.DataFrame(Q_base_i, index=idx, columns=meses)
        df_Q_s1   = pd.DataFrame(Q_s1_i,   index=idx, columns=meses)
        df_Q_s2   = pd.DataFrame(Q_s2_i,   index=idx, columns=meses)
        df_Q_s3   = pd.DataFrame(Q_s3_i,   index=idx, columns=meses)


        Qacc_base = acc_counts(Q_base_i)
        Qacc_s1   = acc_counts(Q_s1_i)
        Qacc_s2   = acc_counts(Q_s2_i)
        Qacc_s3   = acc_counts(Q_s3_i)

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
def run_from_dataprocess(dataprocess):
    """
    dataprocess: lista (array) de bloques.
    Cada bloque = 1 programa (hoja).
    """
    Q_ACC_BY_SHEET = {}
    RESUMEN_MONTOS = []
    DETALLES = {}

    # print("DATAPROCESS", dataprocess)


    for block in dataprocess:
        if not block:
            continue

        sheet_name = (block[0].get("programa") or "").strip() or "SIN_NOMBRE"

        df_raw = build_df_from_block(block)
        reduccion_obj = get_reduccion_from_block(block)

        # ---- AQUÍ usas tus funciones existentes ----
        out = procesa_hoja(sheet_name, df_raw, reduccion_obj)
        # --------------------------------------------

        if not isinstance(out, dict):
            continue

        required = {"Q_acc", "detalle", "areas_totales"}
        if not required.issubset(out.keys()):
            continue

        Q_ACC_BY_SHEET[sheet_name] = out["Q_acc"]

        areas = out["areas_totales"] or {}
        RESUMEN_MONTOS.append({
            "programa": sheet_name,
            "inicial":    areas.get("Inicial", 0),
            "escenario1": areas.get("Escenario 1", 0),
            "escenario2": areas.get("Escenario 2", 0),
            "escenario3": areas.get("Escenario 3", 0),
        })

        DETALLES[sheet_name] = out["detalle"]

    # build_payload = tu función actual que arma respuesta final
    payload = build_payload(
        Q_ACC_BY_SHEET,
        RESUMEN_MONTOS,
        DETALLES,
        tipo_resumen="montos"
    )
    return payload


if __name__ == "__main__":
    raw = sys.stdin.read()
    dataprocess = json.loads(raw)
    payload = run_from_dataprocess(dataprocess)
    # print(json.dumps(payload, ensure_ascii=False, default=str))
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, default=to_json_safe))