# ====================================================================== #
# IMPORT LIBRARIES
# ====================================================================== #
import pandas as pd
import numpy as np
import datetime
from matplotlib import pyplot as plt
from openpyxl import load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import numbers
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
import xlwings as xw
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import sys, os, json, time
from dateutil.parser import parse
import re, unicodedata
from pymongo import MongoClient, UpdateOne
from xlsx2csv import Xlsx2csv
from typing import List, Tuple

# ====================================================================== #
# READ DATA
# ====================================================================== #
BASE_DIR = "./scripts/data/capex"
CACHE_DIR = ".cache_xlsx_csv"; SHEET_ID = 1
os.makedirs(CACHE_DIR, exist_ok=True)

def _read_manifest_from_stdin():
    try:
        if sys.stdin is None or sys.stdin.closed:
            return None
        raw = sys.stdin.read()
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        print(f"[{SHEET_ID}] ERROR reading manifest from stdin: {e}")
        return None

def _read_manifest_from_argv():
    try:
        if len(sys.argv) >= 2:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[{SHEET_ID}] ERROR reading manifest from argv: {e}")
        return None

def resolve_input_lists() -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]], List[Tuple[str, int]], List[Tuple[str, int]]]:
    manifest = _read_manifest_from_stdin() or _read_manifest_from_argv()
    if not manifest:
        return files_rq, files_oc, files_cr, files_misc
    
    man = manifest.get("manifest", manifest)

    def pick(section):
        out = []
        for f in man.get(section, []):
            # if isinstance(f, str):
            path = f.get("path")
            field = f.get("field")
            if not path:
                continue
            
            out.append((path, int(f.get("skiprows", 0)), field))

        return out
    
    return pick("rq"), pick("oc"), pick("cr"), pick("misc")

def load_many(pairs: List[Tuple[str, int]]) -> List[pd.DataFrame]:
    dfs = []
    for path, skip, field in pairs:
        df = pd.read_excel(path, skiprows=skip)
        dfs.append(df)
    return dfs

def _cache_paths(xlsx_path):
    base = os.path.basename(xlsx_path)
    name = "{}__sheet{}.csv".format(os.path.splitext(base)[0], SHEET_ID)
    csv_path  = os.path.join(CACHE_DIR, name)
    meta_path = csv_path + ".meta.json"
    return csv_path, meta_path

def _needs_refresh(xlsx_path, csv_path, meta_path):
    if not os.path.exists(csv_path) or not os.path.exists(meta_path):
        return True
    try:
        st = os.stat(xlsx_path)
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return not (meta.get("size") == st.st_size and meta.get("mtime") == st.st_mtime)
    except Exception:
        return True

def _save_meta(xlsx_path, meta_path):
    st = os.stat(xlsx_path)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"size": st.st_size, "mtime": st.st_mtime}, f)

def convert_xlsx_to_csv_if_needed(xlsx_path):
    csv_path, meta_path = _cache_paths(xlsx_path)
    if _needs_refresh(xlsx_path, csv_path, meta_path):
        Xlsx2csv(xlsx_path, outputencoding="utf-8", sheetid=SHEET_ID).convert(csv_path)
        _save_meta(xlsx_path, meta_path)
    return csv_path

def read_as_csv(xlsx_path, skiprows=None):
    csv_path = convert_xlsx_to_csv_if_needed(xlsx_path)  # conversión SECUENCIAL antes
    return pd.read_csv(csv_path, skiprows=skiprows)

def read_as_excel(xlsx_path, skiprows=None):
    return pd.read_excel(xlsx_path, skiprows=skiprows, engine="openpyxl")

# def convert_all(files):
#     # Convierte primero, secuencial y robusto (evita romper hilos/procesos)
#     for p,_ in files:
#         try:
#             convert_xlsx_to_csv_if_needed(p)
#         except Exception:
#             print("Error convirtiendo:", p)
#             traceback.print_exc()

def load_group_threaded(files, as_csv=True, max_workers=8):
    # lectura en paralelo con hilos (seguro en notebook)
    fn = (lambda f: read_as_csv(*f)) if as_csv else (lambda f: read_as_excel(*f))
    dfs = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn, f): f for f in files}
        for fut in as_completed(futs):
            path,_ = futs[fut]
            try:
                df = fut.result()
                dfs.append((path, df))
            except Exception:
                print("Error leyendo:", path)
                traceback.print_exc()
    # mantener orden
    order = {p:i for i,(p,_) in enumerate(files)}
    dfs.sort(key=lambda t: order[t[0]])
    return pd.concat([d for _,d in dfs], ignore_index=True)

# # --- tus listas ---
# files_rq_static = [
#     (BASE_DIR + "/" + 'TS 03.10 Historico de RQs - Nuevas Columnas v2_Reporte Excel 1.0 (2022).xlsx', 7),
#     (BASE_DIR + "/" + 'TS 03.10 Historico de RQs - Nuevas Columnas v2_Reporte Excel 1.0 (2023).xlsx', 7)
#     # (BASE_DIR + "/" + 'TS 03.10 Historico de RQs - Nuevas Columnas v2_Reporte Excel 1.0 (2024) 2410.xlsx', 7)
# ]
# files_oc_static = [
#     (BASE_DIR + "/" + 'TS 03.15 Orden de Compra_Reporte Excel 1.0 (2022).xlsx', 7),
#     (BASE_DIR + "/" + 'TS 03.15 Orden de Compra_Reporte Excel 1.0 (2023).xlsx', 7)
#     # (BASE_DIR + "/" + 'TS 03.15 Orden de Compra_Reporte Excel 1.0 (Ene_Sep24) 2410.xlsx', 7)
# ]
# files_cr_static = [
#     (BASE_DIR + "/" + 'TS 03.16 Códigos Recepción - Nuevas Columnas_Reporte (2022).xlsx', 7), 
#     (BASE_DIR + "/" + 'TS 03.16 Códigos Recepción - Nuevas Columnas_Reporte (2023).xlsx', 7) 
#     # (BASE_DIR + "/" + 'TS 03.16 Códigos Recepción - Nuevas Columnas_Reporte (2024) 2410.xlsx', 7)
# ]
# files_misc = [
#     (BASE_DIR + "/" + 'FCST 2025.xlsx', None),
#     (BASE_DIR + "/" + 'Proyectos capex 2025 2410.xlsx', 2),
#     (BASE_DIR + "/" + 'GCIR - Master Plan 2025 - General.xlsm', 2),
#     (BASE_DIR + "/" + 'TS 03.15 Orden de Compra_Reporte Excel 1.0 (2024) CIERRE.xlsx', 7),
#     (BASE_DIR + "/" + 'Provision 2024.xlsx', None)
# ]

# # --- ejecución ---

# # convert_all(files_rq + files_oc + files_cr)   # convierte primero (evita roturas)
# matriz_rq_static    = load_group_threaded(files_rq_static, as_csv=True)
# matriz_oc_ac_static = load_group_threaded(files_oc_static, as_csv=True)
# matriz_cr_static    = load_group_threaded(files_cr_static, as_csv=True)
# matriz_fcst, matriz_solpe, matriz_mp, matriz_oc_cierre, matriz_provision = [
#     read_as_excel(p, s) for (p,s) in files_misc
# ]

t0 = time.perf_counter()

_files_rq, _files_oc, _files_cr, _files_misc = resolve_input_lists()


# print(_files_misc)

rq_dfs = load_many(_files_rq)
oc_dfs = load_many(_files_oc)
cr_dfs = load_many(_files_cr)
misc_dfs = load_many(_files_misc)

matriz_rq = pd.concat(rq_dfs, ignore_index=True) if rq_dfs else pd.DataFrame()
matriz_oc_ac = pd.concat(oc_dfs, ignore_index=True) if oc_dfs else pd.DataFrame()
matriz_cr = pd.concat(cr_dfs, ignore_index=True) if cr_dfs else pd.DataFrame()
matriz_solpe = pd.DataFrame()
matriz_oc_cierre = pd.DataFrame()
matriz_fcst = pd.DataFrame()
matriz_mp = pd.DataFrame()
matriz_provision = pd.DataFrame()

for path, skip, field in _files_misc:
    df = pd.read_excel(path, skiprows=skip)

    if field == "solpe":
        matriz_solpe = df
    if field == "cierre":
        matriz_oc_cierre = df
    if field == "fcst":
        matriz_fcst = df
    if field == "master_plan":
        matriz_mp = df
    if field == "provision":
        matriz_provision = df



# print(matriz_rq)
# print(matriz_oc_ac)
# print(matriz_cr)
# # print(misc_dfs)
# print("===================================")
# print(matriz_solpe)
# print(matriz_fcst)
# print(matriz_mp)
# print(matriz_oc_cierre)
# print(matriz_provision)


# print("⏱ Total: {:.2f}s".format(time.perf_counter() - t0))



# ====================================================================== #
# CLEAN DATA
# ====================================================================== #
# Remover RQ's vacías
t0 = time.perf_counter()
if matriz_rq['RQ'].isna().sum() > 0:
    matriz_rq = matriz_rq.dropna(subset=['RQ'])
    
if matriz_oc_ac['Nro RQ'].isna().sum() > 0:
    matriz_oc_ac = matriz_oc_ac.dropna(subset=['Nro RQ'])
    
if matriz_cr['RQ'].isna().sum() > 0:
    matriz_cr = matriz_cr.dropna(subset=['RQ'])
    
if matriz_oc_cierre['Nro RQ'].isna().sum() > 0:
    matriz_oc_cierre = matriz_oc_cierre.dropna(subset=['Nro RQ'])

#### 2. Convetir tipos de datos
# Datos matriz RQ
matriz_rq['Nro Línea'] = matriz_rq['Nro Línea'].astype(int) #
matriz_rq['Nro OC'] = matriz_rq['Nro OC'].fillna(0)
matriz_rq['Nro OC'] = matriz_rq['Nro OC'].astype(int)
matriz_rq['Nro Línea OC'] = matriz_rq['Nro Línea OC'].fillna(0)
matriz_rq['Nro Línea OC'] = matriz_rq['Nro Línea OC'].astype(int)
matriz_rq['Fecha Aprobación RQ'] = pd.to_datetime(matriz_rq['Fecha Aprobación RQ'], format='%d/%m/%Y', errors='coerce')
matriz_rq['Fecha Emisión RQ'] = pd.to_datetime(matriz_rq['Fecha Emisión RQ'], format='%d/%m/%Y', errors='coerce')

# Datos matriz OC
matriz_oc_ac['Línea OC'] = matriz_oc_ac['Línea OC'].astype(int)
matriz_oc_ac['Mes'] = matriz_oc_ac['Mes'].astype(int)
matriz_oc_ac['Nro OC'] = matriz_oc_ac['Nro OC'].astype(int)
matriz_oc_ac['Fecha Emisión OC'] = pd.to_datetime(matriz_oc_ac['Fecha Emisión OC'], format='%d/%m/%Y', errors='coerce')
matriz_oc_ac['Fecha Aprobación OC'] = pd.to_datetime(matriz_oc_ac['Fecha Aprobación OC'], format='%d/%m/%Y', errors='coerce')

# Datos matriz OC - Cierre
matriz_oc_cierre['Línea OC'] = matriz_oc_cierre['Línea OC'].astype(int)
matriz_oc_cierre['Mes'] = matriz_oc_cierre['Mes'].astype(int)
matriz_oc_cierre['Nro OC'] = matriz_oc_cierre['Nro OC'].astype(int)
matriz_oc_cierre['Fecha Emisión OC'] = pd.to_datetime(matriz_oc_cierre['Fecha Emisión OC'], format='%d/%m/%Y', errors='coerce')
matriz_oc_cierre['Fecha Aprobación OC'] = pd.to_datetime(matriz_oc_cierre['Fecha Aprobación OC'], format='%d/%m/%Y', errors='coerce')

# Datos matriz AC
matriz_cr['Línea Orden Compra'] = matriz_cr['Línea Orden Compra'].astype(int)
matriz_cr['OC'] = matriz_cr['OC'].astype(int)


#### 3. Crear llaves de union
# Datos matriz RQ
pos = 0

# Llave 1
matriz_rq['Key'] = np.where(
    (matriz_rq['Nro Línea OC'] != 0) & (matriz_rq['Nro Línea'] != matriz_rq['Nro Línea OC']),
    matriz_rq['RQ'] + "_" + matriz_rq['Nro Línea OC'].astype(str),
    matriz_rq['RQ'] + "_" + matriz_rq['Nro Línea'].astype(str)
)

# Llave 2
matriz_rq['Key3'] = np.where(
    (matriz_rq['Nro Línea OC'] != 0) & (matriz_rq['Nro Línea'] != matriz_rq['Nro Línea OC']),
    matriz_rq['RQ'] + "_" + matriz_rq['Nro Línea OC'].astype(str) + "_" + matriz_rq['Nro OC'].astype(str),
    matriz_rq['RQ'] + "_" + matriz_rq['Nro Línea'].astype(str) + "_" + matriz_rq['Nro OC'].astype(str)
)

# Datos matriz OC
concat_rq_3 = matriz_oc_ac['Nro RQ'] + "_" + matriz_oc_ac['Línea OC'].astype(str)
matriz_oc_ac.insert(loc=pos, column='Key', value=concat_rq_3)
concat_key_3 = matriz_oc_ac['Nro RQ'] + "_" + matriz_oc_ac['Línea OC'].astype(str) + "_" + matriz_oc_ac['Nro OC'].astype(str)
matriz_oc_ac.insert(loc=pos, column='Key3', value=concat_key_3)

# Datos matriz OC - Cierre
concat_rq_3 = matriz_oc_cierre['Nro RQ'] + "_" + matriz_oc_cierre['Línea OC'].astype(str)
matriz_oc_cierre.insert(loc=pos, column='Key', value=concat_rq_3)
concat_key_3 = matriz_oc_cierre['Nro RQ'] + "_" + matriz_oc_cierre['Línea OC'].astype(str) + "_" + matriz_oc_cierre['Nro OC'].astype(str)
matriz_oc_cierre.insert(loc=pos, column='Key3', value=concat_key_3)

# Datos matriz AC
concat_rq_4 = matriz_cr['RQ'] + "_" + matriz_cr['Línea Orden Compra'].astype(str)
matriz_cr.insert(loc=pos, column='Key', value=concat_rq_4)
concat_key_4 = matriz_cr['RQ'] + "_" + matriz_cr['Línea Orden Compra'].astype(str) + "_" + matriz_cr['OC'].astype(str)
matriz_cr.insert(loc=pos, column='Key3', value=concat_key_4)


