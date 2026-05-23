"""Servicio de metas automáticas del sistema.

El sistema genera metas progresivas basadas en las variables actuales
del usuario. No hay metas configurables por el usuario — el sistema
decide qué mejorar y a qué ritmo, actualizando la meta cuando se cumple.

Progresión:
  Nivel 1 → HPD −15%, DCJ ≤ 5 días  (aprox. score objetivo 75-80)
  Nivel 2 → HPD −30%, DCJ ≤ 4 días  (aprox. score objetivo 60-65)
  Nivel 3 → HPD −45%, DCJ ≤ 3 días  (aprox. score objetivo 45-50)
  Nivel 4 → mantenerse en zona BAJO (score < 40) durante 3 análisis

Cumplimiento: las últimas N recolecciones deben cumplir los objetivos
de forma consecutiva (si hay una recaída, el contador vuelve a 0).
"""
from datetime import datetime, timezone


# ─── Helpers ──────────────────────────────────────────────────────────
def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ─── API pública ───────────────────────────────────────────────────────
def calcular_meta(recolecciones, meta_actual=None):
    """Evalúa el estado de la meta activa y genera la siguiente si se cumplió.

    Args:
        recolecciones: lista de recolecciones (más recientes primero).
        meta_actual:   dict con la meta guardada en Firestore, o None.

    Returns:
        dict con la meta actualizada (puede ser la misma u una nueva).
        None si no hay recolecciones.
    """
    if not recolecciones:
        return None

    ultima = recolecciones[0]
    vars_  = ultima.get("variables") or {}
    pred   = ultima.get("prediccion") or {}

    hpd_actual   = _f(vars_.get("HPD"))
    dcj_actual   = _f(vars_.get("DCJ"))
    score_actual = _f(pred.get("score"))

    # ── Sin meta activa: crear la primera ────────────────────────────
    if not meta_actual:
        return _crear_meta(1, hpd_actual, dcj_actual, score_actual)

    # ── Meta ya cumplida: crear la siguiente ──────────────────────────
    if meta_actual.get("cumplida"):
        nivel_sig = meta_actual.get("nivel", 1) + 1
        return _crear_meta(nivel_sig, hpd_actual, dcj_actual, score_actual)

    # ── Meta obsoleta: si el HPD actual ya supera ampliamente el objetivo
    #    (p.ej. la meta fue generada cuando el usuario jugaba mucho más),
    #    regenerar para que sea desafiante desde el nivel actual.
    meta_hpd_obj = _f(meta_actual.get("hpd_objetivo", 99))
    nivel_actual = meta_actual.get("nivel", 1)
    if hpd_actual < meta_hpd_obj * 0.95 and nivel_actual < 4:
        # El usuario ya está por debajo del 95% del objetivo → meta cumplida,
        # generar la siguiente desde el HPD actual.
        meta_actual = dict(meta_actual)
        meta_actual["cumplida"] = True
        meta_actual["fecha_cumplida"] = datetime.now(timezone.utc).isoformat()
        meta_actual["recolecciones_cumplidas"] = meta_actual.get("recolecciones_requeridas", 3)
        # Retornamos la meta marcada como cumplida; el route la archivará.
        return meta_actual

    # ── Meta activa: verificar progreso ───────────────────────────────
    return _verificar_cumplimiento(dict(meta_actual), recolecciones)


def progreso_meta(meta):
    """Devuelve el progreso de la meta como porcentaje 0-100."""
    if not meta:
        return 0
    req = meta.get("recolecciones_requeridas", 3)
    cum = meta.get("recolecciones_cumplidas", 0)
    return round((cum / req) * 100) if req > 0 else 0


# ─── Creación ─────────────────────────────────────────────────────────
def _crear_meta(nivel, hpd_actual, dcj_actual, score_actual):
    """Construye un dict de meta para el nivel dado."""
    now = datetime.now(timezone.utc).isoformat()

    if nivel >= 4:
        return {
            "nivel":                    4,
            "hpd_objetivo":             round(hpd_actual * 0.50, 1),
            "dcj_objetivo":             2,
            "descripcion":              (
                "¡Objetivo final! Mantén tu riesgo en zona Bajo "
                "(score < 40) durante 3 análisis consecutivos."
            ),
            "etiqueta":                 "Objetivo final",
            "creada":                   now,
            "cumplida":                 False,
            "recolecciones_cumplidas":  0,
            "recolecciones_requeridas": 3,
        }

    # Nivel 1: −25% (más exigente que "mejora moderada" del motor, que es −20%)
    # Nivel 2: −40%, Nivel 3: −55%
    reducciones = {1: 0.75, 2: 0.60, 3: 0.45}
    dcj_limites = {1: 5,    2: 4,    3: 3}
    etiquetas   = {1: "Meta inicial", 2: "Meta intermedia", 3: "Meta avanzada"}

    hpd_obj = max(round(hpd_actual * reducciones[nivel], 1), 0.5)
    dcj_obj = dcj_limites[nivel]

    descripciones = {
        1: (f"Reduce tus horas de juego a {hpd_obj} h/día y no superes "
            f"{dcj_obj} días seguidos sin descanso. "
            f"Mantén esto durante 3 análisis consecutivos."),
        2: (f"Baja tus sesiones a {hpd_obj} h/día con descansos cada "
            f"{dcj_obj} días. Un paso más hacia zona Media."),
        3: (f"Llega a {hpd_obj} h/día y toma un descanso cada "
            f"{dcj_obj} días. Esto debería sacarte de zona Alta."),
    }

    return {
        "nivel":                    nivel,
        "hpd_objetivo":             hpd_obj,
        "dcj_objetivo":             dcj_obj,
        "descripcion":              descripciones[nivel],
        "etiqueta":                 etiquetas[nivel],
        "creada":                   now,
        "cumplida":                 False,
        "recolecciones_cumplidas":  0,
        "recolecciones_requeridas": 3,
    }


# ─── Verificación de cumplimiento ─────────────────────────────────────
def _verificar_cumplimiento(meta, recolecciones):
    """Actualiza recolecciones_cumplidas y marca cumplida si corresponde."""
    req     = meta.get("recolecciones_requeridas", 3)
    nivel   = meta.get("nivel", 1)
    hpd_obj = _f(meta.get("hpd_objetivo", 99))
    dcj_obj = _f(meta.get("dcj_objetivo", 99))

    # Contar racha consecutiva desde la recolección más reciente
    racha = 0
    for rec in recolecciones:
        vars_ = rec.get("variables") or {}
        pred  = rec.get("prediccion") or {}
        hpd   = _f(vars_.get("HPD"))
        dcj   = _f(vars_.get("DCJ"))
        score = _f(pred.get("score"))

        if nivel >= 4:
            cumple = score < 40
        else:
            cumple = (hpd <= hpd_obj and dcj <= dcj_obj)

        if cumple:
            racha += 1
        else:
            break  # racha rota, no seguimos contando

    meta["recolecciones_cumplidas"] = min(racha, req)

    if racha >= req:
        meta["cumplida"]      = True
        meta["fecha_cumplida"] = datetime.now(timezone.utc).isoformat()

    return meta
