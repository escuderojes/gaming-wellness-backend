"""Dispara la primera recolección (modo demo) para usuarios que:
  1. Nunca han iniciado sesión en la app (lastSignInTime == creationTime o diferencia < 5 s).
  2. Nunca han realizado ninguna recolección (subcolección 'recolecciones' vacía).

Uso:
    cd D:\\Backend
    python scripts/primera_recoleccion_bulk.py

    # Solo auditar sin ejecutar:
    python scripts/primera_recoleccion_bulk.py --dry-run

    # Procesar solo N usuarios a la vez (útil para pruebas):
    python scripts/primera_recoleccion_bulk.py --limite 10
"""
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import firebase_admin
from firebase_admin import credentials, auth, firestore

# ── Lista de participantes (email → Riot ID) ──────────────────────────────────
from scripts.crear_usuarios import USUARIOS          # reutiliza la misma lista

KEY_PATH = BASE / "firebase-key.json"
PAUSA_ENTRE_USUARIOS = 5   # segundos entre usuarios para respetar rate limit de Riot


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nunca_inicio_sesion(record) -> bool:
    """True si el usuario nunca hizo login (lastSignInTime == creationTime o nulo)."""
    ct = record.user_metadata.creation_timestamp   # ms epoch
    lt = record.user_metadata.last_sign_in_timestamp  # ms epoch o None
    if lt is None:
        return True
    diff_seg = abs(lt - ct) / 1000
    return diff_seg < 5   # margen de 5 s por si Firebase los registra casi iguales


def _tiene_recolecciones(db, uid: str) -> bool:
    """True si el usuario ya tiene al menos una recolección en Firestore."""
    snap = (
        db.collection("usuarios")
        .document(uid)
        .collection("recolecciones")
        .limit(1)
        .get()
    )
    return len(snap) > 0


def _lanzar_real(uid: str, name: str, tag: str, db) -> bool:
    """Ejecuta la recolección REAL contra Riot API y la persiste en Firestore."""
    try:
        from app.services.collector_service import recolectar_usuario
        from app.services.model_service import predecir
        from app.services import firestore_service
        from app.services.metas_service import calcular_meta

        def _noop(pct, msg):
            print(f"      [{pct:3d}%] {msg}")

        recoleccion  = recolectar_usuario(name, tag, _noop, demo=False)
        variables    = recoleccion["variables"]
        perfil       = recoleccion.get("perfil") or {}
        extras       = recoleccion.get("extras") or {}
        prediccion   = predecir(variables)

        firestore_service.crear_o_actualizar_usuario(uid, {
            "riotId": f"{name}#{tag}",
            "profileIconId": perfil.get("profileIconId"),
            "summonerLevel": perfil.get("summonerLevel"),
            "iconUrl":       perfil.get("iconUrl"),
        })

        rec_id = firestore_service.guardar_recoleccion(
            uid, variables, prediccion,
            demo=True, extras=extras,
            riot_id=f"{name}#{tag}",
        )

        if rec_id:
            # Vincular Riot ID si aún no está vinculado.
            if not firestore_service.obtener_riot_id_vinculado(uid):
                firestore_service.vincular_riot_id(uid, f"{name}#{tag}")

            # Evaluar meta del sistema.
            try:
                recs = firestore_service.obtener_recolecciones(uid, limite=10)
                meta_actual = firestore_service.obtener_meta_activa(uid)
                meta_nueva  = calcular_meta(recs, meta_actual)
                if meta_nueva:
                    firestore_service.guardar_meta_activa(uid, meta_nueva)
            except Exception as e:
                print(f"      [warn] Meta no actualizada: {e}")

        return rec_id is not None

    except Exception as e:
        print(f"      [ERROR] {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Primera recolección bulk (demo).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo auditar, no ejecutar recolecciones.")
    parser.add_argument("--limite", type=int, default=0,
                        help="Procesar solo los primeros N elegibles (0 = todos).")
    args = parser.parse_args()

    if not KEY_PATH.exists():
        print(f"[ERROR] No se encontró firebase-key.json en {KEY_PATH}")
        sys.exit(1)

    cred = credentials.Certificate(str(KEY_PATH))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    total      = len(USUARIOS)
    elegibles  = []
    omitidos   = []
    errores_a  = []

    print(f"\n{'='*65}")
    print(f"  Auditando {total} participantes…")
    print(f"{'='*65}")

    # ── Fase 1: auditoría ──────────────────────────────────────────────
    for i, (email, riot_id) in enumerate(USUARIOS, 1):
        try:
            record = auth.get_user_by_email(email)
            uid    = record.uid

            sin_login       = _nunca_inicio_sesion(record)
            sin_recoleccion = not _tiene_recolecciones(db, uid)

            if sin_login and sin_recoleccion:
                elegibles.append((uid, email, riot_id))
                estado = "ELEGIBLE  "
            else:
                motivo = []
                if not sin_login:       motivo.append("ya inició sesión")
                if not sin_recoleccion: motivo.append("ya tiene recolección")
                omitidos.append((email, ", ".join(motivo)))
                estado = f"OMITIR    ({', '.join(motivo)})"

            print(f"  [{i:3d}/{total}] {estado} | {email}")

        except auth.UserNotFoundError:
            errores_a.append(email)
            print(f"  [{i:3d}/{total}] NO EXISTE  | {email}")
        except Exception as e:
            errores_a.append(email)
            print(f"  [{i:3d}/{total}] ERROR      | {email} → {e}")

    print(f"\n{'─'*65}")
    print(f"  Elegibles: {len(elegibles)} | Omitidos: {len(omitidos)} | Errores: {len(errores_a)}")
    print(f"{'─'*65}\n")

    if not elegibles:
        print("  Nada que hacer.")
        return

    if args.dry_run:
        print("  [dry-run] Se habrían procesado:")
        for uid, email, riot_id in elegibles:
            print(f"    • {email} → {riot_id}")
        return

    # ── Fase 2: recolección ────────────────────────────────────────────
    objetivo = elegibles if not args.limite else elegibles[:args.limite]
    ok = 0
    fail = 0

    seg_estimados = len(objetivo) * (15 + PAUSA_ENTRE_USUARIOS)
    min_estimados = seg_estimados // 60
    print(f"  Lanzando recolección REAL para {len(objetivo)} usuario(s)…")
    print(f"  Tiempo estimado: ~{min_estimados} min (puede variar por rate limit de Riot)\n")

    for idx, (uid, email, riot_id) in enumerate(objetivo, 1):
        name, tag = riot_id.rsplit("#", 1)
        print(f"  [{idx:3d}/{len(objetivo)}] {email} → {riot_id}")
        exito = _lanzar_real(uid, name, tag, db)
        if exito:
            ok += 1
            print(f"      ✓ Guardado\n")
        else:
            fail += 1
            print(f"      ✗ Falló (se continúa con el siguiente)\n")

        if idx < len(objetivo):
            time.sleep(PAUSA_ENTRE_USUARIOS)

    print(f"{'='*65}")
    print(f"  Resultado: {ok} OK · {fail} fallidos · {len(elegibles)-len(objetivo)} pendientes")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