#### 4. Concatenar Dataframes de RQ si existe
matriz_concat = matriz_rq
# Estados RQ
options_status_rq = ['Aprobada', 'Aprobado con OC', 'Pendiente Aprobación']

# DF RQ
matriz_concat = matriz_concat[matriz_concat['Estado RQ'].isin(options_status_rq)]
matriz_concat = matriz_concat[matriz_concat['Estado Línea RQ'] != "Cancelada"]


#### 5. Remover llaves duplicadas
if matriz_concat['Key3'].duplicated().sum() > 0:
    matriz_concat = matriz_concat.drop_duplicates(subset=['Key3'], keep='first')
    
matriz_concat['Key3'].duplicated().sum()


#### 6. Limpieza DF Solpe
matriz_solpe['Tipo Proyecto'] = "Proy."
# Filtrar los estados "Rejected" o "Rechazado"
options_status_solpe = ['Rejected', 'Rechazado']
matriz_solpe = matriz_solpe[~matriz_solpe['Project Status'].isin(options_status_solpe)]

matriz_solpe["Project Number"] = matriz_solpe["Project Number"].str.strip()
matriz_solpe["Base Project Code"] = matriz_solpe["Project Number"].str.strip().str.split().str[0]

# Añadir estado de presupuesto
matriz_solpe["contiene_BOD_G"] = matriz_solpe["Project Number"].str.contains(r'\b(BOD|G)\b')
matriz_solpe["Estado Ptto"] = matriz_solpe.groupby("Base Project Code")["contiene_BOD_G"]\
                 .transform(lambda x: "Aprobado" if x.any() else "En validación")

# Remover columna
matriz_solpe.drop(columns=["contiene_BOD_G"], inplace=True)

# Filtrar codigos de proyecto
pattern = r'^\S+$'
matriz_solpe = matriz_solpe[matriz_solpe["Project Number"].str.match(pattern, na=False)]

# Encontrar para cada (Project Number, Task Number) la minima version
df_min_cost = (
    matriz_solpe.loc[
        matriz_solpe.groupby(["Project Number", "Task Number"])["Budget Version Number"].idxmin(), 
        ["Project Number", "Task Number", "Raw Cost"]
    ]
    .rename(columns={"Raw Cost": "PRESUPUESTO ORIGINAL"})
)

# Encontrar para cada (Project Number, Task Number) la máxima version
df_max_cost = (
    matriz_solpe.loc[
        matriz_solpe.groupby(["Project Number", "Task Number"])["Budget Version Number"].idxmax(), 
        ["Project Number", "Task Number", "Raw Cost"]
    ]
    .rename(columns={"Raw Cost": "PRESUPUESTO HABILITADO"})
)

# Unir esos valores de min y max de vuelta al df original
matriz_solpe = (
    matriz_solpe
    .merge(df_min_cost, on=["Project Number", "Task Number"], how="left")
    .merge(df_max_cost, on=["Project Number", "Task Number"], how="left")
)

# Obtener la última versión del presupuesto
matriz_solpe = matriz_solpe[
    matriz_solpe["Budget Version Number"] == matriz_solpe.groupby(["Project Number", "Task Number"])["Budget Version Number"].transform("max")
]

# Por defecto los CARRYOVER tienen como estado "APROBADO"
matriz_solpe.loc[matriz_solpe["Tipo Proyecto"] == "CARRYOVER", 'Estado'] = "Aprobado"


#### 7. Funcion para retirar sufijos al nombre y código del proyecto
def limpiar_nombre_proyecto(nombre):
    for sufijo in [' BOD', ' G', ' R', '_G']:
        if str(nombre).endswith(sufijo):
            nombre = nombre[:-len(sufijo)]
            break
    return nombre

# Aplicando la función a la columna
matriz_concat['Nombre Proyecto'] = matriz_concat['Nombre Proyecto'].apply(limpiar_nombre_proyecto)
matriz_oc_ac['Nombre Proyecto'] = matriz_oc_ac['Nombre Proyecto'].apply(limpiar_nombre_proyecto)
matriz_cr['Nombre Proyecto'] = matriz_cr['Nombre Proyecto'].apply(limpiar_nombre_proyecto)
matriz_solpe['Project Number'] = matriz_solpe['Project Number'].apply(limpiar_nombre_proyecto)

matriz_concat['Código Proyecto'] = matriz_concat['Código Proyecto'].apply(limpiar_nombre_proyecto)
matriz_oc_ac['Código Proyecto'] = matriz_oc_ac['Código Proyecto'].apply(limpiar_nombre_proyecto)
matriz_cr['Código Proyecto'] = matriz_cr['Código Proyecto'].apply(limpiar_nombre_proyecto)
matriz_solpe['Project Name'] = matriz_solpe['Project Name'].apply(limpiar_nombre_proyecto)

# RQ, OC, AC - CIERRE
matriz_oc_cierre['Nombre Proyecto'] = matriz_oc_cierre['Nombre Proyecto'].apply(limpiar_nombre_proyecto)
matriz_oc_cierre['Código Proyecto'] = matriz_oc_cierre['Código Proyecto'].apply(limpiar_nombre_proyecto)


#### 8. Filtrar estados de RQ
# Obtener año y mes de la fecha emision RQ
matriz_concat['Mes RQ'] = matriz_concat['Fecha Emisión RQ'].dt.month
matriz_concat['Año RQ'] = matriz_concat['Fecha Emisión RQ'].dt.year
matriz_concat['Año Aprobación RQ'] = matriz_concat['Fecha Aprobación RQ'].dt.year

# Concatener linea de inversion para DF AC
matriz_cr['Línea inversión'] = matriz_cr['Línea de Inversión'] + "-" + matriz_cr['Descripción Línea de Inversión']


#### 9. Mostrar columnas especificas para DF OC y AC
select_columns_oc = ['Key3', 'Key', 'Nro RQ', 'Nro OC', 'Fecha Emisión OC','Estado OC', 'Fecha Aprobación OC','Moneda', 'Tipo Cambio', 'Monto Original', 'Monto Recepcionado', 'Monto Facturado', 'Descripción OC', 'Descripción Adicional', 'Requisitor', 'Gerencia Requisitor', 'Gerencia Sponsor', 'Código Proyecto','Nombre Proyecto', 'Nombre Inversión/Subrubro', 'Mes', 'Año','Proveedor','Declaración No Uso']
select_columns_cr = ['Key3', 'Key', 'RQ', 'OC', 'Fecha Recepción', 'Código Recepción', 'Categoría', 'Descripcion Línea OC', 'TC OC', 'Nro Factura','Monto Ordenado', 'Precio Unitario', 'Cantidad Recepcionada', 'Monto Facturado', 'Gerencia en OC', 'PM Proyecto', 'Código Proyecto','Nombre Proyecto', 'Línea inversión','Proveedor']

# DF OC y AC
matriz_oc_ac_select = matriz_oc_ac[select_columns_oc]
matriz_cr_select = matriz_cr[select_columns_cr]

# DF OC - Cierre
matriz_oc_cierre_select = matriz_oc_cierre[select_columns_oc]


#### 9. Transformar columna MES de numérico a valor
# Convert Values MES
meses = [
          (matriz_oc_ac_select['Mes']==1),
          (matriz_oc_ac_select['Mes']==2),
            (matriz_oc_ac_select['Mes']==3),
            (matriz_oc_ac_select['Mes']==4),
            (matriz_oc_ac_select['Mes']==5),
            (matriz_oc_ac_select['Mes']==6),
            (matriz_oc_ac_select['Mes']==7),
            (matriz_oc_ac_select['Mes']==8),
            (matriz_oc_ac_select['Mes']==9),
            (matriz_oc_ac_select['Mes']==10),
            (matriz_oc_ac_select['Mes']==11),
            (matriz_oc_ac_select['Mes']==12),
]

meses_rq = [
          (matriz_concat['Mes RQ']==1),
          (matriz_concat['Mes RQ']==2),
            (matriz_concat['Mes RQ']==3),
            (matriz_concat['Mes RQ']==4),
            (matriz_concat['Mes RQ']==5),
            (matriz_concat['Mes RQ']==6),
            (matriz_concat['Mes RQ']==7),
            (matriz_concat['Mes RQ']==8),
            (matriz_concat['Mes RQ']==9),
            (matriz_concat['Mes RQ']==10),
            (matriz_concat['Mes RQ']==11),
            (matriz_concat['Mes RQ']==12),
]

etiquetas = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Setiembre','Octubre','Noviembre','Diciembre']

matriz_oc_ac_select['Mes'] = np.select(meses, etiquetas, "-")
matriz_concat['Mes RQ'] = np.select(meses_rq, etiquetas, "-")



#### 10. JOIN: OC actuales VS OC cierre
# Copia Estado OC
oc_a_copiar = matriz_oc_cierre_select['Estado OC'].copy()
matriz_oc_cierre_select['Estado OC Inicial'] = oc_a_copiar

# Extraigo 02 columnas
columns_cierre_use_2 = ['Key3', 'Estado OC Inicial']
match_cierre = matriz_oc_cierre_select[columns_cierre_use_2]

# JOIN LEFT mediante la llave 2
matriz_oc_ac_select = pd.merge(matriz_oc_ac_select, match_cierre, on=['Key3'], how='left')


#### 11. JOIN: OC vs AC
# JOIN FULL: OC vs AC
matriz_oc_ac_cr = pd.merge(matriz_oc_ac_select, matriz_cr_select, on='Key3', how='outer')

# Rellenar los valores vacíos
matriz_oc_ac_cr['Monto Recepcionado CR'] = matriz_oc_ac_cr['Precio Unitario'] * matriz_oc_ac_cr['Cantidad Recepcionada']
matriz_oc_ac_cr['Key'] = matriz_oc_ac_cr['Key_x'].combine_first(matriz_oc_ac_cr['Key_y'])
matriz_oc_ac_cr['RQ'] = matriz_oc_ac_cr['Nro RQ'].combine_first(matriz_oc_ac_cr['RQ'])
matriz_oc_ac_cr['Nro OC'] = matriz_oc_ac_cr['Nro OC'].combine_first(matriz_oc_ac_cr['OC'])
matriz_oc_ac_cr['Código Proyecto'] = matriz_oc_ac_cr['Código Proyecto_x'].combine_first(matriz_oc_ac_cr['Código Proyecto_y'])
matriz_oc_ac_cr['Nombre Proyecto'] = matriz_oc_ac_cr['Nombre Proyecto_x'].combine_first(matriz_oc_ac_cr['Nombre Proyecto_y'])
matriz_oc_ac_cr['Nombre Inversión/Subrubro'] = matriz_oc_ac_cr['Nombre Inversión/Subrubro'].combine_first(matriz_oc_ac_cr['Línea inversión'])
matriz_oc_ac_cr['Gerencia Requisitor'] = matriz_oc_ac_cr['Gerencia Requisitor'].combine_first(matriz_oc_ac_cr['Gerencia en OC'])
matriz_oc_ac_cr['Requisitor'] = matriz_oc_ac_cr['Requisitor'].combine_first(matriz_oc_ac_cr['PM Proyecto'])
matriz_oc_ac_cr['Proveedor'] = matriz_oc_ac_cr['Proveedor_x'].combine_first(matriz_oc_ac_cr['Proveedor_y'])
matriz_oc_ac_cr['Descripción OC'] = matriz_oc_ac_cr['Descripción OC'].combine_first(matriz_oc_ac_cr['Descripcion Línea OC'])
matriz_oc_ac_cr['Tipo Cambio'] = matriz_oc_ac_cr['Tipo Cambio'].combine_first(matriz_oc_ac_cr['TC OC'])
matriz_oc_ac_cr['Monto Comprometido'] = matriz_oc_ac_cr['Monto Ordenado'].combine_first(matriz_oc_ac_cr['Monto Original'])
matriz_oc_ac_cr['Monto Recepcionado'] = matriz_oc_ac_cr['Monto Recepcionado CR'].combine_first(matriz_oc_ac_cr['Monto Recepcionado'])
matriz_oc_ac_cr['Monto Facturado'] = matriz_oc_ac_cr['Monto Facturado_y'].combine_first(matriz_oc_ac_cr['Monto Facturado_x'])

# Elimina las columnas innecesarias
matriz_oc_ac_cr = matriz_oc_ac_cr.drop(columns=['Key_x', 'Key_y', 
    'Nro RQ', 'OC', 'Código Proyecto_x', 'Código Proyecto_y', 
    'Nombre Proyecto_x', 'Nombre Proyecto_y', 'Línea inversión', 
    'Gerencia en OC', 'PM Proyecto', 'TC OC', 'Monto Original', 'Monto Ordenado', 
    'Monto Facturado_x', 'Monto Facturado_y', 'Monto Recepcionado CR','Descripcion Línea OC',
    'Proveedor_x','Proveedor_y'])


#### 12. JOIN: RQ vs OC-AC
# Convertir tipo de datos y filtrar Tipo RQ
matriz_oc_ac_cr['Nro OC'] = matriz_oc_ac_cr['Nro OC'].astype(int)
matriz_concat['Año RQ'] = matriz_concat['Año RQ'].fillna(0).astype(int)
matriz_concat['Año Aprobación RQ'] = matriz_concat['Año Aprobación RQ'].fillna(0).astype(int)
matriz_concat = matriz_concat[matriz_concat['Tipo RQ'] != "TRANSFERENCIA"] 

# JOIN FULL: RQ vs OC-AC
matriz_final = pd.merge(matriz_concat, matriz_oc_ac_cr, on=['Key', 'Nro OC'], how='outer')

# Rellenar los valores vacíos
matriz_final['Año OC'] = matriz_final['Fecha Emisión OC'].dt.year
matriz_final['Año OC'] = matriz_final['Año OC'].fillna(0).astype(int)
matriz_final['Año Aprobación OC'] = matriz_final['Fecha Aprobación OC'].dt.year
matriz_final['Año Aprobación OC'] = matriz_final['Año Aprobación OC'].fillna(0).astype(int)
matriz_final['Key3'] = matriz_final['Key3_x'].combine_first(matriz_final['Key3_y'])
matriz_final['RQ'] = matriz_final['RQ_x'].combine_first(matriz_final['RQ_y'])
matriz_final['Tipo Cambio'] = matriz_final['Tipo Cambio_y'].combine_first(matriz_final['Tipo Cambio_x'])
matriz_final['Código Proyecto'] = matriz_final['Código Proyecto_x'].combine_first(matriz_final['Código Proyecto_y'])
matriz_final['Nombre Proyecto'] = matriz_final['Nombre Proyecto_x'].combine_first(matriz_final['Nombre Proyecto_y'])
matriz_final['Inversión/SubRubro'] = matriz_final['Inversión/SubRubro'].combine_first(matriz_final['Nombre Inversión/Subrubro'])
matriz_final['Estado OC'] = matriz_final['Estado OC_y'].combine_first(matriz_final['Estado OC_x'])
matriz_final['Descripción Adicional'] = matriz_final['Descripción Adicional_y'].combine_first(matriz_final['Descripción Adicional_x'])
matriz_final['Proveedor'] = matriz_final['Proveedor_x'].combine_first(matriz_final['Proveedor_y'])
matriz_final['Requisitor'] = matriz_final['Usuario Final'].combine_first(matriz_final['Requisitor'])

