import requests
from datetime import datetime
import csv
import os
import time
import pandas as pd
import random

# ==========================================
# CONFIG
# ==========================================

API_KEY    = "RGAPI-ea4963bf-8bf4-41c3-84c7-c9adc33274b9"   # <-- reemplaza con tu key vigente
REGION     = "americas"
headers    = {"X-Riot-Token": API_KEY}

INPUT_CSV  = "zrecoleccion/usuarios_separados.csv"    # tu CSV con columna Usuario_Completo
OUTPUT_CSV = "data_collector/dataset_POSTEST.csv"
# N_PARTIDAS = 60
N_PARTIDAS = random.randint(54, 60)

# ==========================================
# RATE LIMIT
# Riot: 100 requests / 120 s
# Margen seguro: 90 por ventana
# ==========================================

REQUEST_COUNT = 0
WINDOW_START  = time.time()

def controlar_rate_limit():
    global REQUEST_COUNT, WINDOW_START
    REQUEST_COUNT += 1
    elapsed = time.time() - WINDOW_START
    if REQUEST_COUNT >= 90:
        if elapsed < 120:
            wait = 120 - elapsed + 2
            print(f"\n⏳ Rate limit — esperando {round(wait, 1)}s ...\n")
            time.sleep(wait)
        REQUEST_COUNT = 0
        WINDOW_START  = time.time()

# ==========================================
# LEER USUARIOS DESDE CSV
# Columna: Usuario_Completo → "Nombre#Tag"
# ==========================================

def load_users_from_csv():
    df = pd.read_csv(INPUT_CSV)

    # Detecta automáticamente el nombre de la columna
    col = df.columns[0]

    users   = []
    errores = []

    for i, row in df.iterrows():
        raw = str(row[col]).strip()
        if "#" not in raw:
            errores.append(f"Fila {i+2}: '{raw}' — sin '#', se omite")
            continue
        # Separa solo por el ÚLTIMO '#' para nombres con # en el medio
        partes = raw.rsplit("#", 1)
        name   = partes[0].strip()
        tag    = partes[1].strip()
        if name and tag:
            users.append((name, tag))
        else:
            errores.append(f"Fila {i+2}: '{raw}' — nombre o tag vacío")

    if errores:
        print("⚠ Filas con problemas al leer CSV:")
        for e in errores:
            print(f"  {e}")

    return users

# ==========================================
# USUARIOS YA PROCESADOS
# Permite reanudar si el proceso se interrumpe
# ==========================================

def load_processed_users():
    if not os.path.isfile(OUTPUT_CSV):
        return set()
    try:
        df = pd.read_csv(OUTPUT_CSV)
        return set(
            f"{str(r['Usuario']).strip()}#{str(r['Tag']).strip()}"
            for _, r in df.iterrows()
        )
    except Exception:
        return set()

# ==========================================
# API CALLS
# ==========================================

def get_puuid(name, tag):
    controlar_rate_limit()
    url = (
        f"https://{REGION}.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
    )
    r = requests.get(url, headers=headers)
    if r.status_code == 429:
        print("⏳ 429 — esperando 30s ...")
        time.sleep(30)
        return get_puuid(name, tag)
    if r.status_code != 200:
        print(f"❌ PUUID {name}#{tag} — HTTP {r.status_code}")
        return None
    return r.json().get("puuid")

def get_match_ids(puuid, count=N_PARTIDAS):
    controlar_rate_limit()
    url = (
        f"https://{REGION}.api.riotgames.com"
        f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
    )
    r = requests.get(url, headers=headers, params={"start": 0, "count": count})
    if r.status_code == 429:
        print("⏳ 429 — esperando 30s ...")
        time.sleep(30)
        return get_match_ids(puuid, count)
    if r.status_code != 200:
        print(f"❌ matchlist — HTTP {r.status_code}")
        return []
    return r.json()

def get_match(match_id):
    controlar_rate_limit()
    url = (
        f"https://{REGION}.api.riotgames.com"
        f"/lol/match/v5/matches/{match_id}"
    )
    r = requests.get(url, headers=headers)
    if r.status_code == 429:
        print("⏳ 429 — esperando 30s ...")
        time.sleep(30)
        return get_match(match_id)
    if r.status_code != 200:
        print(f"⚠ match {match_id} — HTTP {r.status_code}")
        return None
    return r.json()

