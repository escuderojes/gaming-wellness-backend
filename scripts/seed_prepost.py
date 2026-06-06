"""Siembra recolecciones en Firestore para cada participante usando
el dataset dataset_prepost.csv.

Estructura por usuario (2 semanas: 13 may → 26 may):
  - 13 may 2026  → colecta PRE  (variables reales del CSV)
  - 17 may 2026  → interpolada al 25%
  - 20 may 2026  → interpolada al 50%
  - 23 may 2026  → interpolada al 75%
  - 26 may 2026  → colecta POST (variables reales del CSV)

Cada entrada tiene hora/minuto/segundo aleatorio realista (tarde-noche).
TP (total de partidas) es el real de la ventana de 14 días. demo=False.

Al finalizar la siembra, si hay RIOT_API_KEY configurada, se obtiene
el perfil real de cada usuario (icono, nivel) desde la Riot API y se
actualiza el documento en Firestore sin tocar las recolecciones.

Uso:
    cd D:\\Backend
    python scripts/seed_prepost.py

    # Solo auditar (no escribe nada):
    python scripts/seed_prepost.py --dry-run

    # Solo procesar usuarios específicos (por Riot name):
    python scripts/seed_prepost.py --solo Aiso Tyson

    # Saltar la fase de perfil Riot aunque haya API key:
    python scripts/seed_prepost.py --sin-perfil
"""
import os
import sys
import csv
import time
import random
import argparse
from pathlib import Path
from datetime import datetime, timezone, date, timedelta

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

# Carga el .env antes de leer RIOT_API_KEY (igual que run.py).
from dotenv import load_dotenv
load_dotenv(BASE / ".env")

import firebase_admin
from firebase_admin import credentials, auth, firestore

KEY_PATH     = BASE / "firebase-key.json"
CSV_PATH     = BASE / "dataset_prepost.csv"
RIOT_API_KEY = os.environ.get("RIOT_API_KEY", "")

# ── Fechas del estudio (2 semanas) ────────────────────────────────────────────
FECHA_PRE  = date(2026, 5, 13)
FECHA_POST = date(2026, 5, 26)

INTERMEDIOS = [
    (date(2026, 5, 17), 0.25),
    (date(2026, 5, 20), 0.50),
    (date(2026, 5, 23), 0.75),
]

NOCHE_INICIO = 22
NOCHE_FIN    = 6

# Horas realistas de juego: distribución ponderada (tarde-noche más probable)
HORAS_JUEGO = (
    [10, 11, 12] * 1 +          # mañana (poco probable)
    [13, 14, 15, 16] * 2 +      # tarde
    [17, 18, 19, 20, 21] * 4 +  # tarde-noche (más probable)
    [22, 23, 0, 1] * 2          # noche
)


# ── Helpers de timestamp ──────────────────────────────────────────────────────

def _timestamp_aleatorio(ref_date: date, seed: int) -> datetime:
    """Genera un datetime en ref_date con hora/min/seg aleatorio realista."""
    rng = random.Random(seed)
    hora    = rng.choice(HORAS_JUEGO)
    minuto  = rng.randint(0, 59)
    segundo = rng.randint(0, 59)
    # Si la hora es 0 o 1 pertenece al día siguiente; ajustamos la fecha.
    dia = ref_date
    if hora < 6:
        dia = ref_date + timedelta(days=1)
    return datetime(dia.year, dia.month, dia.day,
                    hora, minuto, segundo, tzinfo=timezone.utc)


# ── Helpers de distribución ───────────────────────────────────────────────────

def _es_noche(h):
    return h >= NOCHE_INICIO or h < NOCHE_FIN