# Elimina las columnas innecesarias
matriz_final = matriz_final.drop(columns=['Key3_x', 'Key3_y', 'RQ_x', 'RQ_y', 'Estado OC_y', 'Estado OC_x','Tipo Cambio_x', 'Tipo Cambio_y', 'Código Proyecto_x', 'Código Proyecto_y', 'Nombre Proyecto_x', 'Nombre Proyecto_y', 'Nombre Inversión/Subrubro', 'Descripción Adicional_y', 'Descripción Adicional_x','Proveedor_x','Proveedor_y'])
matriz_final.loc[matriz_final['Estado OC'].isna(), 'Estado OC'] = 'RQ en proceso'


# Filtrar estatus OC
options_rq_oc_ac = ['Abierta', 'Cerrada', 'Cerrada Final', 'Cerrada para Facturación', 'Cerrada para Recepción', 'RQ en proceso', 'Pendiente Aprobación']


#### 13. JOIN: Matriz Final vs Master Plan
# Duplicar ID proyecto a la columna "Codigo Proyecto"
# matriz_mp['Código Proyecto'] = matriz_mp['ID Proyecto']
columns = ['Código Proyecto', 'PM ACTUAL', 'Gerencia Sponsor Final']
matriz_mp_select = matriz_mp[columns]

# JOIN LEFT: Matriz Final vs Master Plan
matriz_final = pd.merge(matriz_final, matriz_mp_select, on='Código Proyecto', how='left')

# Rellenar "POR REVISAR" si es vacío.
matriz_final.loc[matriz_final['PM ACTUAL'].isna(), 'PM ACTUAL'] = 'La linea'
matriz_final.loc[matriz_final['Gerencia Sponsor Final'].isna(), 'Gerencia Sponsor Final'] = 'Otras Gerencias'

# Ordenar columnas
columnas = list(matriz_final.columns)
indice_pm = columnas.index('PM ACTUAL') #10
indice_gr = columnas.index('Gerencia Requisitor') #3
columna_pm = columnas.pop(indice_pm)
columnas.insert(indice_gr, columna_pm)

# Reorganiza el DataFrame con las columnas movidas
matriz_final = matriz_final[columnas]



#### 14. Añadir año actual
# Obtener el año actual
today = datetime.date.today()
actual_year = today.year

# Convertir tipo fecha a la matriz final
matriz_final['Fecha Recepción'] = pd.to_datetime(matriz_final['Fecha Recepción'], format='%d/%m/%Y %H:%M:%S', errors='coerce')
matriz_final['Año Recepción'] = matriz_final['Fecha Recepción'].dt.year
matriz_final['Mes Recepción'] = matriz_final['Fecha Recepción'].dt.month
matriz_final['Año Recepción'] = matriz_final['Año Recepción'].fillna(0).astype(int)
matriz_final['Mes Recepción'] = matriz_final['Mes Recepción'].fillna(0).astype(int)

# Filtrar datos.
# 1. Solo estados válidos
# 2. Si es cancelada solo si:
# 2.1. Año OC es del último año
# 2.2. Codigo de recepcion es no vacío
# 2.3. Fecha de recepcion es menor a la fecha de aprobacion OC
matriz_final = matriz_final[
    (matriz_final['Estado OC'].isin(options_rq_oc_ac)) |
    ((matriz_final['Estado OC'] == 'Cancelada') & (matriz_final['Año Aprobación OC'] == actual_year) & (matriz_final['Código Recepción'].notna()) & (matriz_final['Fecha Recepción'] < matriz_final['Fecha Aprobación OC']))
]

# Rellenar 0 si no tiene año
matriz_final['Año RQ test'] = matriz_final['Año RQ'].fillna(0).astype(int)


#### 15. Transformar columna MES de numérico a valor
# Convert Values MES - MATRIZ_FINAL
meses_cr = [
          (matriz_final['Mes Recepción']==1),
          (matriz_final['Mes Recepción']==2),
            (matriz_final['Mes Recepción']==3),
            (matriz_final['Mes Recepción']==4),
            (matriz_final['Mes Recepción']==5),
            (matriz_final['Mes Recepción']==6),
            (matriz_final['Mes Recepción']==7),
            (matriz_final['Mes Recepción']==8),
            (matriz_final['Mes Recepción']==9),
            (matriz_final['Mes Recepción']==10),
            (matriz_final['Mes Recepción']==11),
            (matriz_final['Mes Recepción']==12),
]

etiquetas = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Setiembre','Octubre','Noviembre','Diciembre']
matriz_final['Mes Recepción'] = np.select(meses_cr, etiquetas, "-")


#### 16. Configuracion Matriz CR - Detalles
# Copia de la matriz final
matriz_final_individual = matriz_final.copy()

# Añadir campo Importe OC y AC:
matriz_final_individual['Importe OC'] = matriz_final_individual['Monto Comprometido'] * matriz_final_individual['Tipo Cambio']
matriz_final_individual['Importe AC'] = matriz_final_individual['Monto Recepcionado'] * matriz_final_individual['Tipo Cambio']

# Montos Actas solo del año actual y menores al mismo
matriz_final_individual['Importe AC 2026'] = matriz_final_individual.apply(
    lambda row: row['Monto Recepcionado'] * row['Tipo Cambio'] if row['Año Recepción'] == actual_year else 0,
    axis=1
)
matriz_final_individual['Importe AC menores 2026'] = matriz_final_individual.apply(
    lambda row: row['Monto Recepcionado'] * row['Tipo Cambio'] if row['Año Recepción'] < actual_year else 0,
    axis=1
)

# Añadir campo Montos Facturado y RQ
matriz_final_individual['Importe Facturado'] = matriz_final_individual['Monto Facturado'] * matriz_final_individual['Tipo Cambio']
matriz_final_individual['Importe RQ'] = matriz_final_individual['Monto Funcional']

# Códigos de Recepción generados en el año actual y menores al mismo
matriz_final_individual['CR 2026'] = (matriz_final_individual['Año Recepción'] == actual_year).astype(int)
matriz_final_individual['CR menores 2026'] = (matriz_final_individual['Año Recepción'] < actual_year).astype(int) & (matriz_final_individual['Año Recepción'] != 0)

# Regla OC
condicion = (matriz_final_individual['Monto Comprometido'].isna() & 
             matriz_final_individual['RUC'].notna() & 
             (~matriz_final_individual['Estado OC'].isin(["Cancelada", "Incompleta"])))

condicion_oc = ((matriz_final_individual['Estado OC'] == 'Cancelada') & 
                (matriz_final_individual['Año Aprobación OC'] == actual_year) & 
                (matriz_final_individual['Código Recepción'].notna()) & 
                (matriz_final_individual['Fecha Recepción'] < matriz_final_individual['Fecha Aprobación OC']))

matriz_final_individual.loc[condicion, 'Importe OC'] = matriz_final_individual['Monto Funcional']
matriz_final_individual.loc[condicion_oc, 'Importe OC'] = matriz_final_individual['Importe AC']


# ====================================================================== #
# LOGICA CARRYOVER INDIVIDUAL
# ====================================================================== #
# Columna Importe OC Auxiliar
matriz_final_individual['Nuevo Importe OC'] = matriz_final_individual['Importe OC'].copy()

# Condiciones
condicion_1 = (matriz_final_individual['Importe OC'] != matriz_final_individual['Importe AC'])
condicion_2 = (matriz_final_individual['CR menores 2026'] > 0)

condicion_3 = (matriz_final_individual['Importe OC'] == matriz_final_individual['Importe AC'])
condicion_4 = (matriz_final_individual['CR 2026'] > 0) & (matriz_final_individual['CR menores 2026'] > 0)

condicion_5 = (matriz_final_individual['Importe OC'] == matriz_final_individual['Importe AC']) & (matriz_final_individual['CR 2026'] == 0)

condicion_6 = ((matriz_final_individual['Año RQ'] < actual_year) & (matriz_final_individual['Año RQ'] != 0)) & (matriz_final_individual['Importe OC'] != matriz_final_individual['Importe AC menores 2026'])

# Aplicar las reglas de forma secuencial
for idx, row in matriz_final_individual.iterrows():
    if condicion_1[idx] & condicion_2[idx]:
        matriz_final_individual.at[idx, 'Nuevo Importe OC'] = (
            row['Importe OC'] - row['Importe AC'] + row['Importe AC 2026']
        )
        matriz_final_individual.at[idx, 'Importe AC'] = matriz_final_individual.at[idx, 'Importe AC 2026']
    elif condicion_3[idx] & condicion_4[idx]:
        matriz_final_individual.at[idx, 'Nuevo Importe OC'] = (
            row['Importe OC'] - row['Importe AC'] + row['Importe AC 2026']
        )
        matriz_final_individual.at[idx, 'Importe AC'] = matriz_final_individual.at[idx, 'Importe AC 2026']

    # elif condicion_5[idx]:
    #     matriz_final_individual.at[idx, 'Eliminar'] = True
    # elif condicion_6[idx]:
    #     matriz_final_individual.at[idx, 'SOLPE'] = round(matriz_final_individual.at[idx, 'Nuevo Importe OC'], 2)
    
    else:
        # Si ninguna condición se cumple, mantener el valor original
        matriz_final_individual.at[idx, 'Nuevo Importe OC'] = row['Importe OC']


# Actualizar 'Importe OC' con los valores correctos
matriz_final_individual['Importe OC'] = matriz_final_individual['Nuevo Importe OC']
matriz_final_individual.reset_index(drop=True, inplace=True)

# Eliminar la columna temporal
matriz_final_individual.drop(columns=['Nuevo Importe OC'], inplace=True)


#### 18. Extraer las columnas necesarias de CR - Detalles
# Seleccionar columnas a mostrar en CR - DETALLES
mf_individual_columns = [
    'RQ', 
    'Nro OC',
    'Nro Línea OC', 
    'Estado OC',
    'Fecha Emisión RQ',
    'Fecha Aprobación RQ',
    'Fecha Emisión OC',
    'Fecha Aprobación OC',
    'Descripción de RQ',
    'Descripción OC',
    'Descripción Adicional',
    'Código Recepción',
    'Fecha Recepción',
    'Código Proyecto',
    'Nombre Proyecto', 
    'Inversión/SubRubro', 
    'PM ACTUAL',
    'Gerencia Sponsor Final',
    'Acuerdo',
    'Proveedor',
    'Requisitor', 
    'Gerencia Requisitor',
    'Gerencia Sponsor',
    'Importe OC',
    'Importe AC',
    'Importe Facturado',
    'Importe RQ'
]

matriz_final_individual_selected = matriz_final_individual[mf_individual_columns]

# Si los campos de proveedor, requisitor y gerencia son vacíos rellenar por defecto "POR REVISAR"
matriz_final_individual_selected.loc[matriz_final_individual_selected['Proveedor'].isna(), 'Proveedor'] = 'POR REVISAR'
matriz_final_individual_selected.loc[matriz_final_individual_selected['Requisitor'].isna(), 'Requisitor'] = 'POR REVISAR'
matriz_final_individual_selected.loc[matriz_final_individual_selected['Gerencia Requisitor'].isna(), 'Gerencia Requisitor'] = 'POR REVISAR'


# ====================================================================== #
# LOGICA CARRYOVER AGRUPADO
# ====================================================================== #
#### 19. Configuracion Matriz RQ Agrupado
# Copia de la matriz original
matriz_final_agrupado = matriz_final.copy()

pos_2 = 1
# Dividir ID y nombre de línea
matriz_final_agrupado[['ID Linea', 'Nombre Linea']] = matriz_final_agrupado['Inversión/SubRubro'].str.extract(r'(^[\d\-]+)(.*)')
matriz_final_agrupado['ID Linea'] = matriz_final_agrupado['ID Linea'].str.strip('-')

# Generer Llave de union
concat_proyecto = matriz_final_agrupado['Código Proyecto'] + "_" + matriz_final_agrupado['ID Linea']
concat_proyecto_2 = matriz_final_agrupado['Código Proyecto'] + matriz_final_agrupado['ID Linea']
matriz_final_agrupado.insert(loc=pos_2, column='Key2', value=concat_proyecto.str.lower())
matriz_final_agrupado.insert(loc=pos_2, column='Llave', value=concat_proyecto_2.str.lower())

matriz_final_agrupado['Key4'] = matriz_final_agrupado['Key3'] + "_" + matriz_final_agrupado['Código Recepción'].astype(str)

# Convertir OC a 0 para realizar la suma correcta  
matriz_final_agrupado['Monto Comprometido'] = matriz_final_agrupado['Monto Comprometido'].where(~matriz_final_agrupado.duplicated(subset=['Key3']), 0)
matriz_final_agrupado['Monto Funcional'] = matriz_final_agrupado['Monto Funcional'].where(~matriz_final_agrupado.duplicated(subset=['Key3']), 0)

# Convertir DNU a 0 para realizar la suma correcta
matriz_final_agrupado['Declaración No Uso'] = matriz_final_agrupado['Declaración No Uso'].where(~matriz_final_agrupado.duplicated(subset=['Key3']), 0)

matriz_final_agrupado['Tipo'] = f"Proy. {matriz_final['Año RQ test'].astype(str)}"

# Cálculo Ordenes y Actas
matriz_final_agrupado['Importe OC'] = matriz_final_agrupado['Monto Comprometido'] * matriz_final_agrupado['Tipo Cambio']
matriz_final_agrupado['Importe AC'] = matriz_final_agrupado['Monto Recepcionado'] * matriz_final_agrupado['Tipo Cambio']
matriz_final_agrupado['Declaración No Uso'] = matriz_final_agrupado['Declaración No Uso'] * matriz_final_agrupado['Tipo Cambio']

# Convertir AC a 0 para realizar la suma correcta
matriz_final_agrupado['Importe AC'] = matriz_final_agrupado['Importe AC'].where(~matriz_final_agrupado.duplicated(subset=['Key4']), 0)

