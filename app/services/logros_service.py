"""Servicio de logros — calcula los logros del usuario a partir de su historial."""


def _f(valor, defecto=0.0):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def calcular_logros(recolecciones, config, usuario, historial_metas=None):
    """Devuelve la lista de logros calculados para el usuario.

    Cada logro: id, nombre, desc, icono, desbloqueado (bool), fecha (ISO|None).
    Las recolecciones llegan más-recientes-primero (orden del API).
    """
    recs    = recolecciones or []
    cfg     = config or {}
    hist_m  = historial_metas or []
    total   = len(recs)

    # recs[0] = más reciente, recs[-1] = más antigua
    ultima = recs[0] if total >= 1 else None
    primera = recs[-1] if total >= 2 else None   # solo para comparaciones

    logros = []

    # ── 1. Primera recolección ─────────────────────────────────────────────
    logros.append(_mk(
        id="primera_recoleccion",
        nombre="Primera recolección",
        desc="Completaste tu primer análisis de hábitos de juego. El primer paso siempre es el más importante.",
        icono="Star",
        ok=total >= 1,
        fecha=_fecha(ultima) if total >= 1 else None,
    ))

    # ── 2. Constancia ──────────────────────────────────────────────────────
    logros.append(_mk(
        id="constancia",
        nombre="Constancia",
        desc="Realizaste 5 o más análisis. Llevas un seguimiento serio de tu bienestar.",
        icono="Award",
        ok=total >= 5,
        fecha=None,
    ))

    # ── 3. Semana limpia ───────────────────────────────────────────────────
    sem_limpia = False
    if ultima:
        por_dia = ((ultima.get("extras") or {}).get("porDiaSemana") or [])
        hpd_max = _f(cfg.get("hpdMax"), 4.0)
        if len(por_dia) == 7 and all(_f(h) <= hpd_max for h in por_dia):
            sem_limpia = True
    logros.append(_mk(
        id="semana_limpia",
        nombre="Semana limpia",
        desc="No superaste tu meta de HPD ningún día en la última semana registrada.",
        icono="ShieldCheck",
        ok=sem_limpia,
        fecha=_fecha(ultima) if sem_limpia else None,
    ))

    # ── 4. Noctámbulo en recuperación ─────────────────────────────────────
    noc_ok = False
    if primera and ultima:
        pjn_p = _f((primera.get("extras") or {}).get("pjnMin"))
        pjn_u = _f((ultima.get("extras") or {}).get("pjnMin"))
        if pjn_p > 0 and pjn_u <= pjn_p * 0.70:
            noc_ok = True
    logros.append(_mk(
        id="noctambulo_recuperacion",
        nombre="Noctámbulo en recuperación",
        desc="Redujiste tu juego nocturno (PJN) un 30% o más desde tu primera recolección.",
        icono="Moon",
        ok=noc_ok,
        fecha=_fecha(ultima) if noc_ok else None,
    ))

    # ── 5. Tendencia positiva ──────────────────────────────────────────────
    tend_ok = False
    if primera and ultima:
        score_p = _f((primera.get("prediccion") or {}).get("score"))
        score_u = _f((ultima.get("prediccion") or {}).get("score"))
        if score_u < score_p:
            tend_ok = True
    logros.append(_mk(
        id="tendencia_positiva",
        nombre="Tendencia positiva",
        desc="Tu score de riesgo bajó entre tu primera y tu última recolección.",
        icono="TrendingDown",
        ok=tend_ok,
        fecha=_fecha(ultima) if tend_ok else None,
    ))

    # ── 6. Primera meta del sistema cumplida ──────────────────────────────
    primera_meta_ok   = len(hist_m) >= 1
    primera_meta_fecha = hist_m[0].get("fecha_cumplida") if primera_meta_ok else None
    logros.append(_mk(
        id="primera_meta",
        nombre="Primera meta cumplida",
        desc="Cumpliste tu primera meta automática del sistema. El cambio empieza con un paso.",
        icono="CheckCircle",
        ok=primera_meta_ok,
        fecha=primera_meta_fecha,
    ))

    # ── 7. Tres metas consecutivas ────────────────────────────────────────
    tres_metas_ok = len(hist_m) >= 3
    logros.append(_mk(
        id="tres_metas",
        nombre="En racha",
        desc="Completaste 3 metas del sistema seguidas. Eso es disciplina real.",
        icono="Zap",
        ok=tres_metas_ok,
        fecha=hist_m[2].get("fecha_cumplida") if tres_metas_ok else None,
    ))

    # ── 8. Pasar de ALTO a MEDIO ──────────────────────────────────────────
    alto_a_medio = False
    alto_a_medio_fecha = None
    if primera and ultima:
        score_p = _f((primera.get("prediccion") or {}).get("score"))
        score_u = _f((ultima.get("prediccion") or {}).get("score"))
        if score_p >= 70 and score_u < 70:
            alto_a_medio = True
            alto_a_medio_fecha = _fecha(ultima)
    logros.append(_mk(
        id="alto_a_medio",
        nombre="Bajando el nivel",
        desc="Tu score pasó de zona Alta a zona Media. Un cambio visible y medible.",
        icono="TrendingDown",
        ok=alto_a_medio,
        fecha=alto_a_medio_fecha,
    ))

    # ── 9. Llegar a zona BAJO ─────────────────────────────────────────────
    zona_bajo = False
    zona_bajo_fecha = None
    if ultima:
        score_u = _f((ultima.get("prediccion") or {}).get("score"))
        if score_u < 40:
            zona_bajo = True
            zona_bajo_fecha = _fecha(ultima)
    logros.append(_mk(
        id="zona_bajo",
        nombre="Zona segura",
        desc="Tu riesgo llegó a zona Baja. Es el resultado de semanas de esfuerzo sostenido.",
        icono="ShieldCheck",
        ok=zona_bajo,
        fecha=zona_bajo_fecha,
    ))

    # ── 10. Meta final: objetivo cumplido ────────────────────────────────
    meta_final_ok = any(m.get("nivel", 0) >= 4 for m in hist_m)
    meta_final_fecha = next(
        (m.get("fecha_cumplida") for m in hist_m if m.get("nivel", 0) >= 4), None
    )
    logros.append(_mk(
        id="objetivo_final",
        nombre="Objetivo final",
        desc="Completaste todas las metas del sistema y mantuviste zona Baja. Excepcional.",
        icono="Trophy",
        ok=meta_final_ok,
        fecha=meta_final_fecha,
    ))

    # ── 7. Racha rota ──────────────────────────────────────────────────────
    racha_ok = False
    if ultima:
        dcj = _f((ultima.get("variables") or {}).get("DCJ"))
        racha_ok = dcj == 0
    logros.append(_mk(
        id="racha_rota",
        nombre="Racha rota",
        desc="Tu DCJ es 0 — tomaste un descanso real. Eso merece reconocimiento.",
        icono="Coffee",
        ok=racha_ok,
        fecha=_fecha(ultima) if racha_ok else None,
    ))

    return logros


def _mk(id, nombre, desc, icono, ok, fecha):
    return {
        "id": id,
        "nombre": nombre,
        "desc": desc,
        "icono": icono,
        "desbloqueado": ok,
        "fecha": fecha,
    }


def _fecha(rec):
    if not rec:
        return None
    val = rec.get("fecha")
    if val is None:
        return None
    return val.isoformat() if hasattr(val, "isoformat") else str(val)