def _extras_para_fecha(hpd, tht, nd, ref_date: date, perfil: str, seed: int) -> dict:
    """Genera extras simulados con fecha de referencia histórica y seed fijo.

    Tanto porHora como porDiaSemana usan tts_semana como base común para que
    ambas gráficas del dashboard sean coherentes entre sí.
    """
    rng = random.Random(seed)

    monday             = ref_date - timedelta(days=ref_date.weekday())
    dias_transcurridos = ref_date.weekday() + 1          # 1 (lun) … 7 (dom)
    dias_activos_semana = rng.randint(1, min(int(nd), dias_transcurridos))
    hpd_semana  = round(hpd, 2)
    # tts_semana = horas reales de la semana: BASE ÚNICA para ambas gráficas.
    tts_semana  = round(hpd_semana * dias_activos_semana, 2)
    dcj_semana  = min(dias_activos_semana, dias_transcurridos)

    # porDiaSemana: distribuye tts_semana entre los 7 días con pesos aleatorios.
    pesos   = [rng.uniform(0.4, 1.6) for _ in range(7)]
    s_pesos = sum(pesos) or 1
    por_dia = [round(tts_semana * w / s_pesos, 2) for w in pesos]

    # porHora: distribuye tts_semana con forma horaria realista.
    forma = [3, 2, 1, 1, 1, 1, 2, 4, 6, 8, 9, 10, 11, 11,
             12, 13, 15, 17, 19, 21, 22, 20, 12, 6]
    if perfil == "alto":
        for h in (22, 23, 0, 1, 2, 3):
            forma[h] *= 3
    elif perfil == "medio":
        for h in (22, 23, 0, 1):
            forma[h] = int(forma[h] * 1.8)
    s_forma  = sum(forma) or 1
    por_hora = [round(tts_semana * f / s_forma, 2) for f in forma]

    noche_horas = sum(por_hora[h] for h in range(24) if _es_noche(h))

    return {
        # pjnMin: minutos nocturnos promedio por día activo de la semana.
        "pjnMin":            round(noche_horas * 60 / max(dias_activos_semana, 1), 1),
        "nochesActivas":     rng.randint(0, min(dias_activos_semana, 7)),
        "porDiaSemana":      por_dia,
        "porHora":           por_hora,
        "desde":             monday.isoformat(),
        "hasta":             ref_date.isoformat(),
        "diasActivosSemana": dias_activos_semana,
        "hpdSemana":         hpd_semana,
        "ttsSemana":         tts_semana,
        "dcjSemana":         dcj_semana,
    }


def _interpolar(pre: dict, post: dict, t: float) -> dict:
    """Interpola linealmente entre pre y post (t=0 → pre, t=1 → post)."""
    resultado = {}
    for k in pre:
        v = float(pre[k]) + (float(post[k]) - float(pre[k])) * t
        resultado[k] = int(round(v)) if k in ("ND", "TP", "DCJ") else round(v, 2)
    return resultado


def _perfil_desde_riesgo(riesgo) -> str:
    """Perfil de ícono demo según el riesgo binario del ICOGS-A.
    Acepta 1/'1'/'Riesgo' como 'alto' y el resto como 'bajo'."""
    r = str(riesgo).strip().lower()
    return "alto" if r in ("1", "riesgo", "alto") else "bajo"


def _solo_interp(variables: dict) -> dict:
    """Devuelve las variables interpoladas tal cual (TP ya es real)."""
    return dict(variables)


# ── Escritura en Firestore ────────────────────────────────────────────────────

def _borrar_recolecciones(db, uid: str):
    """Elimina todas las recolecciones existentes del usuario."""
    col_ref = db.collection("usuarios").document(uid).collection("recolecciones")
    docs = col_ref.stream()
    borrados = 0
    for doc in docs:
        doc.reference.delete()
        borrados += 1
    return borrados


def _guardar_recoleccion_historica(db, uid, variables, prediccion, extras,
                                   riot_id, fecha_dt: datetime) -> str:
    doc = {
        "fecha":      fecha_dt,
        "demo":       False,
        "variables":  variables,
        "prediccion": prediccion,
        "extras":     extras,
        "riotId":     riot_id,
    }
    ref = (db.collection("usuarios")
             .document(uid)
             .collection("recolecciones")
             .document())
    ref.set(doc)
    db.collection("usuarios").document(uid).set(
        {"ultimaActividad": fecha_dt}, merge=True
    )
    return ref.id


# ── Fase de perfil Riot ───────────────────────────────────────────────────────

REGION   = "americas"
PLATFORM = "la2"

