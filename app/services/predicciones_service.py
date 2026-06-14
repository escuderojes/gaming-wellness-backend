"""Motor de predicciones determinístico.

Convierte las variables actuales de un usuario + su historial en
proyecciones de riesgo para 3 horizontes (7 / 14 / 30 días) bajo
3 escenarios: actual (sin cambios), mejora (HPD −20 %) y saludable
(HPD = meta del usuario).

No requiere un segundo modelo ML — usa tendencia lineal + ajuste
paramétrico basado en literatura de gaming disorder (Lemmens et al.).
"""


# ─── Umbrales de nivel ────────────────────────────────────────────────
def _nivel(score):
    if score >= 75:
        return "Alto"
    if score >= 50:
        return "Medio"
    return "Bajo"


def _float_or_none(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _score_desde_modelo(variables):
    """Recalcula el score con el modelo cuando la prediccion guardada no lo trae."""
    v = variables or {}
    requeridas = ("ND", "HPD", "DCJ")
    if any(v.get(k) is None for k in requeridas):
        return None

    try:
        from app.services.model_service import predecir
    except Exception:
        try:
            import importlib.util
            from pathlib import Path

            path = Path(__file__).with_name("model_service.py")
            spec = importlib.util.spec_from_file_location("model_service", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            predecir = module.predecir
        except Exception:
            return None

    try:
        pred = predecir({k: v[k] for k in requeridas})
    except Exception:
        return None

    score = _float_or_none(pred.get("score"))
    if score is not None:
        return score

    probs = pred.get("probabilidades") or {}
    riesgo = _float_or_none(probs.get("Riesgo"))
    return round(riesgo * 100, 1) if riesgo is not None else None


def _score_prediccion(prediccion, variables=None):
    """Obtiene el score 0-100 sin confundir dato ausente con riesgo 0."""
    pred = prediccion or {}
    score = None
    if "score" in pred and pred.get("score") not in (None, ""):
        score = _float_or_none(pred.get("score"))

    probs = pred.get("probabilidades") or {}
    riesgo = _float_or_none(probs.get("Riesgo"))
    score_prob = round(riesgo * 100, 1) if riesgo is not None else None

    if score == 0 and score_prob and score_prob > 0:
        return score_prob
    if score is not None:
        return score
    if score_prob is not None:
        return score_prob

    return _score_desde_modelo(variables)


# ─── Templates de mensajes ────────────────────────────────────────────
# Clave: (nivel_proyectado, tipo_tendencia)
# Valor: dict {indicador_critico → mensaje}
_MSGS = {
    ("Bajo", "mejorando"): {
        "general":  "Vas por buen camino. Si mantienes este ritmo, tu riesgo seguirá bajando.",
        "hpd":      "Reducir tus sesiones está teniendo efecto. El cuerpo y la mente te lo agradecen.",
        "dcj":      "Tomar pausas entre días de juego es exactamente lo que necesitas seguir haciendo.",
        "pjn":      "Dormir mejor tiene un impacto directo en tu bienestar. Sigue cuidando el horario.",
    },
    ("Bajo", "estable"): {
        "general":  "Tu situación es saludable. Mantener este equilibrio es todo lo que necesitas.",
        "hpd":      "Tus horas de juego están bajo control. Así se ve un buen hábito.",
        "dcj":      "Incluir días sin jugar en tu semana es clave para sostener este nivel.",
        "pjn":      "Tu riesgo general sigue bajo, pero el juego nocturno está alto. Cuidar el horario evitará que suba.",
    },
    ("Bajo", "empeorando"): {
        "general":  "Todavía estás en zona segura, pero tu tendencia está subiendo. Presta atención.",
        "hpd":      "Tus horas promedio van subiendo poco a poco. Mejor ajustar antes de que sea un problema.",
        "dcj":      "Llevas muchos días seguidos. Un día libre haría bastante diferencia ahora.",
        "pjn":      "El juego nocturno va en aumento. Vale la pena ponerle un límite de horario.",
    },
    ("Medio", "mejorando"): {
        "general":  "Vas mejorando. Mantén lo que estás haciendo y el riesgo seguirá bajando.",
        "hpd":      "Reducir aunque sea media hora diaria está moviendo la aguja. Sigue así.",
        "dcj":      "Intercalar días de descanso es la palanca más efectiva que tienes ahora.",
        "pjn":      "Acortar el juego nocturno tiene efecto directo sobre tu nivel de riesgo.",
    },
    ("Medio", "estable"): {
        "general":  "Estás en zona media. No empeoras, pero tampoco mejoras. Pequeños cambios marcan la diferencia.",
        "hpd":      "Una reducción de 30–60 minutos diarios podría sacarte de esta zona en pocas semanas.",
        "dcj":      "Un día sin jugar cada semana es el cambio más fácil con mayor impacto.",
        "pjn":      "Mover las sesiones nocturnas a una hora antes podría mejorar bastante tu situación.",
    },
    ("Medio", "empeorando"): {
        "general":  "Tu tendencia está subiendo. Si no cambias algo pronto, podrías entrar en zona de riesgo.",
        "hpd":      "Tus horas están escalando. Un límite diario concreto puede cortar esta tendencia.",
        "dcj":      "Llevas muchos días sin un descanso. Planifica un día libre esta semana.",
        "pjn":      "El juego de madrugada está erosionando tu descanso. Es el factor más fácil de corregir.",
    },
    ("Alto", "mejorando"): {
        "general":  "Bien que estés cambiando. Todavía estás en zona alta, pero la dirección es la correcta.",
        "hpd":      "Bajar las horas es el paso más importante. Cada día que lo mantienes suma.",
        "dcj":      "Empezar a incluir descansos entre sesiones es una señal muy positiva. Continúa.",
        "pjn":      "Proteger las horas de sueño es clave para recuperarse. Sigue alejándote del juego nocturno.",
    },
    ("Alto", "estable"): {
        "general":  "Tu riesgo es alto y no está bajando. Es momento de hacer cambios concretos.",
        "hpd":      "Mantener más de {hpd:.0f} horas diarias de forma sostenida es un patrón que conviene cortar.",
        "dcj":      "Llevar {dcj} días seguidos sin descanso está afectando tu recuperación cognitiva.",
        "pjn":      "El juego nocturno frecuente fragmenta tu sueño y retroalimenta el ciclo de uso excesivo.",
    },
    ("Alto", "empeorando"): {
        "general":  "Tu situación está empeorando. Este es el momento de tomar una decisión.",
        "hpd":      "Tu promedio diario sigue subiendo. Considera establecer un tope real y concreto.",
        "dcj":      "Sin pausas y con tendencia al alza, el agotamiento cognitivo es muy probable.",
        "pjn":      "Jugar de madrugada cada noche y con tendencia creciente es la combinación más dañina.",
    },
}


def _get_msg(nivel_proy, tendencia_tipo, indicador_critico, hpd=0.0, dcj=0, pjn=0.0):
    pool = _MSGS.get((nivel_proy, tendencia_tipo), {})
    msg = pool.get(indicador_critico) or pool.get("general", "")
    try:
        msg = msg.format(hpd=float(hpd), dcj=int(dcj), pjn=float(pjn))
    except (KeyError, ValueError, IndexError):
        pass
    return msg


# ─── Mensaje específico para el escenario "Alcanzando tu meta" ───────
def _msg_meta(nivel_proyectado, meta_hpd_objetivo, meta_etiqueta):
    """Mensaje personalizado para el escenario 'Alcanzando tu meta'.

    Diferencia el texto del de 'Con mejora moderada' incluso cuando ambos
    proyectan al mismo nivel de riesgo.
    """
    textos = {
        "Alto": (
            f"Llegar a {meta_hpd_objetivo:.1f} h/día ({meta_etiqueta}) "
            "ya es un avance real, aunque el riesgo seguirá siendo alto a corto plazo. "
            "Cada sesión más corta cuenta."
        ),
        "Medio": (
            f"Con {meta_hpd_objetivo:.1f} h/día ({meta_etiqueta}) "
            "podrías salir de zona alta en dos semanas. "
            "Es el cambio más directo que puedes hacer ahora mismo."
        ),
        "Bajo": (
            f"Alcanzando {meta_hpd_objetivo:.1f} h/día ({meta_etiqueta}) "
            "tu riesgo llegaría a zona segura. "
            "Este es el objetivo concreto que el sistema te propone."
        ),
    }
    return textos.get(nivel_proyectado, "Alcanza tu meta para ver este impacto.")


# ─── Función principal ────────────────────────────────────────────────
def generar_prediccion_futura(variables, extras, config, historial, prediccion_actual, meta_activa=None):
    """Genera proyecciones de riesgo para 7, 14 y 30 días bajo 3 escenarios.

    Args:
        variables:         dict {THT, ND, TP, HPD, NPPD, DCJ}
        extras:            dict {pjnMin, nochesActivas, porHora, porDiaSemana, ...}
        config:            dict {hpdMax, ttsMax, dcjMax, ...}
        historial:         list de recolecciones (más recientes primero),
                           cada una con {prediccion: {score}, variables: {HPD, DCJ}}
        prediccion_actual: dict {nivel, score, probabilidades}

    Returns:
        dict con claves: tendencia, horizontes, escenarios, indicador_critico, alertas
    """
    v   = variables or {}
    ext = extras    or {}
    cfg = config    or {}

    hpd_actual   = float(v.get("HPD")   or 0)
    dcj_actual   = float(v.get("DCJ")   or 0)
    pjn_actual   = float(ext.get("pjnMin") or 0)
    hpd_max      = float(cfg.get("hpdMax") or 5)
    dcj_max      = float(cfg.get("dcjMax") or 5)
    score_actual = _score_prediccion(prediccion_actual, v)
    if score_actual is None:
        return {
            "disponible": False,
            "motivo": "sin_score_modelo",
            "mensaje": (
                "No hay una prediccion valida para proyectar. "
                "Se necesita score, probabilidades o variables ND/HPD/DCJ."
            ),
            "tendencia": {
                "tipo": "sin_datos",
                "tasa": None,
                "detalle": "No hay score de modelo suficiente para calcular tendencia.",
                "historial_suficiente": False,
            },
            "horizontes": [],
            "escenarios": {},
            "indicador_critico": None,
            "alertas": [],
        }

    # ── Proyección basada solo en la recolección más reciente ──────────
    # No se usa el historial para calcular una tendencia: cada predicción
    # se basa únicamente en las variables (ND/HPD/DCJ) de la última
    # recolección, evitando comparar mediciones de origenes distintos
    # (p. ej. datos sembrados vs. una recolección real posterior).
    tasa = 0.0
    tendencia_tipo = "actual"
    tendencia_det = (
        "La proyección se basa únicamente en tu recolección más reciente."
    )

    tendencia = {
        "tipo":    tendencia_tipo,
        "tasa":    0.0,
        "detalle": tendencia_det,
        "historial_suficiente": True,
    }

    tendencia_mensajes = (
        tendencia_tipo if tendencia_tipo in ("mejorando", "estable", "empeorando")
        else "estable"
    )

    # ── Indicador crítico (determina qué mensaje mostrar) ─────────────
    if dcj_actual > dcj_max * 1.2:
        indicador_critico = "dcj"
    elif pjn_actual > 90:
        indicador_critico = "pjn"
    elif hpd_actual > hpd_max * 1.5:
        indicador_critico = "hpd"
    else:
        indicador_critico = "general"

    # ── Proyección de score ───────────────────────────────────────────
    # El cambio de habito ajusta el score proyectado de cada horizonte.
    def _proyectar(dias, hpd_nuevo, k):
        """Score proyectado en `dias` días dado un cambio de HPD con coeficiente k.

        El efecto del cambio de comportamiento escala con el tiempo (días/14 como
        referencia): a 7 días el impacto es parcial, a 30 días es mayor porque el
        cambio sostenido acumula beneficio (o daño).
        """
        time_factor = dias / 14.0
        score_base = score_actual + tasa * time_factor
        if hpd_actual > 0 and abs(hpd_nuevo - hpd_actual) > 0.01:
            delta_ratio = (hpd_nuevo - hpd_actual) / hpd_actual
            # si baja el HPD, el escenario debe mostrar una reduccion visible.
            score_base += delta_ratio * max(score_base, 1.0) * k * time_factor
        return max(0.0, min(100.0, round(score_base, 1)))

    hpd_mejora = round(hpd_actual * 0.8, 2)

    # Escenario saludable: usa la meta del sistema si es más exigente que
    # la mejora moderada (HPD menor). Si la meta es más laxa, usa hpd_mejora
    # para que "Alcanzando tu meta" sea siempre ≥ "Con mejora moderada".
    meta_sistema_hpd = float((meta_activa or {}).get("hpd_objetivo") or 0)
    meta_config_hpd = float(cfg.get("hpdMax") or 0)
    metas_hpd = [m for m in (meta_sistema_hpd, meta_config_hpd) if m > 0]
    meta_hpd = min(metas_hpd) if metas_hpd else 0
    meta_etiqueta = (
        "Meta configurada"
        if meta_config_hpd > 0 and (meta_sistema_hpd <= 0 or meta_config_hpd <= meta_sistema_hpd)
        else (meta_activa or {}).get("etiqueta", "Meta del sistema")
    )
    if meta_hpd > 0 and meta_hpd < hpd_actual:
        hpd_saludable = round(min(meta_hpd, hpd_mejora), 2)
    else:
        hpd_saludable = hpd_mejora

    # ── Horizontes (7 / 14 / 30 días) ────────────────────────────────
    horizontes = []
    for dias in (7, 14, 30):
        s_act = _proyectar(dias, hpd_actual,    k=1.0)
        s_mej = _proyectar(dias, hpd_mejora,    k=0.7)
        s_sal = _proyectar(dias, hpd_saludable, k=0.9)
        # Guardrail: el escenario saludable nunca puede ser peor que mejora.
        # Si k=0.9 produce un score mayor que k=0.7 (porque hpd_saludable
        # coincide con hpd_mejora o el time_factor amplifica la diferencia),
        # forzamos el mínimo para mantener la coherencia visual.
        s_sal = min(s_sal, s_mej)
        horizontes.append({
            "dias":            dias,
            "score_actual":    s_act,
            "nivel_actual":    _nivel(s_act),
            "score_mejora":    s_mej,
            "nivel_mejora":    _nivel(s_mej),
            "score_saludable": s_sal,
            "nivel_saludable": _nivel(s_sal),
        })

    # ── Escenarios a 14 días (referencia para mensajes) ───────────────
    h14 = next(h for h in horizontes if h["dias"] == 14)

    escenarios = {
        "actual": {
            "titulo":    "Tendencia actual",
            "subtitulo": "Si nada cambia",
            "hpd":       round(hpd_actual, 1),
            "score":     h14["score_actual"],
            "nivel":     h14["nivel_actual"],
            "mensaje":   _get_msg(
                h14["nivel_actual"], tendencia_mensajes, indicador_critico,
                hpd=hpd_actual, dcj=dcj_actual, pjn=pjn_actual,
            ),
        },
        "mejora": {
            "titulo":    "Con mejora moderada",
            "subtitulo": f"HPD −20 % → {hpd_mejora:.1f} h/día",
            "hpd":       hpd_mejora,
            "score":     h14["score_mejora"],
            "nivel":     h14["nivel_mejora"],
            # Mensaje según el nivel proyectado (objetivo), no el actual
            "mensaje":   _get_msg(
                h14["nivel_mejora"], "mejorando", indicador_critico,
                hpd=hpd_mejora, dcj=dcj_actual, pjn=pjn_actual,
            ),
        },
        "saludable": {
            "titulo":    "Alcanzando tu meta",
            "subtitulo": (
                f"HPD → {meta_hpd:.1f} h/día · {meta_etiqueta}"
                if meta_hpd > 0 and meta_hpd < hpd_actual
                else f"HPD → {hpd_saludable:.1f} h/día (meta)"
            ),
            # Mostrar siempre el HPD objetivo real de la meta (no el ajustado internamente)
            "hpd":       round(meta_hpd, 1) if meta_hpd > 0 and meta_hpd < hpd_actual else hpd_saludable,
            "score":     h14["score_saludable"],
            "nivel":     h14["nivel_saludable"],
            # Mensaje personalizado para "Alcanzando tu meta", distinto al
            # de "Con mejora moderada" aunque proyecten al mismo nivel.
            "mensaje":   (
                _msg_meta(
                    h14["nivel_saludable"],
                    round(meta_hpd, 1) if meta_hpd > 0 and meta_hpd < hpd_actual else round(hpd_saludable, 1),
                    meta_etiqueta,
                )
                if meta_activa
                else _get_msg(
                    h14["nivel_saludable"], "mejorando", indicador_critico,
                    hpd=hpd_saludable, dcj=dcj_actual, pjn=pjn_actual,
                )
            ),
        },
    }

    # ── Alertas DSM-5 y clínicas ──────────────────────────────────────
    alertas = []
    h30 = next(h for h in horizontes if h["dias"] == 30)

    if _nivel(score_actual) != "Alto" and h30["nivel_actual"] == "Alto":
        alertas.append(
            "A 30 días, tu trayectoria te llevaría a zona de riesgo alto si no cambias nada."
        )
    if dcj_actual >= 6 and tasa >= 0:
        alertas.append(
            "Llevas muchos días seguidos de juego — cerca del umbral de 7 días del criterio DSM-5."
        )
    if pjn_actual > 90:
        alertas.append(
            f"Tu juego nocturno promedio ({int(pjn_actual)} min/noche) supera los 90 min "
            "recomendados para preservar la calidad del sueño."
        )

    return {
        "disponible":         True,
        "score_base":         round(score_actual, 1),
        "tendencia":         tendencia,
        "horizontes":        horizontes,
        "escenarios":        escenarios,
        "indicador_critico": indicador_critico,
        "alertas":           alertas,
    }