# ==========================================
# DCJ = max(ck)
# Racha máxima de días consecutivos activos
# Viljanen et al. (2018, IEEE Trans. Games)
# ==========================================

def calcular_dcj(dates):
    sorted_days = sorted(set(d.date() for d in dates))
    if not sorted_days:
        return 0
    racha = max_racha = 1
    for i in range(1, len(sorted_days)):
        if (sorted_days[i] - sorted_days[i - 1]).days == 1:
            racha += 1
        else:
            max_racha = max(max_racha, racha)
            racha = 1
    return max(max_racha, racha)

# ==========================================
# CLASIFICACIÓN DE RIESGO
# 3 indicadores × 2 pts máx = 6 pts totales
# Equiponderación: Gage et al. (2001, JAMA)
#
# Umbrales HPD:
#   >5 h/día → Alto  (Pontes et al. 2021: ~40h/sem OMS)
#   >3 h/día → Medio (Brunborg et al. 2024: ~33h/sem)
#
# Umbrales NPPD (coherentes con HPD para LoL):
#   >7 partidas/día → Alto  (7 × ~35min ≈ 4.1h)
#   >4 partidas/día → Medio (4 × ~35min ≈ 2.3h)
#
# Umbrales DCJ (ICD-11 WHO 2022):
#   >5 días → "continuo"            → Alto
#   >3 días → "episódico/recurrente"→ Medio
# ==========================================

def calcular_riesgo(hpd, nppd, dcj):
    score = 0

    if hpd > 5:    score += 2
    elif hpd > 3:  score += 1

    if nppd > 7:   score += 2
    elif nppd > 4: score += 1

    if dcj > 5:    score += 2
    elif dcj > 3:  score += 1

    if score >= 5:   return "Alto"
    elif score >= 3: return "Medio"
    return "Bajo"

# ==========================================
# GUARDAR FILA
# ==========================================

FIELDNAMES = [
    "Usuario", "Tag",
    "THT",    # Tiempo Total Horas jugadas (Seif El-Nasr et al. 2021)
    "ND",     # Número de Días con actividad (Seif El-Nasr et al. 2021)
    "TPP",    # Total Partidas del Período
    "HPD",    # Horas Promedio por Día = THT/ND
    "NPPD",   # Partidas Promedio por Día = TPP/ND
    "DCJ",    # Días Consecutivos de Juego = max(ck)
    "Riesgo"
]