def _riot_request(url: str, reintentos: int = 5):
    """GET a Riot API con reintentos ante rate limit (429) y backoff."""
    import requests as req_lib
    headers = {"X-Riot-Token": RIOT_API_KEY}
    espera  = 30
    for intento in range(reintentos):
        try:
            r = req_lib.get(url, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                retry_after = int(r.headers.get("Retry-After", espera))
                print(f"      [rate limit] esperando {retry_after}s…", flush=True)
                time.sleep(retry_after + 1)
                espera = min(espera * 2, 120)
                continue
            if r.status_code == 404:
                return None   # cuenta no encontrada, no reintentar
            print(f"      [warn] HTTP {r.status_code} en {url}")
            time.sleep(5)
        except Exception as e:
            print(f"      [warn] red: {e}")
            time.sleep(10)
    return None


def _fetch_perfil_riot(name: str, tag: str):
    """Consulta Riot API para obtener icono y nivel del invocador."""
    if not RIOT_API_KEY:
        return None

    # 1. PUUID via account-v1
    cuenta = _riot_request(
        f"https://{REGION}.api.riotgames.com"
        f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}"
    )
    if not cuenta or "puuid" not in cuenta:
        print(f"      [warn] cuenta no encontrada: {name}#{tag}")
        return None
    puuid = cuenta["puuid"]

    # 2. Icono y nivel via summoner-v4
    summ = _riot_request(
        f"https://{PLATFORM}.api.riotgames.com"
        f"/lol/summoner/v4/summoners/by-puuid/{puuid}"
    )
    if not summ:
        print(f"      [warn] summoner no encontrado en {PLATFORM}: {name}#{tag}")
        return None

    icon_id = summ.get("profileIconId", 0)
    # Usa la misma función que el collector para generar la URL con la
    # versión real de DDragon (no hardcodeada).
    from app.services.collector_service import _icon_url
    return {
        "profileIconId": icon_id,
        "summonerLevel": summ.get("summonerLevel", 0),
        "iconUrl": _icon_url(icon_id),
    }


# ── Carga CSV ─────────────────────────────────────────────────────────────────

def cargar_csv(path: Path) -> dict:
    datos = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = row["Usuario"].strip().lower()
            datos[key] = row
    return datos