# Montos Actas solo del año actual y menores al mismo
matriz_final_agrupado['Importe AC 2026'] = matriz_final_agrupado.apply(
    lambda row: row['Monto Recepcionado'] * row['Tipo Cambio'] if row['Año Recepción'] == actual_year else 0,
    axis=1
)
matriz_final_agrupado['Importe AC menores 2026'] = matriz_final_agrupado.apply(
    lambda row: row['Monto Recepcionado'] * row['Tipo Cambio'] if row['Año Recepción'] < actual_year else 0,
    axis=1
)
matriz_final_agrupado['Importe Facturado'] = matriz_final_agrupado['Monto Facturado'] * matriz_final_agrupado['Tipo Cambio']
matriz_final_agrupado['Importe RQ'] = matriz_final_agrupado['Monto Funcional']

# Códigos de Recepción generados en el año actual y menores al mismo
matriz_final_agrupado['CR 2026'] = (matriz_final_agrupado['Año Recepción'] == actual_year).astype(int)
matriz_final_agrupado['CR menores 2026'] = (matriz_final_agrupado['Año Recepción'] < actual_year).astype(int) & (matriz_final_agrupado['Año Recepción'] != 0)

# Regla OC
condicion = (matriz_final_agrupado['Monto Comprometido'].isna() & 
             matriz_final_agrupado['RUC'].notna() & 
             (~matriz_final_agrupado['Estado OC'].isin(["Cancelada", "Incompleta"])))

condicion_oc = ((matriz_final_agrupado['Estado OC'] == 'Cancelada') & 
                    (matriz_final_agrupado['Año Aprobación OC'] >= actual_year) & 
                (matriz_final_agrupado['Código Recepción'].notna()) & 
                (matriz_final_agrupado['Fecha Recepción'] < matriz_final_agrupado['Fecha Aprobación OC']))


matriz_final_agrupado.loc[condicion, 'Importe OC'] = matriz_final_agrupado['Monto Funcional']
matriz_final_agrupado.loc[condicion_oc, 'Importe OC'] = matriz_final_agrupado['Importe AC']


matriz_final_agrupado = matriz_final_agrupado[~((matriz_final_agrupado['Año RQ'] < actual_year) &
                            (matriz_final_agrupado['Código Recepción'].isna()) &
                            (matriz_final_agrupado['Importe RQ'] == 0))]



#### 20. Agrupar Matriz RQ Agrupado
# Agrupar por RQ, ID Linea y Mes Recepcion
matriz_final_agrupado_rq = matriz_final_agrupado.groupby(['RQ', 'ID Linea', 'Mes Recepción']).agg({
    'Key2': 'first',
    'Nro OC': 'first',
    'Año RQ': 'first',
    'Mes': 'first',
    'Mes RQ': 'first',
    'Estado OC': 'first',
    'Estado OC Inicial': 'first',
    'Fecha Emisión RQ': 'first',
    'Fecha Aprobación RQ': 'first',
    'Fecha Emisión OC': 'first',
    'Fecha Aprobación OC': 'first',
    'Fecha Inicio de Proyecto': 'first',
    'Fecha de Fin de Proyecto': 'first',
    'Descripción OC': 'first',
    'Descripción Adicional': 'first',
    'Código Recepción': 'first',
    'Fecha Recepción': 'first',
    'Código Proyecto': 'first',
    'Nombre Proyecto': 'first',
    'Inversión/SubRubro': 'first',
    'Acuerdo': 'first',
    'Proveedor': 'first',
    'Requisitor': 'first',
    'PM ACTUAL': 'first',
    'Gerencia Requisitor': 'first',
    'Gerencia Sponsor': 'first',
    'Gerencia Sponsor Final': 'first',
    'Importe OC': 'sum',
    'Importe AC': 'sum',
    'Importe AC 2026': 'sum',
    'Importe AC menores 2026': 'sum',
    'Importe Facturado': 'sum',
    'Importe RQ': 'sum',
    'CR 2026': 'sum',
    'CR menores 2026': 'sum',
    'Monto Funcional': 'sum',
    'Año RQ': 'first', # Fecha Emision
    'Año Aprobación OC': 'first',
    'Año RQ test': 'first',
    'Llave': 'first',
    'Año Recepción': 'first',
    'Declaración No Uso': 'sum'
}).reset_index()


#### 21. JOIN LEFT: Matriz RQ Agrupado vs Provisiones
# MATCH PROVISIONES
matriz_final_agrupado_rq['Clave'] = matriz_final_agrupado_rq['RQ'].astype(str) + matriz_final_agrupado_rq['Nro OC'].astype(str) + matriz_final_agrupado_rq['Llave'].astype(str)
matriz_final_agrupado_rq = pd.merge(matriz_final_agrupado_rq, matriz_provision, on='Clave', how='left')

IS_2024 = matriz_final_agrupado_rq.groupby('Clave')['Año Recepción'].transform(lambda s: (s == 2024).any())
FIRST_2024 = matriz_final_agrupado_rq['Año Recepción'].eq(2024) & ~matriz_final_agrupado_rq.duplicated(['Clave', 'Año Recepción'])
primera_de_clave = ~matriz_final_agrupado_rq.duplicated('Clave')
mask = FIRST_2024 | (~IS_2024 & primera_de_clave)
matriz_final_agrupado_rq['Provisión Real'] = matriz_final_agrupado_rq['Provisión'].where(mask, 0)

# mask_2024_primera = matriz_final_agrupado_rq['Año Recepción'].eq(2024) & ~matriz_final_agrupado_rq.duplicated(['Clave', 'Año Recepción'])
# matriz_final_agrupado_rq['Provisión Real'] = matriz_final_agrupado_rq['Provisión'].where(mask_2024_primera, 0)
# matriz_final_agrupado_rq['Provisión Real'] = matriz_final_agrupado_rq['Provisión'].where(~matriz_final_agrupado_rq.duplicated(subset=['Clave'], keep='last'), 0)

matriz_final_agrupado_rq['Ahorro Real'] = matriz_final_agrupado_rq['Ahorro'].where(~matriz_final_agrupado_rq.duplicated(subset=['Clave'], keep='last'), 0)
condicion = ((matriz_final_agrupado_rq['Provisión'].isna()) | ((matriz_final_agrupado_rq['Provisión'] == "-")))
matriz_final_agrupado_rq.loc[condicion, 'Provisión'] = 0
condicion_sd = ((matriz_final_agrupado_rq['Provisión Real'].isna()) | ((matriz_final_agrupado_rq['Provisión Real'] == "-")))
matriz_final_agrupado_rq.loc[condicion_sd, 'Provisión Real'] = 0

matriz_final_agrupado_rq = matriz_final_agrupado_rq.drop(columns=['Clave', 'Llave_2', 'RQ_2', 'Nro OC_2'])


#### 22. Lógica CARRYOVER - Matriz RQ Agrupado
# REDONDEAR MONTOS
matriz_final_agrupado_rq['Importe OC'] = matriz_final_agrupado_rq['Importe OC'].round(2)
matriz_final_agrupado_rq['Importe AC'] = matriz_final_agrupado_rq['Importe AC'].round(2)
matriz_final_agrupado_rq['Importe AC 2026'] = matriz_final_agrupado_rq['Importe AC 2026'].round(2)
matriz_final_agrupado_rq['Importe AC menores 2026'] = matriz_final_agrupado_rq['Importe AC menores 2026'].round(2)
matriz_final_agrupado_rq['Importe Facturado'] = matriz_final_agrupado_rq['Importe Facturado'].round(2)
matriz_final_agrupado_rq['Importe RQ'] = matriz_final_agrupado_rq['Importe RQ'].round(2)

# Auxiliar
matriz_final_agrupado_rq['Nuevo Importe OC'] = matriz_final_agrupado_rq['Importe OC'].copy()
# Inicializar la columna SOLPE y ORIGINAL en 0
matriz_final_agrupado_rq['SOLPE'] = 0.0  
matriz_final_agrupado_rq['SOLPE ORIGINAL'] = 0.0 
matriz_final_agrupado_rq['Tipo'] = "Proy."

# Inicializar la columna 'Eliminar' como False
matriz_final_agrupado_rq['Eliminar'] = False

# Duplicar Importes
matriz_final_agrupado_rq['Importe OC Original'] = matriz_final_agrupado_rq['Importe OC'].copy()
matriz_final_agrupado_rq['Importe AC Original'] = matriz_final_agrupado_rq['Importe AC'].copy()

matriz_final_agrupado_rq['Periodo'] = matriz_final_agrupado_rq['Nombre Proyecto'].apply(lambda x: actual_year if str(actual_year) in x else actual_year - 1)

# ######## NEW
# s = matriz_final_agrupado_rq['Nombre Proyecto'].astype('string')
# mask = s.str.contains(str(actual_year), na=False, regex=False)

# matriz_final_agrupado_rq['Periodo'] = (
#     np.where(mask, int(actual_year), int(actual_year) - 1).astype('int64')
# )
# ##############


# Condiciones
condicion_init_actual_year = ((matriz_final_agrupado_rq['Estado OC Inicial'] == "Abierta") | (matriz_final_agrupado_rq['Estado OC Inicial'].isna()) | (matriz_final_agrupado_rq['Estado OC Inicial'] == "Pendiente Aprobación")) & (matriz_final_agrupado_rq['Periodo'] == actual_year)
condicion_init = ((matriz_final_agrupado_rq['Estado OC Inicial'] == "Abierta") | (matriz_final_agrupado_rq['Estado OC Inicial'].isna()) | (matriz_final_agrupado_rq['Estado OC Inicial'] == "Pendiente Aprobación")) & (matriz_final_agrupado_rq['Periodo'] < actual_year)
condicion_init_not = (matriz_final_agrupado_rq['Estado OC Inicial'].astype(str).str.startswith("Cerrada")) & (matriz_final_agrupado_rq['Fecha Emisión OC'].dt.year < actual_year)

condicion_1 = (matriz_final_agrupado_rq['Importe OC'] != matriz_final_agrupado_rq['Importe AC'])
condicion_2 = (matriz_final_agrupado_rq['CR menores 2026'] >= 0)

condicion_3 = (matriz_final_agrupado_rq['Importe OC'] == matriz_final_agrupado_rq['Importe AC'])
condicion_4 = (matriz_final_agrupado_rq['CR 2026'] > 0) & (matriz_final_agrupado_rq['CR menores 2026'] > 0)

condicion_5 = (matriz_final_agrupado_rq['Importe OC'] == matriz_final_agrupado_rq['Importe AC']) & (matriz_final_agrupado_rq['CR 2026'] == 0)

condicion_6 = ((matriz_final_agrupado_rq['Año RQ'] < actual_year) & (matriz_final_agrupado_rq['Año RQ'] != 0)) & (matriz_final_agrupado_rq['Importe OC'] != matriz_final_agrupado_rq['Importe AC menores 2026'])

# Aplicar las reglas de forma secuencial
for idx, row in matriz_final_agrupado_rq.iterrows():
    if  condicion_init[idx] & condicion_1[idx] & condicion_2[idx]:
        matriz_final_agrupado_rq.at[idx, 'Nuevo Importe OC'] = (
            row['Importe OC'] - row['Importe AC'] + row['Importe AC 2026']
        )
        matriz_final_agrupado_rq.at[idx, 'Tipo'] = "CARRYOVER"
        matriz_final_agrupado_rq.at[idx, 'Importe AC'] = matriz_final_agrupado_rq.at[idx, 'Importe AC 2026'] 
        
    elif condicion_init[idx] & condicion_3[idx] & condicion_4[idx]:
        matriz_final_agrupado_rq.at[idx, 'Nuevo Importe OC'] = (
            row['Importe OC'] - row['Importe AC'] + row['Importe AC 2026']
        )
        matriz_final_agrupado_rq.at[idx, 'Tipo'] = "CARRYOVER"
        matriz_final_agrupado_rq.at[idx, 'Importe AC'] = matriz_final_agrupado_rq.at[idx, 'Importe AC 2026']
    
    elif condicion_5[idx]:
        matriz_final_agrupado_rq.at[idx, 'Eliminar'] = True
        matriz_final_agrupado_rq.at[idx, 'Importe OC'] = 0
        matriz_final_agrupado_rq.at[idx, 'Importe AC'] = 0

    elif condicion_init_actual_year[idx] & condicion_1[idx] & condicion_2[idx]:
        matriz_final_agrupado_rq.at[idx, 'Nuevo Importe OC'] = (
            row['Importe OC'] - row['Importe AC'] + row['Importe AC 2026']
        )
        matriz_final_agrupado_rq.at[idx, 'Importe AC'] = matriz_final_agrupado_rq.at[idx, 'Importe AC 2026'] 

    # elif condicion_6[idx]:
    #     matriz_final_agrupado_rq.at[idx, 'Tipo'] = "CARRYOVER"
        
    elif condicion_init_not[idx]:
        # matriz_final_agrupado_rq.at[idx, 'SOLPE'] = round(matriz_final_agrupado_rq.at[idx, 'Nuevo Importe OC'], 2)
        matriz_final_agrupado_rq.at[idx, 'Nuevo Importe OC'] = 0
        matriz_final_agrupado_rq.at[idx, 'Importe AC'] = matriz_final_agrupado_rq.at[idx, 'Importe AC 2026']
        
    else:
        # Si ninguna condición se cumple, mantener el valor original
        matriz_final_agrupado_rq.at[idx, 'Nuevo Importe OC'] = row['Importe OC']


# # Filtrar para excluir los registros marcados

matriz_final_filtrado = matriz_final_agrupado_rq.copy()
# matriz_final_filtrado = matriz_final_agrupado_rq[matriz_final_agrupado_rq['Eliminar'] == False].copy()

# Reindexar el DataFrame para evitar huecos en los índices
# matriz_final_filtrado.reset_index(drop=True, inplace=True)
matriz_final_filtrado.loc[matriz_final_filtrado['Eliminar'] == False, 'Importe OC'] = matriz_final_filtrado['Nuevo Importe OC']
        
# Actualizar 'Importe OC' con los valores correctos
# matriz_final_filtrado['Importe OC'] = matriz_final_filtrado['Nuevo Importe OC']

# Restar Provision
matriz_final_filtrado['Importe OC'] = matriz_final_filtrado['Importe OC'] - matriz_final_filtrado['Provisión Real']

mask = matriz_final_filtrado.groupby('Código Proyecto')['Tipo'].transform(lambda tipos: (tipos == "CARRYOVER").any())
matriz_final_filtrado.loc[mask, 'SOLPE'] = matriz_final_filtrado.loc[mask, 'Importe OC']