def save_row(row):
    file_exists = os.path.isfile(OUTPUT_CSV)
    with open(OUTPUT_CSV, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

# ==========================================
# PROCESAR UN USUARIO
# ==========================================

def procesar_usuario(name, tag):
    # 1 — PUUID
    puuid = get_puuid(name, tag)
    if not puuid:
        return None

    # 2 — Match IDs
    n_partidas = random.randint(54, 60)
    match_ids = get_match_ids(puuid, count=n_partidas)
    if not match_ids:
        print("  ⚠ Sin partidas.")
        return None

    durations = []
    dates     = []

    # 3 — Detalle de cada partida
    for i, match_id in enumerate(match_ids, start=1):
        print(f"  ➡ Partida {i}/{len(match_ids)}", end="\r")
        match = get_match(match_id)
        time.sleep(0.08)
        if not match:
            continue
        info = match.get("info", {})

        # gameDuration en SEGUNDOS → horas
        dur_h = info.get("gameDuration", 0) / 3600
        # gameCreation en MILISEGUNDOS → datetime
        fecha = datetime.fromtimestamp(info.get("gameCreation", 0) / 1000)

        durations.append(dur_h)
        dates.append(fecha)

    print()

    if not durations:
        return None

    # ---- Variables base ----------------------------------------
    THT = round(sum(durations), 2)           # horas totales
    ND  = len(set(d.date() for d in dates))  # días únicos con actividad
    TPP = len(durations)                     # total partidas válidas

    # ---- Indicadores (Tabla 1 tesis) ---------------------------
    HPD  = round(THT / ND,  2) if ND > 0 else 0   # THT/ND
    NPPD = round(TPP / ND,  2) if ND > 0 else 0   # TPP/ND
    DCJ  = calcular_dcj(dates)                     # max(ck)

    # ---- Etiqueta (weak supervision) ---------------------------
    Riesgo = calcular_riesgo(HPD, NPPD, DCJ)

    row = {
        "Usuario": name, "Tag": tag,
        "THT": THT, "ND": ND, "TPP": TPP,
        "HPD": HPD, "NPPD": NPPD, "DCJ": DCJ,
        "Riesgo": Riesgo
    }
    save_row(row)
    return row

# ==========================================
# MAIN
# ==========================================

def main():
    # Cargar todos los usuarios del CSV
    all_users = load_users_from_csv()
    processed = load_processed_users()

    pendientes = [
        (n, t) for n, t in all_users
        if f"{n}#{t}" not in processed
    ]

    total = len(all_users)
    print(f"\n{'='*48}")
    print(f"  Archivo entrada  : {INPUT_CSV}")
    print(f"  Total usuarios   : {total}")
    print(f"  Ya procesados    : {total - len(pendientes)}")
    print(f"  Por procesar     : {len(pendientes)}")
    print(f"  Partidas/usuario : {N_PARTIDAS}")

    # Estimación tiempo
    req_total = (57 + 2) * len(pendientes)
    min_est   = round(
        (req_total / 90) * 2 + (N_PARTIDAS * len(pendientes) * 0.08) / 60,
        1
    )
    h = int(min_est // 60)
    m = int(min_est % 60)
    print(f"  Tiempo estimado  : ~{h}h {m}m")
    print(f"{'='*48}\n")

    if not pendientes:
        print("✅ Todos los usuarios ya fueron procesados.")
        return

    exitos   = 0
    errores  = 0
    t_inicio = time.time()

    for idx, (name, tag) in enumerate(pendientes, start=1):
        print(f"\n[{idx}/{len(pendientes)}] {name}#{tag}")
        t0  = time.time()
        row = procesar_usuario(name, tag)

        if row:
            exitos += 1
            print(
                f"  ✅ THT={row['THT']}h  ND={row['ND']}d  "
                f"HPD={row['HPD']}h/d  NPPD={row['NPPD']}  "
                f"DCJ={row['DCJ']}d  → {row['Riesgo']}  "
                f"({round(time.time()-t0, 1)}s)"
            )
        else:
            errores += 1
            print("  ❌ No procesado — se continúa con el siguiente")

        # Progreso cada 20 usuarios
        if idx % 20 == 0:
            transcurrido = (time.time() - t_inicio) / 60
            velocidad    = transcurrido / idx          # min/usuario
            restante     = velocidad * (len(pendientes) - idx)
            print(
                f"\n  ── Progreso: {idx}/{len(pendientes)} │ "
                f"Éxitos: {exitos} │ Errores: {errores} │ "
                f"Restante: ~{int(restante)} min ──\n"
            )

    # ---- Resumen final -----------------------------------------
    tiempo_total = round((time.time() - t_inicio) / 60, 1)

    print(f"\n{'='*48}")
    print(f"  PROCESO TERMINADO")
    print(f"  Éxitos   : {exitos}")
    print(f"  Errores  : {errores}")
    print(f"  Tiempo   : {tiempo_total} min")
    print(f"{'='*48}")

    if os.path.isfile(OUTPUT_CSV):
        df = pd.read_csv(OUTPUT_CSV)
        n  = len(df)
        print(f"\n📊 DISTRIBUCIÓN DE RIESGO ({n} usuarios):")
        for nivel, cant in df["Riesgo"].value_counts().items():
            pct = round(cant / n * 100, 1)
            bar = "█" * int(pct / 4)
            print(f"  {nivel:<6}: {cant:>3} ({pct:>5}%)  {bar}")

        print(f"\n📈 ESTADÍSTICAS DESCRIPTIVAS:")
        print(df[["HPD", "NPPD", "DCJ"]].describe().round(2).to_string())
        print(f"\n💾 Guardado en: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()