def construir_mapa_email(usuarios_list) -> dict:
    mapa = {}
    for email, riot_id in usuarios_list:
        nombre = riot_id.split("#")[0].strip().lower()
        mapa[nombre] = email
    return mapa


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--sin-perfil", action="store_true",
                        help="No consultar Riot API para el perfil.")
    parser.add_argument("--solo", nargs="*")
    args = parser.parse_args()

    if not KEY_PATH.exists():
        print(f"[ERROR] No se encontró firebase-key.json en {KEY_PATH}")
        sys.exit(1)

    from scripts.crear_usuarios import USUARIOS
    from app.services.model_service import predecir
    from app.services import firestore_service

    cred = credentials.Certificate(str(KEY_PATH))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    csv_datos  = cargar_csv(CSV_PATH)
    email_mapa = construir_mapa_email(USUARIOS)
    filtro     = [n.lower() for n in args.solo] if args.solo else None

    ok = omitidos = errores = 0

    print(f"\n{'='*65}")
    print(f"  seed_prepost.py — {len(csv_datos)} usuarios en CSV")
    print(f"  Período: {FECHA_PRE} → {FECHA_POST} (2 semanas)")
    if args.dry_run:
        print("  [DRY-RUN] No se escribirá nada en Firestore.")
    if RIOT_API_KEY and not args.sin_perfil:
        print("  RIOT_API_KEY detectada → se actualizará el perfil al final.")
    print(f"{'='*65}\n")

    # ── Fase 1: siembra de recolecciones ──────────────────────────────────────
    for nombre_csv, fila in csv_datos.items():
        riot_name = fila["Usuario"].strip()
        riot_tag  = fila["Tag"].strip()
        riot_id   = f"{riot_name}#{riot_tag}"

        if filtro and nombre_csv not in filtro:
            continue

        email = email_mapa.get(nombre_csv)
        if not email:
            print(f"  [SKIP] {riot_id} — no encontrado en USUARIOS")
            omitidos += 1
            continue

        try:
            uid = auth.get_user_by_email(email).uid
        except Exception as e:
            print(f"  [ERROR] {riot_id} — Auth: {e}")
            errores += 1
            continue

        if not args.dry_run:
            n = _borrar_recolecciones(db, uid)
            if n:
                print(f"  {riot_id} — {n} recolección(es) anterior(es) eliminada(s)")

        try:
            vars_pre_raw = {
                "THT":  float(fila["THT_pre"]),
                "ND":   int(fila["ND_pre"]),
                "TP":   int(fila["TP_pre"]),         # partidas reales (ventana 14 días)
                "HPD":  float(fila["HPD_pre"]),
                "NPPD": float(fila["NPPD_pre"]),     # complementaria, real del CSV
                "DCJ":  int(fila["DCJ_pre"]),
            }
            vars_post_raw = {
                "THT":  float(fila["THT_post"]),
                "ND":   int(fila["ND_post"]),
                "TP":   int(fila["TPP_post"]),       # partidas reales (ventana 14 días)
                "HPD":  float(fila["HPD_post"]),
                "NPPD": float(fila["NPPD_post"]),    # complementaria, real del CSV
                "DCJ":  int(fila["DCJ_post"]),
            }
        except (KeyError, ValueError) as e:
            print(f"  [ERROR] {riot_id} — CSV: {e}")
            errores += 1
            continue

        perfil_pre  = _perfil_desde_riesgo(fila.get("Riesgo_pre",  "0"))
        perfil_post = _perfil_desde_riesgo(fila.get("Riesgo_post", "0"))

        puntos = [(FECHA_PRE, vars_pre_raw, perfil_pre)]
        for ref_date, t in INTERMEDIOS:
            v_interp = _solo_interp(_interpolar(vars_pre_raw, vars_post_raw, t))
            puntos.append((ref_date, v_interp, perfil_pre if t < 0.5 else perfil_post))
        puntos.append((FECHA_POST, vars_post_raw, perfil_post))

        print(f"  {riot_id} ({email})")

        if args.dry_run:
            for ref_date, v, _ in puntos:
                print(f"    [{ref_date}] HPD={v['HPD']} DCJ={v['DCJ']} TP={v['TP']} NPPD={v['NPPD']}")
            ok += 1
            print()
            continue

        try:
            for idx, (ref_date, variables, perfil) in enumerate(puntos):
                seed      = hash(f"{riot_id}{ref_date}") & 0xFFFFFF
                fecha_dt  = _timestamp_aleatorio(ref_date, seed)
                prediccion = predecir(variables)
                extras     = _extras_para_fecha(
                    hpd=variables["HPD"], tht=variables["THT"],
                    nd=variables["ND"],   ref_date=ref_date,
                    perfil=perfil,        seed=seed,
                )
                rec_id = _guardar_recoleccion_historica(
                    db, uid, variables, prediccion, extras,
                    riot_id=riot_id, fecha_dt=fecha_dt,
                )
                hora_str = fecha_dt.strftime("%H:%M")
                print(f"    ✓ [{ref_date} {hora_str}] HPD={variables['HPD']} "
                      f"DCJ={variables['DCJ']} → {prediccion.get('nivel_label','?')} "
                      f"(id: {rec_id[:8]}…)")

            firestore_service.vincular_riot_id(uid, riot_id)
            db.collection("usuarios").document(uid).set({
                "riotId":            riot_id,
                "riotIdVinculado":   riot_id,
                "displayName":       riot_name,
                "summonerName":      riot_name,
                "tag":               riot_tag,
            }, merge=True)

            ok += 1
            print()
        except Exception as e:
            print(f"    ✗ Error: {e}\n")
            errores += 1

    # ── Fase 2: perfil Riot (icono, nivel) ────────────────────────────────────
    if RIOT_API_KEY and not args.sin_perfil and not args.dry_run:
        print(f"\n{'─'*65}")
        print("  Fase 2 — Actualizando perfiles desde Riot API…")
        print(f"{'─'*65}\n")

    if RIOT_API_KEY and not args.sin_perfil and not args.dry_run:
        ok2 = errores2 = 0

        for nombre_csv, fila in csv_datos.items():
            riot_name = fila["Usuario"].strip()
            riot_tag  = fila["Tag"].strip()
            riot_id   = f"{riot_name}#{riot_tag}"

            if filtro and nombre_csv not in filtro:
                continue

            email = email_mapa.get(nombre_csv)
            if not email:
                continue

            try:
                uid = auth.get_user_by_email(email).uid
            except Exception:
                errores2 += 1
                continue

            print(f"  {riot_id} … ", end="", flush=True)
            perfil = _fetch_perfil_riot(riot_name, riot_tag)
            nivel  = perfil.get("summonerLevel", 0) if perfil else 0
            icono  = perfil.get("profileIconId",  0) if perfil else 0
            if perfil and nivel > 0 and icono > 0:
                db.collection("usuarios").document(uid).set({
                    "profileIconId": icono,
                    "summonerLevel": nivel,
                    "iconUrl":       perfil.get("iconUrl"),
                }, merge=True)
                print(
                    f"✓  nivel={nivel}  "
                    f"icono={icono}  "
                    f"url={perfil.get('iconUrl','')[:60]}…"
                )
                ok2 += 1
            else:
                print("✗  sin datos (perfil inválido o API key expirada)")
                errores2 += 1

            time.sleep(2)

        print(f"\n  Perfiles: {ok2} OK · {errores2} errores")

    print(f"\n{'='*65}")
    print(f"  Resultado: {ok} OK · {omitidos} omitidos · {errores} errores")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