matriz_final_filtrado.loc[matriz_final_filtrado['Provisión'].ne(0), 'Importe AC'] = matriz_final_filtrado['Importe AC'] - matriz_final_filtrado['Provisión Real']


suma_por_oc_old = matriz_final_filtrado.groupby('Nro OC')['Importe AC'].transform('sum').fillna(0)
suma_por_oc_old = suma_por_oc_old.round(2)
matriz_final_filtrado['Importe AC Mes'] = matriz_final_filtrado['Importe AC'].where(suma_por_oc_old > 0, 0)

matriz_final_filtrado.loc[suma_por_oc_old >= 0, 'Declaración No Uso'] = matriz_final_filtrado['Declaración No Uso']
matriz_final_filtrado.loc[suma_por_oc_old < 0, 'Declaración No Uso'] = matriz_final_filtrado['Declaración No Uso'] + matriz_final_filtrado['Importe AC']
# matriz_final_filtrado['Declaración No Uso'] = matriz_final_filtrado['Declaración No Uso'] - matriz_final_filtrado['Provisión Real']

# Eliminar la columna temporal
matriz_final_filtrado.drop(columns=['Nuevo Importe OC', 'Eliminar'], inplace=True)


# Añadir categoia Harware y Servicios
matriz_final_filtrado['Categoría'] = ""
matriz_final_filtrado['ID Inversion'] = matriz_final_filtrado['Inversión/SubRubro'].str.split("-").str[0]

matriz_final_filtrado.loc[(matriz_final_filtrado['ID Inversion'] == "1") | (matriz_final_filtrado['ID Inversion'] == "3") | (matriz_final_filtrado['ID Inversion'] == "4"), 'Categoría'] = "Hardware"
matriz_final_filtrado.loc[(matriz_final_filtrado['ID Inversion'] == "2"), 'Categoría'] = "Servicios"


# Mostrar como Diciembre montos de años anteriores.
matriz_final_filtrado.loc[((matriz_final_filtrado['Año RQ'] < actual_year) | ((matriz_final_filtrado['Año RQ'].isna()) & (matriz_final_filtrado['Fecha Emisión OC'].dt.year < actual_year))), 'Mes RQ'] = 'Dic 25'


#### 23. Añadir llave 3 para UNIR Matriz RQ Agrupado vs Matriz FCST
pos = 0

matriz_fcst[['ID Linea SOLPE', 'Nombre Linea SOLPE']] = matriz_fcst['Linea de Inversión'].str.extract(r'(^[\d\-]+)(.*)')
matriz_fcst['ID Linea SOLPE'] = matriz_fcst['ID Linea SOLPE'].str.strip('-')

concat_proyecto_4 = matriz_fcst['Project Number (ORACLE)'] + "_" + matriz_fcst['ID Linea SOLPE']
matriz_fcst.insert(loc=pos, column='Key2', value=concat_proyecto_4.str.lower())

cond = (matriz_fcst['Key2'].isna())
matriz_fcst.loc[cond, 'Key2'] = matriz_fcst['Project Number (ORACLE)'] + "_" + matriz_fcst['Linea de Inversión']

matriz_fcst.loc[matriz_fcst['Jefatura Final'].isna(), 'Jefatura Final'] = 'Revisar'
matriz_fcst.loc[matriz_fcst['Gerencia'].isna(), 'Gerencia'] = 'Revisar'


#### 24. Seleccionar columnas especificas en la Matriz FCST
selected_columns = matriz_fcst.drop(columns=['Llave', 'Llave2', 'ID Linea SOLPE', 'Nombre Linea SOLPE','ID','PM'])


#### 25. Agrupar Matriz RQ Agrupado por RQ, OC y Linea de Inversion
matriz_final_filtrado['Importe OC 2'] = matriz_final_filtrado['Importe OC'].copy()
matriz_final_filtrado['Importe AC 2'] = matriz_final_filtrado['Importe AC'].copy()
matriz_final_filtrado['Importe Facturado 2'] = matriz_final_filtrado['Importe Facturado'].copy()
matriz_final_filtrado['Importe RQ 2'] = matriz_final_filtrado['Importe RQ'].copy()

selects_matriz_final = ['RQ', 
                      'Nro OC', 
                      'Estado OC',
                      'Fecha Emisión RQ',
                      'Fecha Aprobación RQ',
                      'Fecha Emisión OC', 
                      'Fecha Aprobación OC',
                      'Fecha Inicio de Proyecto',
                      'Fecha de Fin de Proyecto',
                      'Tipo',
                      'Código Proyecto', 
                      'Nombre Proyecto', 
                      'Inversión/SubRubro',
                      'Categoría',
                      'Acuerdo',
                      'Proveedor',
                      'Requisitor', 
                      'PM ACTUAL', 
                      'Gerencia Requisitor', 
                      'Gerencia Sponsor',
                      'Gerencia Sponsor Final', 
                      'Importe OC', 
                      'Importe AC', 
                      'Importe Facturado', 
                      'Importe RQ', 
                      'CR 2026',
                      'CR menores 2026',
                      'Key2',
                      #'Mes',
                      #'Mes Recepción',
                      'Llave',
                      'Año RQ test',
                      'Provisión Real',
                      'Ahorro Real',
                      'Declaración No Uso'
                      #'Importe OC Original', 
                      #'Importe AC Original',
                      #'Importe AC 2025',
                      #'Importe AC menores 2025'
                       ]

# # Descripción OC = Descripción Linea OC

matriz_final_filtrado_selected = matriz_final_filtrado[selects_matriz_final]

matriz_final_filtrado_selected_group = matriz_final_filtrado_selected.groupby(['RQ', 'Nro OC', 'Inversión/SubRubro']).agg({
    'Estado OC': 'first',
    'Fecha Emisión RQ': 'first',
    'Fecha Aprobación RQ': 'first',
    'Fecha Emisión OC': 'first',
    'Fecha Aprobación OC': 'first',
    'Fecha Inicio de Proyecto': 'first',
    'Fecha de Fin de Proyecto': 'first',
    'Tipo': 'first',
    'Código Proyecto': 'first',
    'Nombre Proyecto': 'first',
    'Categoría': 'first',
    'Acuerdo': 'first',
    'Proveedor': 'first',
    'Requisitor': 'first',
    'PM ACTUAL': 'first',
    'Gerencia Requisitor': 'first',
    'Gerencia Sponsor': 'first',
    'Gerencia Sponsor Final': 'first',
    'Importe OC': 'sum',
    # 'Importe AC': 'sum',
    'Importe AC': lambda s: max(pd.to_numeric(s, errors='coerce').sum(), 0),
    'Importe Facturado': 'sum',
    'Importe RQ': 'sum',
    'CR 2026': 'sum',
    'CR menores 2026': 'sum',
    'Key2': 'first',
    #'Mes': 'first',
    #'Mes Recepción': 'first',
    'Llave': 'first',
    'Año RQ test': 'first',
    'Provisión Real': 'sum',
    'Ahorro Real': 'sum',
    'Declaración No Uso': 'sum'
    #'Importe OC Original': 'sum',
    #'Importe AC Original': 'sum',
    #'Importe AC 2025': 'sum',
    #'Importe AC menores 2025': 'sum'
}).reset_index()

resta_menor_dnu = (matriz_final_filtrado_selected_group['Declaración No Uso'] < 0)
matriz_final_filtrado_selected_group.loc[resta_menor_dnu, 'Declaración No Uso'] = 0


# #Obtén la lista de columnas
columnas = list(matriz_final_filtrado_selected_group.columns)

# Encuentra los índices de las columnas que deseas mover
indice_nombre = columnas.index('Nombre Proyecto') #10
indice_li = columnas.index('Inversión/SubRubro')
columna_li = columnas.pop(indice_li)
columnas.insert(indice_nombre, columna_li)

# Reorganiza el DataFrame con las columnas movidas
matriz_final_filtrado_selected_group = matriz_final_filtrado_selected_group[columnas]

#### 26. JOIN: RQ Agrupado vs FCST
columns_to_select = ['Key2', 'Jefatura Final', 'Unidad Funcional', 'Gerencia', 'Trimestre', 'Trimestre Real', 'Avance Proyecto']
matriz_fcst_select = matriz_fcst[columns_to_select]

matriz_final_filtrado_selected_group_j = pd.merge(matriz_final_filtrado_selected_group, matriz_fcst_select, on='Key2', how='left')


#### 27. Añadir lógica de no ingreso de OC para proyectos CARRYOVER
matriz_final_filtrado_selected_group_j['IS_2024'] = matriz_final_filtrado_selected_group_j['Nombre Proyecto'].apply(lambda x: actual_year - 1 if str(actual_year - 1) in x else 2099)
matriz_final_filtrado_selected_group_j['Comentarios'] = matriz_final_filtrado_selected_group_j.apply(lambda row: 'Observado' if row['Año RQ test'] > row['IS_2024'] else '-', axis=1)

#Remover columna IS_2024
matriz_final_filtrado_selected_group_j = matriz_final_filtrado_selected_group_j.drop(columns=['IS_2024'])

suma_por_oc = matriz_final_filtrado.groupby('Nro OC')['Importe AC'].transform('sum').fillna(0)

## 1. Regla 1: la suma del OC > umbral, copiamos Importe AC; si no, 0
suma_por_oc = suma_por_oc.round(2)
eps = 1e-6
matriz_final_filtrado['Importe AC Mes'] = matriz_final_filtrado['Importe AC'].where(suma_por_oc > eps, 0)

## 2. Regla 2: si hay 2024 en el OC y el valor del mes es POSITIVO,
mes_orden = {
    'Enero':1,'Febrero':2,'Marzo':3,'Abril':4,'Mayo':5,'Junio':6,
    'Julio':7,'Agosto':8,'Septiembre':9,'Setiembre':9,'Octubre':10,
    'Noviembre':11,'Diciembre':12
}
col_anio = 'Año Recepción'      # ajusta si tu columna se llama distinto (con tilde)
col_mes  = 'Mes Recepción'      # idem

def ajustar_carry(grp: pd.DataFrame) -> pd.DataFrame:
    # ¿hay filas con año 2024 o 0?
    tiene_base = grp[col_anio].isin([2024, 0]).any()

    # Solo aplica si hay base (2024/0) Y el total del OC es > umbral
    if not (tiene_base and grp['Importe AC'].sum() > 0):
        return grp

    # Deuda = suma de Importe AC de años 2024 o 0 (suele ser negativa)
    deuda = grp.loc[grp[col_anio].isin([2024, 0]), 'Importe AC'].sum()

    # Recorremos años futuros (>= 2025) en orden Año, Mes
    future = grp[grp[col_anio] > 0].copy()
    future['_m'] = future[col_mes].map(mes_orden).fillna(99).astype(int)
    future = future.sort_values([col_anio, '_m'], kind='mergesort')

    carry = deuda
    for idx, row in future.iterrows():
        val = row['Importe AC']
        if val > 0:
            if carry < 0:
                nuevo = val + carry
                if abs(nuevo) <= 0:
                    nuevo = 0.0
                grp.at[idx, 'Importe AC Mes'] = nuevo
                carry = nuevo
            else:
                # deuda ya cubierta: dejar igual al Importe AC
                grp.at[idx, 'Importe AC Mes'] = val
        # si no es positivo, se deja como está (0 o el valor base)
    return grp


matriz_final_filtrado = matriz_final_filtrado.groupby('Nro OC', group_keys=False).apply(ajustar_carry)

prov_resta_menor = (matriz_final_filtrado['Importe AC Mes'] < 0)
matriz_final_filtrado.loc[prov_resta_menor, 'Importe AC Mes'] = 0


#### 28. Transmutar filas a columnas mostrando Enero a Diciembre para OC, AC, Facturado y RQ
# Agrupar datos
# Pivotamos los datos para crear columnas separadas para cada mes de OC y AC
pivoted_oc = matriz_final_filtrado.pivot_table(index='Key2', columns=['Mes RQ'], values='Importe OC 2', aggfunc='sum').fillna(0)
pivoted_ac = matriz_final_filtrado.pivot_table(index='Key2', columns=['Mes Recepción'], values='Importe AC Mes', aggfunc='sum').fillna(0)
# pivoted_ac = matriz_final_filtrado.pivot_table(index='Key2', columns='Mes Recepción', values='Importe AC 2', aggfunc=lambda s: max(pd.to_numeric(s, errors='coerce').sum(), 0), fill_value=0)
pivoted_fa = matriz_final_filtrado.pivot_table(index='Key2', columns=['Mes RQ'], values='Importe Facturado 2', aggfunc='sum').fillna(0)
pivoted_rq = matriz_final_filtrado.pivot_table(index='Key2', columns=['Mes RQ'], values='Monto Funcional', aggfunc='sum').fillna(0)

# Renombramos las columnas para identificar si es OC o AC
pivoted_oc.columns = [f'{mes} - OC' for mes in pivoted_oc.columns]
pivoted_ac.columns = [f'{mes} - AC' for mes in pivoted_ac.columns]
pivoted_fa.columns = [f'{mes} - Facturado' for mes in pivoted_fa.columns]
pivoted_rq.columns = [f'{mes} - RQ' for mes in pivoted_rq.columns]

