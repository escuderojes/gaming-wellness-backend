"""Siembra los tests ICOGS-A (pre y post) en Firestore para cada
participante, usando data_collector/dataset_final_tesis_limpio.csv.

Estructura por usuario (usuarios/{uid}/icogs):
  - 13 may 2026 -> test PRE  (pre_P1..pre_P12,  total ICOGS_A_pre)
  - 26 may 2026 -> test POST (post_P1..post_P12, total ICOGS_A_post)

El puntaje se RECALCULA desde las respuestas crudas (items invertidos
{2,3,4,5,6,8} recodificados como 6 - v) y se verifica contra el total
del CSV; si no coincide, la fila se reporta y se omite (coherencia).

Uso:
    cd D:\\Backend
    python scripts/seed_icogs.py
    python scripts/seed_icogs.py --dry-run
    python scripts/seed_icogs.py --solo Aiso Tyson
"""
import argparse
import csv
import random
import sys
from datetime import datetime, timezone, date, time, timedelta
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore, auth

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

KEY_PATH = BASE / "firebase-key.json"
CSV_PATH = BASE / "data_collector" / "dataset_final_tesis_limpio.csv"

FECHA_PRE = date(2026, 5, 13)
FECHA_POST = date(2026, 5, 26)

INVERTIDOS = {2, 3, 4, 5, 6, 8}
UMBRAL = 36


def calcular(respuestas):
    return sum((6 - v) if i in INVERTIDOS else v
               for i, v in enumerate(respuestas, start=1))


def fecha_realista(d):
    """Datetime UTC del dia d con hora de tarde-noche aleatoria."""
    hora = time(random.randint(15, 22), random.randint(0, 59), random.randint(0, 59))
    return datetime.combine(d, hora, tzinfo=timezone.utc)


def construir_mapa_email(usuarios_list):
    mapa = {}
    for email, riot_id in usuarios_list:
        mapa[riot_id.split("#")[0].strip().lower()] = email
    return mapa


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--solo", nargs="*")
    args = parser.parse_args()

    if not KEY_PATH.exists():
        print(f"[ERROR] No se encontró firebase-key.json en {KEY_PATH}")
        sys.exit(1)
    if not CSV_PATH.exists():
        print(f"[ERROR] No se encontró el dataset en {CSV_PATH}")
        sys.exit(1)

    from scripts.crear_usuarios import USUARIOS

    cred = credentials.Certificate(str(KEY_PATH))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    email_mapa = construir_mapa_email(USUARIOS)
    filtro = [n.lower() for n in args.solo] if args.solo else None

    ok = omitidos = errores = 0

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))

    print(f"\n{'=' * 60}")
    print(f"  seed_icogs.py — {len(filas)} usuarios en CSV")
    print(f"  PRE: {FECHA_PRE}  ·  POST: {FECHA_POST}  ·  umbral: {UMBRAL}")
    if args.dry_run:
        print("  [DRY-RUN] No se escribirá nada en Firestore.")
    print(f"{'=' * 60}\n")

    for fila in filas:
        nombre = fila["Usuario"].strip()
        clave = nombre.lower()
        if filtro and clave not in filtro:
            continue

        email = email_mapa.get(clave)
        if not email:
            print(f"  [SKIP] {nombre} — no encontrado en USUARIOS")
            omitidos += 1
            continue
        try:
            uid = auth.get_user_by_email(email).uid
        except Exception as e:
            print(f"  [ERROR] {nombre} — Auth: {e}")
            errores += 1
            continue

        try:
            resp_pre = [int(fila[f"pre_P{i}"]) for i in range(1, 13)]
            resp_post = [int(fila[f"post_P{i}"]) for i in range(1, 13)]
            total_pre_csv = int(fila["ICOGS_A_pre"])
            total_post_csv = int(fila["ICOGS_A_post"])
        except (KeyError, ValueError) as e:
            print(f"  [ERROR] {nombre} — fila inválida: {e}")
            errores += 1
            continue

        # Verificación de coherencia respuestas <-> total del CSV.
        calc_pre, calc_post = calcular(resp_pre), calcular(resp_post)
        if calc_pre != total_pre_csv or calc_post != total_post_csv:
            print(f"  [SKIP] {nombre} — total no coincide "
                  f"(pre {calc_pre}≠{total_pre_csv} o post {calc_post}≠{total_post_csv})")
            omitidos += 1
            continue

        if not args.dry_run:
            # borra tests anteriores para no duplicar al re-ejecutar.
            col = db.collection("usuarios").document(uid).collection("icogs")
            for snap in col.stream():
                snap.reference.delete()

            for respuestas, total, dia, origen in (
                (resp_pre, calc_pre, FECHA_PRE, "seed_pre"),
                (resp_post, calc_post, FECHA_POST, "seed_post"),
            ):
                col.document().set({
                    "fecha": fecha_realista(dia),
                    "respuestas": respuestas,
                    "puntaje": total,
                    "nivel": "Alto" if total >= UMBRAL else "Bajo",
                    "umbral": UMBRAL,
                    "origen": origen,
                })

        marca = "→" if not args.dry_run else "(dry)"
        print(f"  {marca} {nombre}: pre {calc_pre} ({'Alto' if calc_pre >= UMBRAL else 'Bajo'})"
              f" · post {calc_post} ({'Alto' if calc_post >= UMBRAL else 'Bajo'})")
        ok += 1

    print(f"\n  Listo: {ok} sembrados · {omitidos} omitidos · {errores} errores\n")


if __name__ == "__main__":
    main()
