"""Intercambia los correos entre dos usuarios en Firebase Auth + Firestore.

Caso específico:
  Aiso#P2W     escuderosantillan@gmail.com  →  itzel.rr2003@gmail.com
  jeshuco#777  itzel.rr2003@gmail.com       →  escuderosantillan@gmail.com

La estrategia usa un correo temporal para evitar el error de unicidad de
Firebase Auth al hacer el swap directo:

  Paso 1: Aiso        → temp_swap_aiso@swap.invalid
  Paso 2: jeshuco     → escuderosantillan@gmail.com
  Paso 3: Aiso        → itzel.rr2003@gmail.com
  Paso 4: Firestore   actualiza el campo 'email' en ambos documentos

Uso:
    cd D:\\Backend
    python scripts/swap_emails.py

    # Solo auditar sin escribir nada:
    python scripts/swap_emails.py --dry-run
"""
import sys
import argparse
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import firebase_admin
from firebase_admin import credentials, auth, firestore

KEY_PATH = BASE / "firebase-key.json"

# ── Parámetros del swap ───────────────────────────────────────────────────────
EMAIL_A    = "escuderosantillan@gmail.com"   # actualmente Aiso#P2W
EMAIL_B    = "itzel.rr2003@gmail.com"        # actualmente jeshuco#777
EMAIL_TEMP = "temp_swap_aiso@swap.invalid"   # puente temporal (no real)

# Después del swap:  Aiso → EMAIL_B,  jeshuco → EMAIL_A


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra qué haría, sin escribir nada.")
    args = parser.parse_args()

    if not KEY_PATH.exists():
        print(f"[ERROR] No se encontró firebase-key.json en {KEY_PATH}")
        sys.exit(1)

    cred = credentials.Certificate(str(KEY_PATH))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # ── Obtener UIDs ──────────────────────────────────────────────────────────
    try:
        user_a = auth.get_user_by_email(EMAIL_A)
    except auth.UserNotFoundError:
        print(f"[ERROR] No existe en Auth: {EMAIL_A}")
        sys.exit(1)

    try:
        user_b = auth.get_user_by_email(EMAIL_B)
    except auth.UserNotFoundError:
        print(f"[ERROR] No existe en Auth: {EMAIL_B}")
        sys.exit(1)

    uid_a = user_a.uid
    uid_b = user_b.uid

    print(f"\n{'='*60}")
    print(f"  Swap de correos")
    print(f"  A  uid={uid_a}  {EMAIL_A}  →  {EMAIL_B}")
    print(f"  B  uid={uid_b}  {EMAIL_B}  →  {EMAIL_A}")
    if args.dry_run:
        print("  [DRY-RUN] No se escribirá nada.")
    print(f"{'='*60}\n")

    if args.dry_run:
        print("  Paso 1: A  →  temp_swap_aiso@swap.invalid")
        print(f"  Paso 2: B  →  {EMAIL_A}")
        print(f"  Paso 3: A  →  {EMAIL_B}")
        print("  Paso 4: Firestore actualiza campo 'email' en ambos docs")
        print("\n  (DRY-RUN: ningún cambio aplicado)\n")
        return

    # ── Paso 1: A → temporal ──────────────────────────────────────────────────
    print(f"  Paso 1 · A → {EMAIL_TEMP} … ", end="", flush=True)
    auth.update_user(uid_a, email=EMAIL_TEMP)
    print("✓")

    # ── Paso 2: B → EMAIL_A ──────────────────────────────────────────────────
    print(f"  Paso 2 · B → {EMAIL_A} … ", end="", flush=True)
    auth.update_user(uid_b, email=EMAIL_A)
    print("✓")

    # ── Paso 3: A → EMAIL_B ──────────────────────────────────────────────────
    print(f"  Paso 3 · A → {EMAIL_B} … ", end="", flush=True)
    auth.update_user(uid_a, email=EMAIL_B)
    print("✓")

    # ── Paso 4: Firestore ─────────────────────────────────────────────────────
    print(f"  Paso 4 · Firestore uid_a → {EMAIL_B} … ", end="", flush=True)
    db.collection("usuarios").document(uid_a).set(
        {"email": EMAIL_B}, merge=True
    )
    print("✓")

    print(f"  Paso 4 · Firestore uid_b → {EMAIL_A} … ", end="", flush=True)
    db.collection("usuarios").document(uid_b).set(
        {"email": EMAIL_A}, merge=True
    )
    print("✓")

    print(f"\n{'='*60}")
    print("  Swap completado.")
    print(f"  Aiso#P2W   → {EMAIL_B}")
    print(f"  jeshuco#777 → {EMAIL_A}")
    print(f"{'='*60}\n")
    print("  IMPORTANTE: actualiza crear_usuarios.py manualmente:")
    print(f'    ("{EMAIL_B}", "Aiso#P2W")')
    print(f'    ("{EMAIL_A}", "jeshuco#777")')
    print()


if __name__ == "__main__":
    main()