# Meses Esperados
meses_oc_esperado = ['Dic 25 - OC', 'Enero - OC', 'Febrero - OC', 'Marzo - OC', 'Abril - OC', 'Mayo - OC', 'Junio - OC', 'Julio - OC', 'Agosto - OC', 'Setiembre - OC', 'Octubre - OC', 'Noviembre - OC', 'Diciembre - OC']
meses_fact_esperado = ['Dic 25 - Facturado', 'Enero - Facturado', 'Febrero - Facturado', 'Marzo - Facturado', 'Abril - Facturado', 'Mayo - Facturado', 'Junio - Facturado', 'Julio - Facturado', 'Agosto - Facturado', 'Setiembre - Facturado', 'Octubre - Facturado', 'Noviembre - Facturado', 'Diciembre - Facturado']
meses_rq_esperado = ['Dic 25 - RQ', 'Enero - RQ', 'Febrero - RQ', 'Marzo - RQ', 'Abril - RQ', 'Mayo - RQ', 'Junio - RQ', 'Julio - RQ', 'Agosto - RQ', 'Setiembre - RQ', 'Octubre - RQ', 'Noviembre - RQ', 'Diciembre - RQ']
meses_ordenados = ['Dic 25', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Setiembre', 'Octubre', 'Noviembre', 'Diciembre']

columnas_oc_faltantes = set(meses_oc_esperado) - set(pivoted_oc.columns)
columnas_fact_faltantes = set(meses_fact_esperado) - set(pivoted_fa.columns)
columnas_rq_faltantes = set(meses_rq_esperado) - set(pivoted_rq.columns)

# Agregar las columnas OC faltantes con valor 0
for column_oc in columnas_oc_faltantes:
    pivoted_oc[column_oc] = 0

# Agregar las columnas FA faltantes con valor 0
for column_fa in columnas_fact_faltantes:
    pivoted_fa[column_fa] = 0

# Agregar las columnas RQ faltantes con valor 0
for column_rq in columnas_rq_faltantes:
    pivoted_rq[column_rq] = 0

columnas_oc_ordenadas = [f'{mes} - OC' for mes in meses_ordenados if f'{mes} - OC' in pivoted_oc.columns]
columnas_ac_ordenadas = [f'{mes} - AC' for mes in meses_ordenados if f'{mes} - AC' in pivoted_ac.columns]
columnas_fa_ordenadas = [f'{mes} - Facturado' for mes in meses_ordenados if f'{mes} - Facturado' in pivoted_fa.columns]
columnas_rq_ordenadas = [f'{mes} - RQ' for mes in meses_ordenados if f'{mes} - RQ' in pivoted_rq.columns]

# Reorganiza las columnas de pivoted_oc y pivoted_ac en el orden correcto
pivoted_oc = pivoted_oc[columnas_oc_ordenadas]
pivoted_ac = pivoted_ac[columnas_ac_ordenadas]
pivoted_fa = pivoted_fa[columnas_fa_ordenadas]
pivoted_rq = pivoted_rq[columnas_rq_ordenadas]

# Agrupamos los resultados de OC y AC con el dataframe original
matriz_final_agrupado_key_2 = matriz_final_filtrado.groupby('Key2').agg({
    'Código Proyecto': 'first',
    'Nombre Proyecto': 'first',
    'Inversión/SubRubro': 'first',
    'Gerencia Requisitor': 'first',
    'Tipo': lambda x: 'CARRYOVER' if 'CARRYOVER' in x.values else 'Proy.',
    'Año RQ test': 'max',
    'PM ACTUAL': 'first',
    # 'Requisitor': lambda x: ' - '.join(sorted(set(filter(None, x)))),
    'Requisitor': lambda x: ' - '.join(
        sorted(set(str(v).strip() for v in x if pd.notna(v) and str(v).strip() != ''))
    ),
    'Importe OC 2': 'sum',
    'Importe AC 2': lambda s: max(pd.to_numeric(s, errors='coerce').sum(), 0),
    'Importe AC Mes': 'sum',
    'Importe Facturado 2': 'sum',
    'Importe RQ 2': 'sum',
    'SOLPE': 'sum',
    'SOLPE ORIGINAL': 'sum',
    'Importe OC Original': 'sum',
    'Importe AC Original': 'sum',
    'Provisión Real': 'sum',
    'Declaración No Uso': 'sum',
    'Gerencia Sponsor Final': 'first'
}).reset_index()

# Rellanar como 0 SI IMPORTE AC es negativo
# prov_resta_menor = (matriz_final_agrupado_key_2['Importe AC 2'] < 0)
# matriz_final_agrupado_key_2.loc[prov_resta_menor, 'Importe AC 2'] = 0

# Unimos los datos pivotados
matriz_final_agrupado_key_2 = matriz_final_agrupado_key_2.merge(pivoted_oc, on='Key2', how='left')
matriz_final_agrupado_key_2['Importe OC'] = matriz_final_agrupado_key_2['Importe OC 2'].copy()
matriz_final_agrupado_key_2['Dic 25 - AC'] = 0.0
matriz_final_agrupado_key_2 = matriz_final_agrupado_key_2.merge(pivoted_ac, on='Key2', how='left')
matriz_final_agrupado_key_2['Importe AC'] = matriz_final_agrupado_key_2['Importe AC Mes'].copy()

#NEW
matriz_final_agrupado_key_2 = matriz_final_agrupado_key_2.merge(pivoted_fa, on='Key2', how='left')
matriz_final_agrupado_key_2['Importe Facturado'] = matriz_final_agrupado_key_2['Importe Facturado 2'].copy()
matriz_final_agrupado_key_2 = matriz_final_agrupado_key_2.merge(pivoted_rq, on='Key2', how='left')
matriz_final_agrupado_key_2['Importe RQ'] = matriz_final_agrupado_key_2['Importe RQ 2'].copy()
# Rellenamos posibles valores NaN con 0
# matriz_final_agrupado_key_2.fillna(0, inplace=True)

# NEW
str_cols = matriz_final_agrupado_key_2.select_dtypes(include=['object', 'string']).columns
matriz_final_agrupado_key_2[str_cols] = matriz_final_agrupado_key_2[str_cols].fillna('')
num_cols = matriz_final_agrupado_key_2.select_dtypes(include=['number']).columns
matriz_final_agrupado_key_2[num_cols] = matriz_final_agrupado_key_2[num_cols].fillna(0)
# 

# Remover columnas innecesarias
matriz_final_agrupado_key_2 = matriz_final_agrupado_key_2.drop(columns=['Importe OC 2', 'Importe Facturado 2', 'Importe RQ 2', 'Importe AC Mes'])


#### 29. Limpieza Matriz Solpe
pos = 0
concat_id = matriz_solpe['Project Number'] + "_" + matriz_solpe['Task Number']
matriz_solpe.insert(loc=pos, column='Key2', value=concat_id.str.lower())

matriz_solpe = matriz_solpe.reset_index(drop=True)
dup = matriz_solpe.index[matriz_solpe.index.duplicated()]

# Generar Llave y seleccionar especificas columnas en Matriz SOLPE
matriz_solpe.loc[matriz_solpe['Key2'].isna(), 'Key2'] = matriz_solpe['Project Number'] + "_" + matriz_solpe['Task Name']
matriz_solpe['Linea de Inversión'] = matriz_solpe['Task Number'] + "-" + matriz_solpe['Task Name']
selected_solpe_columns = ['Key2', 'Project Number', 'Project Name', 'Linea de Inversión', 'Estado Ptto', 'PRESUPUESTO ORIGINAL','PRESUPUESTO HABILITADO', 'Tipo Proyecto']
matriz_solpe = matriz_solpe[selected_solpe_columns]
matriz_solpe['IS_SOLPE'] = "OK"

# JOIN FULL: Proyectos vs SOLPE
matriz_resultante = pd.merge(matriz_final_agrupado_key_2, matriz_solpe, on='Key2', how='outer')


#### 30. JOIN: Proyectos vs SOLPE
matriz_final_filtrado_selected_group_j = pd.merge(matriz_final_filtrado_selected_group_j, matriz_solpe, on='Key2', how='left')
matriz_final_filtrado_selected_group_j['Tipo'] = matriz_final_filtrado_selected_group_j['Tipo'].combine_first(matriz_final_filtrado_selected_group_j['Tipo Proyecto'])

cond_filter = ((matriz_final_filtrado_selected_group_j['IS_SOLPE'].isna()) & (matriz_final_filtrado_selected_group_j['Año RQ test'] < actual_year))

matriz_final_filtrado_selected_group_j.loc[cond_filter, 'Tipo'] = "Proy. antiguo"

matriz_final_filtrado_selected_group_j.drop(columns=['Key2', 'Año RQ test', 'Project Number', 'Project Name', 'Linea de Inversión', 'PRESUPUESTO ORIGINAL', 'PRESUPUESTO HABILITADO', 'Tipo Proyecto', 'IS_SOLPE'], inplace=True)

## CONVERTIR CARRYOVER
mask_3 = matriz_final_filtrado_selected_group_j.groupby('Código Proyecto')['Tipo'].transform(lambda x: (x == "CARRYOVER").any())
matriz_final_filtrado_selected_group_j.loc[mask_3, 'Tipo'] = "CARRYOVER"


# Rellenar vacíos
matriz_resultante['Código Proyecto'] = matriz_resultante['Código Proyecto'].combine_first(matriz_resultante['Project Number'])  
matriz_resultante['Nombre Proyecto'] = matriz_resultante['Nombre Proyecto'].combine_first(matriz_resultante['Project Name'])
matriz_resultante['Inversión/SubRubro'] = matriz_resultante['Inversión/SubRubro'].combine_first(matriz_resultante['Linea de Inversión'])
matriz_resultante['SOLPE ORIGINAL'] = matriz_resultante['SOLPE ORIGINAL'].replace(0, np.nan).combine_first(matriz_resultante['PRESUPUESTO ORIGINAL'])
# matriz_resultante['SOLPE'] = matriz_resultante['SOLPE'].replace(0, np.nan).combine_first(matriz_resultante['PRESUPUESTO HABILITADO'])
matriz_resultante['SOLPE'] = matriz_resultante['SOLPE'].combine_first(matriz_resultante['PRESUPUESTO HABILITADO'])

mask_2 = ((matriz_resultante['Año RQ test'] == actual_year) | (matriz_resultante['Nombre Proyecto'].str.contains(str(actual_year))))
matriz_resultante.loc[mask_2, 'SOLPE'] = np.where(
    matriz_resultante.loc[mask_2, 'SOLPE'] == 0,
    matriz_resultante.loc[mask_2, 'PRESUPUESTO HABILITADO'],
    matriz_resultante.loc[mask_2, 'SOLPE']
)
matriz_resultante['Tipo'] = matriz_resultante['Tipo'].combine_first(matriz_resultante['Tipo Proyecto'])


#  Rellenar SOLPE 0 si cumple las condiciones
# Aplica para proyectos menores al año actual
condicion_void = ((matriz_resultante['Importe OC'].isna()) & ((matriz_resultante['Año RQ test'] < actual_year) & (matriz_resultante['Año RQ test'] != 0)))
matriz_resultante.loc[condicion_void, 'SOLPE'] = 0


condicion_actual_year = ((matriz_resultante['Año RQ test'] < actual_year) & (matriz_resultante['Nombre Proyecto'].str.contains(str(actual_year))))
matriz_resultante.loc[condicion_actual_year, 'SOLPE'] = matriz_resultante.loc[condicion_actual_year, 'SOLPE'] - matriz_resultante['Importe AC Original'] + matriz_resultante['Importe AC 2']


# Actualizar Tipo como "CARRYOVER" si un proyecto tiene como minimo una linea como CARRYOVER
has_co = matriz_resultante.groupby('Código Proyecto')['Tipo'].transform(lambda x: (x == "CARRYOVER").any())
matriz_resultante.loc[has_co, 'Tipo'] = "CARRYOVER"

matriz_resultante = matriz_resultante[
    ((~has_co) & (matriz_resultante['SOLPE'] != 0)) |
    ((has_co) & (matriz_resultante['Tipo'] != 'Proy.') & (matriz_resultante['SOLPE'] > 0))
]

# Aplica para proyectos que tienen como tipo "CARRYOVER" y "PROY".
proyectos_co = matriz_resultante.loc[matriz_resultante['Tipo'] == "CARRYOVER", 'Código Proyecto'].unique()
matriz_resultante = matriz_resultante[~((matriz_resultante['Código Proyecto'].isin(proyectos_co)) & (matriz_resultante['Tipo'] == "Proy."))]
mask = (
    (
        matriz_resultante['Año RQ test'].notnull() & (matriz_resultante['Año RQ test'] != '') & (matriz_resultante['Año RQ test'] > actual_year - 2)
    ) |
    (
        (matriz_resultante['Año RQ test'].isnull() | (matriz_resultante['Año RQ test'] == '')) & (matriz_resultante['Nombre Proyecto'].str.contains(str(actual_year)))
    )
)

matriz_resultante = matriz_resultante[mask]

# Remover columnas inncesarias
matriz_resultante = matriz_resultante.drop(columns=['Project Number', 'Project Name', 'Linea de Inversión', 'PRESUPUESTO ORIGINAL', 'PRESUPUESTO HABILITADO', 'Importe OC Original', 'Importe AC Original','Tipo Proyecto','Importe AC 2'])



# Remover SOLPES VACIAS
matriz_resultante['Eliminar'] = False
cond_remove = ((matriz_resultante['SOLPE'].isna()) & (matriz_resultante['IS_SOLPE'].isna()) & (matriz_resultante['Año RQ test'] < actual_year))
matriz_resultante.loc[cond_remove, 'Eliminar'] = True

matriz_resultante = matriz_resultante[matriz_resultante['Eliminar'] == False].copy()
matriz_resultante.reset_index(drop=True, inplace=True)

# remover columna temp
matriz_resultante.drop(columns=['Eliminar', 'IS_SOLPE', 'Año RQ test'], inplace=True)


#### 31. JOIN: Proyectos vs FCST y Master Plan
# JOIN FULL: Proyectos vs FCST
matriz_resultante = pd.merge(matriz_resultante, selected_columns, on='Key2', how='outer')

# Rellenar vacios
matriz_resultante['Código Proyecto'] = matriz_resultante['Código Proyecto'].combine_first(matriz_resultante['Project Number (ORACLE)'])
matriz_resultante['Nombre Proyecto'] = matriz_resultante['Nombre Proyecto'].combine_first(matriz_resultante['Proyecto'])
matriz_resultante['Inversión/SubRubro'] = matriz_resultante['Inversión/SubRubro'].combine_first(matriz_resultante['Linea de Inversión'])
matriz_resultante['Gerencia'] = matriz_resultante['Gerencia'].combine_first(matriz_resultante['Gerencia Requisitor'])
matriz_resultante['Tipo'] = matriz_resultante['Tipo'].combine_first(matriz_resultante['Tipo Proyecto'])

# Eliminar columnas inncesarias
matriz_resultante = matriz_resultante.drop(columns=['Project Number (ORACLE)', 'Proyecto', 'Linea de Inversión', 'PM ACTUAL', 'Gerencia Sponsor Final', 'Gerencia Requisitor','Tipo Proyecto'])

# JOIN LEFT: Proyectos vs Master Plan
matriz_resultante_mp = pd.merge(matriz_resultante, matriz_mp_select, on='Código Proyecto', how='left')
matriz_resultante_mp.loc[matriz_resultante_mp['PM ACTUAL'].isna(), 'PM ACTUAL'] = 'La linea'
matriz_resultante_mp.loc[matriz_resultante_mp['Gerencia Sponsor Final'].isna(), 'Gerencia Sponsor Final'] = 'Otras Gerencias'
matriz_resultante_mp.loc[matriz_resultante_mp['Gerencia'].isna(), 'Gerencia'] = 'Pendiente'


#### 32. Añadir nuevas columnas: Forecast, Acumulado mes FCST y Pendiente FCST
matriz_resultante_mp = matriz_resultante_mp.drop(columns=['Key2'])

pos = 3
matriz_resultante_mp.insert(loc=pos, column='Forecast', value=0)
matriz_resultante_mp.insert(loc=pos+1, column='="FCST a " & I2', value=0)
matriz_resultante_mp.insert(loc=pos+2, column='="Pendiente de FCST a " & I2', value=0)
matriz_resultante_mp.insert(loc=pos+3, column='% cumplimiento FCST', value=0)
matriz_resultante_mp.insert(loc=pos+4, column='="% cumplimiento a " & I2', value=0)

# =SI.ERROR(AQ126/REDONDEAR(N126;2);0)

matriz_resultante_mp['="Pendiente de FCST a " & I2'] = matriz_resultante_mp.apply(lambda row: f'=K{row.name + 6} - AT{row.name + 6}', axis=1)
matriz_resultante_mp['% cumplimiento FCST'] = matriz_resultante_mp.apply(lambda row: f'=IFERROR(AT{row.name + 6} / ROUND(O{row.name + 6},2),0)', axis=1)
matriz_resultante_mp['="% cumplimiento a " & I2'] = matriz_resultante_mp.apply(lambda row: f'=IFERROR(AT{row.name + 6} / ROUND(K{row.name + 6},2),0)', axis=1)


matriz_resultante_mp['Forecast Total'] = matriz_resultante_mp['TOTAL FCST 9+3'] + matriz_resultante_mp['TOTAL CF 9+3']

matriz_resultante_mp.loc[matriz_resultante_mp['SOLPE'].isna(), 'SOLPE'] = 0
matriz_resultante_mp.loc[matriz_resultante_mp['Importe OC'].isna(), 'Importe OC'] = 0
matriz_resultante_mp.loc[matriz_resultante_mp['Forecast Total'].isna(), 'Forecast Total'] = 0


matriz_resultante_mp['Exceso/Por comprometer'] = matriz_resultante_mp['Importe OC'] - matriz_resultante_mp['Forecast Total']
matriz_resultante_mp.loc[matriz_resultante_mp['Forecast Total'] == 0, 'Exceso/Por comprometer'] = 0
matriz_resultante_mp['Ptto Disponible'] = matriz_resultante_mp['SOLPE'] - matriz_resultante_mp['Importe OC']



#### 33. Ordenar columnas de PROYECTOS
# #Obtén la lista de columnas
columnas = list(matriz_resultante_mp.columns)
# columnas
# Encuentra los índices de las columnas que deseas mover
indice_solpe = columnas.index('SOLPE') #10
indice_pm = columnas.index('PM ACTUAL')
indice_fcst = columnas.index('Forecast')
indice_oc = columnas.index('Dic 25 - OC') #3
indice_jf = columnas.index('Jefatura Final')


columna_pm = columnas.pop(indice_pm)
columna_jf = columnas.pop(indice_jf)

# Mueve 'OC' y 'AC' inmediatamente después de 'Nombre Proyecto'
columnas.insert(indice_fcst, columna_pm)
columnas.insert(indice_fcst, columna_jf)

# Reorganiza el DataFrame con las columnas movidas
matriz_resultante_mp = matriz_resultante_mp[columnas]


#### 34. Añadir columna si es CAPEX u OPEX en Proyectos
matriz_resultante_mp['Código Proyecto'] = matriz_resultante_mp['Código Proyecto'].astype(str)
matriz_resultante_mp['CAPEX/OPEX'] = matriz_resultante_mp['Código Proyecto'].apply(lambda x: 'OPEX' if 'OPEX' in x else 'CAPEX')
matriz_resultante_mp.loc[matriz_resultante_mp['Jefatura Final'].isna(), 'Jefatura Final'] = 'Otras Gerencias'
matriz_resultante_mp.loc[matriz_resultante_mp['Unidad Funcional'].isna(), 'Unidad Funcional'] = 'Otras Gerencias'
matriz_resultante_mp.loc[matriz_resultante_mp['Trimestre'].isna(), 'Trimestre'] = '-'
matriz_resultante_mp.loc[matriz_resultante_mp['Trimestre Real'].isna(), 'Trimestre Real'] = '-'
matriz_resultante_mp.loc[matriz_resultante_mp['Avance Proyecto'].isna(), 'Avance Proyecto'] = 0

#### 35. Añadir columna categoria Hardware o Servicios en Proyectos
matriz_resultante_mp['Categoría'] = ""
matriz_resultante_mp['ID Inversion'] = matriz_resultante_mp['Inversión/SubRubro'].str.split("-").str[0]

matriz_resultante_mp.loc[(matriz_resultante_mp['ID Inversion'] == "1") | (matriz_resultante_mp['ID Inversion'] == "3") | (matriz_resultante_mp['ID Inversion'] == "4"), 'Categoría'] = "Hardware"
matriz_resultante_mp.loc[(matriz_resultante_mp['ID Inversion'] == "2"), 'Categoría'] = "Servicios"

matriz_resultante_mp = matriz_resultante_mp.drop(columns=['ID Inversion'])

### Llave2
matriz_resultante_mp['Llave2'] = ""
matriz_resultante_mp[['IDLine', 'Nombre Linea2']] = matriz_resultante_mp['Inversión/SubRubro'].str.extract(r'(^[\d\-]+)(.*)')
matriz_resultante_mp['IDLine'] = matriz_resultante_mp['IDLine'].str.strip('-')
matriz_resultante_mp['Llave2'] = matriz_resultante_mp['Código Proyecto'] + matriz_resultante_mp['IDLine']

matriz_resultante_mp = matriz_resultante_mp.drop(columns=['IDLine', 'Nombre Linea2'])


# ASIGNAR PM A LINEAS ESPECÍFICAS
# CVM
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09312-4", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09312-3", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09312-2", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09312-1", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09311-1-4", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09312-12", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09312-13", 'PM ACTUAL'] = "Henrry Mijahuanca"

# COBERTURA
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-5", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-4", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-3", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-2", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-1", 'PM ACTUAL'] = "Jason Olivos"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08611-1-7", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-12", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-20", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-21", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-22", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08612-23", 'PM ACTUAL'] = "Henrry Mijahuanca"

# INDOOR PROFUNDO
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09322-7", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09322-8", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M09322-10", 'PM ACTUAL'] = "Henrry Mijahuanca"

# ROLLOUT
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08532-10", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08532-7", 'PM ACTUAL'] = "Henrry Mijahuanca"
matriz_resultante_mp.loc[matriz_resultante_mp['Llave2'] == "M08532-9", 'PM ACTUAL'] = "Henrry Mijahuanca"


sel_matriz_resultante_mp = [
    "Llave2", 
    'CAPEX/OPEX',
    'Tipo', 
    'Código Proyecto',
    'Nombre Proyecto',
    'Inversión/SubRubro',
    'Gerencia', 
    'Jefatura Final',
    'PM ACTUAL',
    'Requisitor',
    '="FCST a " & I2',
    '="Pendiente de FCST a " & I2', 
    '% cumplimiento FCST', 
    '="% cumplimiento a " & I2',
    'Forecast',
    'Estado Ptto',
    'SOLPE ORIGINAL',
    'SOLPE', 
    'Dic 25 - OC', 
    'Enero - OC', 
    'Febrero - OC', 
    'Marzo - OC', 
    'Abril - OC', 
    'Mayo - OC', 
    'Junio - OC', 
    'Julio - OC',
    'Agosto - OC',
    'Setiembre - OC',
    'Octubre - OC',
    'Noviembre - OC',
    'Diciembre - OC',
    'Importe OC',
    'Dic 25 - AC',
    'Enero - AC',
    'Febrero - AC',
    'Marzo - AC',
    'Abril - AC', 
    'Mayo - AC',
    'Junio - AC',
    'Julio - AC',
    'Agosto - AC',
    'Setiembre - AC', 
    'Octubre - AC', 
    'Noviembre - AC', 
    'Diciembre - AC', 
    'Importe AC', 
    'Dic 25 - Facturado', 
    'Enero - Facturado', 
    'Febrero - Facturado',
    'Marzo - Facturado',
    'Abril - Facturado',
    'Mayo - Facturado',
    'Junio - Facturado',
    'Julio - Facturado',
    'Agosto - Facturado',
    'Setiembre - Facturado',
    'Octubre - Facturado',
    'Noviembre - Facturado',
    'Diciembre - Facturado', 
    'Importe Facturado',
    'Dic 25 - RQ',
    'Enero - RQ',
    'Febrero - RQ',
    'Marzo - RQ', 
    'Abril - RQ', 
    'Mayo - RQ',
    'Junio - RQ',
    'Julio - RQ',
    'Agosto - RQ',
    'Setiembre - RQ',
    'Octubre - RQ',
    'Noviembre - RQ',
    'Diciembre - RQ',
    'Importe RQ',
    "ENERO PLAN",
    "FEBRERO PLAN",
    "MARZO PLAN",
    "ABRIL PLAN",
    "MAYO PLAN",
    "JUNIO PLAN",
    "JULIO PLAN",
    "AGOSTO PLAN",
    "SETIEMBRE PLAN",
    "OCTUBRE PLAN",
    "NOVIEMBRE PLAN",
    "DICIEMBRE PLAN",
    "TOTAL PLAN",
    "ENERO CF PLAN",
    "FEBRERO CF PLAN",
    "MARZO CF PLAN",
    "ABRIL CF PLAN",
    "TOTAL CF PLAN",
    "ENERO FCST 1+11",
    "FEBRERO FCST 1+11",
    "MARZO FCST 1+11",
    "ABRIL FCST 1+11",
    "MAYO FCST 1+11",
    "JUNIO FCST 1+11",
    "JULIO FCST 1+11",
    "AGOSTO FCST 1+11",
    "SETIEMBRE FCST 1+11",
    "OCTUBRE FCST 1+11",
    "NOVIEMBRE FCST 1+11",
    "DICIEMBRE FCST 1+11",
    "TOTAL FCST 1+11",
    "ENERO CF 1+11",
    "FEBRERO CF 1+11",
    "MARZO CF 1+11",
    "ABRIL CF 1+11",
    "TOTAL CF 1+11",
    "ENERO FCST 2+10",
    "FEBRERO FCST 2+10",
    "MARZO FCST 2+10",
    "ABRIL FCST 2+10",
    "MAYO FCST 2+10",
    "JUNIO FCST 2+10",
    "JULIO FCST 2+10",
    "AGOSTO FCST 2+10",
    "SETIEMBRE FCST 2+10",
    "OCTUBRE FCST 2+10",
    "NOVIEMBRE FCST 2+10",
    "DICIEMBRE FCST 2+10",
    "TOTAL FCST 2+10",
    "ENERO CF 2+10",
    "FEBRERO CF 2+10",
    "MARZO CF 2+10",
    "ABRIL CF 2+10",
    "TOTAL CF 2+10",
    "ENERO FCST 3+9",
    "FEBRERO FCST 3+9",
    "MARZO FCST 3+9",
    "ABRIL FCST 3+9",
    "MAYO FCST 3+9",
    "JUNIO FCST 3+9",
    "JULIO FCST 3+9",
    "AGOSTO FCST 3+9",
    "SETIEMBRE FCST 3+9",
    "OCTUBRE FCST 3+9",
    "NOVIEMBRE FCST 3+9",
    "DICIEMBRE FCST 3+9",
    "TOTAL FCST 3+9",
    "ENERO CF 3+9",
    "FEBRERO CF 3+9",
    "MARZO CF 3+9",
    "ABRIL CF 3+9",
    "TOTAL CF 3+9",
    "ENERO FCST 4+8",
    "FEBRERO FCST 4+8",
    "MARZO FCST 4+8",
    "ABRIL FCST 4+8",
    "MAYO FCST 4+8",
    "JUNIO FCST 4+8",
    "JULIO FCST 4+8",
    "AGOSTO FCST 4+8",
    "SETIEMBRE FCST 4+8",
    "OCTUBRE FCST 4+8",
    "NOVIEMBRE FCST 4+8",
    "DICIEMBRE FCST 4+8",
    "TOTAL FCST 4+8",
    "ENERO CF 4+8",
    "FEBRERO CF 4+8",
    "MARZO CF 4+8",
    "ABRIL CF 4+8",
    "TOTAL CF 4+8",
    "ENERO FCST 5+7",
    "FEBRERO FCST 5+7",
    "MARZO FCST 5+7",
    "ABRIL FCST 5+7",
    "MAYO FCST 5+7",
    "JUNIO FCST 5+7",
    "JULIO FCST 5+7",
    "AGOSTO FCST 5+7",
    "SETIEMBRE FCST 5+7",
    "OCTUBRE FCST 5+7",
    "NOVIEMBRE FCST 5+7",
    "DICIEMBRE FCST 5+7",
    "TOTAL FCST 5+7",
    "ENERO CF 5+7",
    "FEBRERO CF 5+7",
    "MARZO CF 5+7",
    "ABRIL CF 5+7",
    "TOTAL CF 5+7",
    "ENERO FCST 6+6",
    "FEBRERO FCST 6+6",
    "MARZO FCST 6+6",
    "ABRIL FCST 6+6",
    "MAYO FCST 6+6",
    "JUNIO FCST 6+6",
    "JULIO FCST 6+6",
    "AGOSTO FCST 6+6",
    "SETIEMBRE FCST 6+6",
    "OCTUBRE FCST 6+6",
    "NOVIEMBRE FCST 6+6",
    "DICIEMBRE FCST 6+6",
    "TOTAL FCST 6+6",
    "ENERO CF 6+6",
    "FEBRERO CF 6+6",
    "MARZO CF 6+6",
    "ABRIL CF 6+6",
    "TOTAL CF 6+6",
    "ENERO FCST 7+5",
    "FEBRERO FCST 7+5",
    "MARZO FCST 7+5",
    "ABRIL FCST 7+5",
    "MAYO FCST 7+5",
    "JUNIO FCST 7+5",
    "JULIO FCST 7+5",
    "AGOSTO FCST 7+5",
    "SETIEMBRE FCST 7+5",
    "OCTUBRE FCST 7+5",
    "NOVIEMBRE FCST 7+5",
    "DICIEMBRE FCST 7+5",
    "TOTAL FCST 7+5",
    "ENERO CF 7+5",
    "FEBRERO CF 7+5",
    "MARZO CF 7+5",
    "ABRIL CF 7+5",
    "TOTAL CF 7+5",
    "ENERO FCST 8+4",
    "FEBRERO FCST 8+4",
    "MARZO FCST 8+4",
    "ABRIL FCST 8+4",
    "MAYO FCST 8+4",
    "JUNIO FCST 8+4",
    "JULIO FCST 8+4",
    "AGOSTO FCST 8+4",
    "SETIEMBRE FCST 8+4",
    "OCTUBRE FCST 8+4",
    "NOVIEMBRE FCST 8+4",
    "DICIEMBRE FCST 8+4",
    "TOTAL FCST 8+4",
    "ENERO CF 8+4",
    "FEBRERO CF 8+4",
    "MARZO CF 8+4",
    "ABRIL CF 8+4",
    "TOTAL CF 8+4",
    "ENERO FCST 9+3",
    "FEBRERO FCST 9+3",
    "MARZO FCST 9+3",
    "ABRIL FCST 9+3",
    "MAYO FCST 9+3",
    "JUNIO FCST 9+3",
    "JULIO FCST 9+3",
    "AGOSTO FCST 9+3",
    "SETIEMBRE FCST 9+3",
    "OCTUBRE FCST 9+3",
    "NOVIEMBRE FCST 9+3",
    "DICIEMBRE FCST 9+3",
    "TOTAL FCST 9+3",
    "ENERO CF 9+3",
    "FEBRERO CF 9+3",
    "MARZO CF 9+3",
    "ABRIL CF 9+3",
    "TOTAL CF 9+3",
    "ENERO FCST 10+2",
    "FEBRERO FCST 10+2",
    "MARZO FCST 10+2",
    "ABRIL FCST 10+2",
    "MAYO FCST 10+2",
    "JUNIO FCST 10+2",
    "JULIO FCST 10+2",
    "AGOSTO FCST 10+2",
    "SETIEMBRE FCST 10+2",
    "OCTUBRE FCST 10+2",
    "NOVIEMBRE FCST 10+2",
    "DICIEMBRE FCST 10+2",
    "TOTAL FCST 10+2",
    "ENERO CF 10+2",
    "FEBRERO CF 10+2",
    "MARZO CF 10+2",
    "ABRIL CF 10+2",
    "TOTAL CF 10+2",
    "ENERO FCST 11+1",
    "FEBRERO FCST 11+1",
    "MARZO FCST 11+1",
    "ABRIL FCST 11+1",
    "MAYO FCST 11+1",
    "JUNIO FCST 11+1",
    "JULIO FCST 11+1",
    "AGOSTO FCST 11+1",
    "SETIEMBRE FCST 11+1",
    "OCTUBRE FCST 11+1",
    "NOVIEMBRE FCST 11+1",
    "DICIEMBRE FCST 11+1",
    "TOTAL FCST 11+1",
    "ENERO CF 11+1",
    "FEBRERO CF 11+1",
    "MARZO CF 11+1",
    "ABRIL CF 11+1",
    "TOTAL CF 11+1",
    "Provisión Real",
    "Declaración No Uso",
    "Categoría",
    "Exceso/Por comprometer",
    "Ptto Disponible",
    "Gerencia Sponsor Final",
    "Unidad Funcional",
    "Trimestre",
    "Trimestre Real",
    "Avance Proyecto"
]

matriz_resultante_mp = matriz_resultante_mp[sel_matriz_resultante_mp]


# # ====================================================================== #
# # UPLOAD DATA TO DB
# # ====================================================================== #
df_proyectos = matriz_resultante_mp
df_individual_proyectos = matriz_final_individual_selected
df_agrupado_proyectos = matriz_final_filtrado_selected_group_j

# print(df_proyectos)
# print(df_individual_proyectos)
# print(df_agrupado_proyectos)

client = MongoClient("mongodb://gcirAdmin:Entel1234_@10.30.17.57:27017/?directConnection=true&serverSelectionTimeoutMS=5000")
db = client["gcir"]

def _xl_col_to_idx(col_letters: str) -> int:
    col_letters = str(col_letters).strip().upper()
    n = 0
    for c in col_letters:
        n = n*26 + (ord(c)-64)
    return n-1

def _slice_by_letters(df, start_letter, end_letter):
    s, e = _xl_col_to_idx(start_letter), _xl_col_to_idx(end_letter)
    return df.iloc[:, s:e+1]

def _safe_total_series(df, col_letter):
    idx = _xl_col_to_idx(col_letter)
    return df.iloc[:, idx] if idx < df.shape[1] else [0.0]*len(df)

def _to_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0

def sanitize_key(k: str) -> str:
    """
    Mongo no permite '.' ni claves que empiecen con '$'.
    Además normalizamos espacios a '_'.
    """
    ks = str(k).strip()
    ks = ks.replace('.', '_').replace(' ', '_')
    if ks.startswith('$'):
        ks = '_' + ks[1:]
    return ks

def cols_from_letters(df, start, end):
    s, e = _xl_col_to_idx(start), _xl_col_to_idx(end)
    return list(df.columns[s:e+1]) if s < df.shape[1] else []


def fix_date_columns_to_iso(df: pd.DataFrame, date_cols):
    df = df.copy()
    for col in date_cols:
        if col in df.columns:
            # s = pd.to_datetime(df[col], errors="coerce", utc=False, infer_datetime_format=True)
            s = pd.to_datetime(df[col], errors="coerce", utc=False)
            df[col] = s.dt.strftime("%Y-%m-%d").where(s.notna(), None)  # NaT -> None
    return df

# aplica a CR_Individual y RQ_Agrupado
DATE_COLS = [
    "Fecha Emisión RQ", "Fecha Aprobación RQ",
    "Fecha Emisión OC", "Fecha Aprobación OC",
    "Fecha Recepción", "Fecha Inicio de Proyecto",
    "Fecha de Fin de Proyecto"
    # añade otras si existen…
]


def _build_proyectos_docs(dfp: pd.DataFrame):
    # --- Identificadores (seguimos detectando code/nombre por si quieres indexarlos) ---
    id_cols_candidates = [c for c in dfp.columns
                          if re.search(r"(c[oó]digo|code|proyecto|project|nombre|name)", str(c), re.I)]
    id_cols = id_cols_candidates[:5] if id_cols_candidates else list(dfp.columns[:5])

    # --- Rangos que definiste (AJUSTADOS a tus letras) ---
    # Bloques base de meses y sus totales
    oc_m   = _slice_by_letters(dfp, "S",  "AE");  oc_total_col  = "AF"
    ac_m   = _slice_by_letters(dfp, "AG", "AS");  ac_total_col  = "AT"
    fac_m  = _slice_by_letters(dfp, "AU", "BG");  fac_total_col = "BH"
    rq_m   = _slice_by_letters(dfp, "BI", "BU");  rq_total_col  = "BV"

    oc_h, ac_h, fac_h, rq_h = list(oc_m.columns), list(ac_m.columns), list(fac_m.columns), list(rq_m.columns)

    # Totales como series
    oc_total_series  = _safe_total_series(dfp, oc_total_col)
    ac_total_series  = _safe_total_series(dfp, ac_total_col)
    fac_total_series = _safe_total_series(dfp, fac_total_col)
    rq_total_series  = _safe_total_series(dfp, rq_total_col)

    # FCST/CF dinámicos (tus rangos)
    blocks = {
        "Plan": {"fcst": ("BW","CH","CI"), "cf": ("CJ","CM","CN")},
        "1+11": {"fcst": ("CO","CZ","DA"), "cf": ("DB","DE","DF")},
        "2+10": {"fcst": ("DG","DR","DS"), "cf": ("DT","DW","DX")},
        "3+9":  {"fcst": ("DY","EJ","EK"), "cf": ("EL","EO","EP")},
        "4+8":  {"fcst": ("EQ","FB","FC"), "cf": ("FD","FG","FH")},
        "5+7":  {"fcst": ("FI","FT","FU"), "cf": ("FV","FY","FZ")},
        "6+6":  {"fcst": ("GA","GL","GM"), "cf": ("GN","GQ","GR")},
        "7+5":  {"fcst": ("GS","HD","HE"), "cf": ("HF","HI","HJ")},
        "8+4":  {"fcst": ("HK","HV","HW"), "cf": ("HX","IA","IB")},
        "9+3":  {"fcst": ("IC","IN","IO"), "cf": ("IP","IS","IT")},
        "10+2": {"fcst": ("IU","JF","JG"), "cf": ("JH","JK","JL")},
        "11+1": {"fcst": ("JM","JX","JY"), "cf": ("JZ","KC","KD")}
    }

    # --- Construimos el SET de columnas a excluir del "copiado masivo" ---
    exclude_cols = set()
    # meses base
    exclude_cols.update(oc_h + ac_h + fac_h + rq_h)
    exclude_cols.update([oc_total_col, ac_total_col, fac_total_col, rq_total_col])
    # meses/totales de cada FCST/CF
    for spec in blocks.values():
        fcst_start, fcst_end, fcst_total_col = spec["fcst"]
        cf_start,   cf_end,   cf_total_col   = spec["cf"]
        exclude_cols.update(cols_from_letters(dfp, fcst_start, fcst_end))
        exclude_cols.update(cols_from_letters(dfp, cf_start,   cf_end))
        exclude_cols.update([fcst_total_col, cf_total_col])

    # --- Helper de conversión numérica segura para months ---
    def num_or_zero(v):
        if pd.isna(v):
            return 0.0
        try:
            return float(v)
        except Exception:
            return 0.0

    # --- Construcción de documentos fila a fila ---
    docs = []
    for i, row in dfp.iterrows():
        # 1) Copiar TODAS las columnas "meta" (no excluidas) con saneo de claves
        base_fields = {}
        for col in dfp.columns:
            if col in exclude_cols:
                continue
            val = row.get(col, None)
            if pd.isna(val):
                val = ""  # para campos no numéricos guardamos vacío
            base_fields[sanitize_key(col)] = val

        # 2) Opcional: además de meta, aseguramos id_cols por si quieres indexarlos fácil
        for c in id_cols:
            v = row.get(c, None)
            if pd.notna(v) and str(v).strip() != "":
                base_fields[sanitize_key(c)] = v

        # 3) amounts
        doc = {
            **base_fields,
            "amounts": {
                "oc": {
                    "total": num_or_zero(oc_total_series[i]),
                    "months": [{"header": h, "value": num_or_zero(row.get(h, 0))} for h in oc_h],
                },
                "ac": {
                    "total": num_or_zero(ac_total_series[i]),
                    "months": [{"header": h, "value": num_or_zero(row.get(h, 0))} for h in ac_h],
                },
                "facturado": {
                    "total": num_or_zero(fac_total_series[i]),
                    "months": [{"header": h, "value": num_or_zero(row.get(h, 0))} for h in fac_h],
                },
                "rq": {
                    "total": num_or_zero(rq_total_series[i]),
                    "months": [{"header": h, "value": num_or_zero(row.get(h, 0))} for h in rq_h],
                },
            },
            "forecasts": {}
        }

        # 4) forecasts (fcst + cf)
        for k, spec in blocks.items():
            fcst_start, fcst_end, fcst_total_col = spec["fcst"]
            cf_start,   cf_end,   cf_total_col   = spec["cf"]

            # headers de meses para cada bloque
            fcst_hdrs = cols_from_letters(dfp, fcst_start, fcst_end)
            cf_hdrs   = cols_from_letters(dfp, cf_start,   cf_end)

            # totales
            def total_from_letter(letter):
                idx = _xl_col_to_idx(letter)
                return row.iat[idx] if idx < dfp.shape[1] else 0.0

            doc["forecasts"][k] = {
                "fcst": {
                    "total": num_or_zero(total_from_letter(fcst_total_col)),
                    "months": [{"header": h, "value": num_or_zero(row.get(h, 0))} for h in fcst_hdrs],
                },
                "cf": {
                    "total": num_or_zero(total_from_letter(cf_total_col)),
                    "months": [{"header": h, "value": num_or_zero(row.get(h, 0))} for h in cf_hdrs],
                },
            }

        docs.append(doc)

    return docs





def insert_dataframes_to_mongo(df_proyectos, df_individual_proyectos, df_agrupado_proyectos,
                               mongo_uri="mongodb://gcirAdmin:Entel1234_@10.30.17.57:27017/?directConnection=true&serverSelectionTimeoutMS=5000",
                               db_name="gcir",
                               drop_collections=True):
    """
    Inserta directamente tus DataFrames ya calculados a MongoDB.
    """
    client = MongoClient(mongo_uri)
    db = client[db_name]
    c_proy = db["projects"]
    c_cr   = db["cr_individual"]
    c_rq   = db["rq_agrupado"]

    if drop_collections:
        c_proy.delete_many({})
        c_cr.delete_many({})
        c_rq.delete_many({})

    # Proyectos (con months + FCST/CF)
    proy_docs = _build_proyectos_docs(df_proyectos)
    
    # print(proy_docs)
    if proy_docs: c_proy.insert_many(proy_docs)

    # ---- CR_Individual ----
    df_cr_fixed = fix_date_columns_to_iso(df_individual_proyectos, DATE_COLS)
    cr_docs = df_cr_fixed.where(pd.notna(df_cr_fixed), None).to_dict(orient="records")
    c_cr.insert_many(cr_docs)
    
    # ---- RQ_Agrupado ----
    df_rq_fixed = fix_date_columns_to_iso(df_agrupado_proyectos, DATE_COLS)
    rq_docs = df_rq_fixed.where(pd.notna(df_rq_fixed), None).to_dict(orient="records")
    c_rq.insert_many(rq_docs)

    # Índices útiles
    c_proy.create_index([("proyecto",1), ("Proyecto",1), ("project_code",1)], name="project_fields")
    # for t in ["2+10","3+9","6+6","9+3"]:
    for t in ["1+11","2+10","3+9","4+8","5+7","6+6","7+5","8+4","9+3","10+2","11+1"]:
        c_proy.create_index([(f"forecasts.{t}.fcst.months.header",1)], name=f"hdr_{t.replace('+','_')}", sparse=True)
    c_cr.create_index([("RQ",1), ("Project Code",1), ("Project Name",1)], name="cr_keys")
    c_rq.create_index([("Project Code",1), ("Project Name",1)], name="rq_keys")


insert_dataframes_to_mongo(
    df_proyectos,
    df_individual_proyectos,
    df_agrupado_proyectos,
    mongo_uri="mongodb://gcirAdmin:Entel1234_@10.30.17.57:27017/?directConnection=true&serverSelectionTimeoutMS=5000",
    db_name="gcir",
    drop_collections=True  # pon False si no quieres borrar antes
)


