"""Capa de reglas — recomendaciones, alertas y cumplimiento.

Genera de forma DETERMINISTICA (sin usar el modelo de ML) la lista de
recomendaciones que ve el usuario en la vista "Recomendaciones", a
partir de:
  - las metricas de su ultima recoleccion (las 6 variables),
  - los extras de la semana ISO en curso (hpdSemana, dcjSemana, ttsSemana),
  - su configuracion (metas, ventana de sueno, sensibilidad),
  - la prediccion del modelo (nivel + score).

Las alertas usan SIEMPRE los valores de la semana ISO (lunes → hoy)
cuando están disponibles en extras, garantizando consistencia con lo
que muestran los gráficos del dashboard.

Son reglas explicitas y explicables: cada alerta tiene una causa
trazable. Esto es deseable para una tesis, frente a una "caja negra".
"""

# Factor por sensibilidad: alta => umbrales mas estrictos (mas alertas);
# baja => mas permisivo (menos alertas).
FACTOR_SENSIBILIDAD = {"alta": 0.85, "media": 1.0, "baja": 1.15}


def _f(valor, defecto=0.0):
    """Convierte a float de forma segura."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _semana_val(extras, key_semana, variables, key_hist):
    """Devuelve el valor semanal si existe en extras; si no, cae al histórico."""
    e = extras or {}
    v = variables or {}
    val = e.get(key_semana)
    return _f(val if val is not None else v.get(key_hist))


def generar_recomendaciones(variables, extras, config, prediccion):
    """Devuelve la lista de recomendaciones para un usuario.

    Cada recomendacion es un dict con: id, type (critical|high|info),
    tag, icon, title y desc.

    Usa los valores de la semana ISO (extras) para garantizar
    consistencia con los gráficos del dashboard.
    """
    e = extras or {}
    c = config or {}
    pred = prediccion or {}

    # HPD y DCJ: semana ISO si está disponible; si no, histórico.
    HPD = _semana_val(extras, "hpdSemana", variables, "HPD")
    DCJ = _semana_val(extras, "dcjSemana", variables, "DCJ")
    # TTS real acumulado esta semana; si no existe, proyectar desde HPD.
    TTS_real = _f(e.get("ttsSemana"))
    tts_estimado = TTS_real if TTS_real > 0 else round(HPD * 7, 1)

    hpd_max = _f(c.get("hpdMax"), 4.0)
    dcj_max = _f(c.get("dcjMax"), 5.0)
    tts_max = _f(c.get("ttsMax"), 21.0)
    factor = FACTOR_SENSIBILIDAD.get(c.get("sensibilidad", "media"), 1.0)

    hpd_lim = hpd_max * factor
    dcj_lim = dcj_max * factor
    tts_lim = tts_max * factor

    recos = []
    nivel = pred.get("nivel")
    score = pred.get("score")

    # 1) Resumen segun el nivel del modelo --------------------------------
    if nivel == "Alto":
        recos.append({
            "id": "nivel", "type": "critical", "tag": "Crítica",
            "icon": "AlertTriangle",
            "title": "Ojo — tu forma de jugar está generando señales de alerta",
            "desc": (f"El modelo ve un patrón de riesgo ALTO (score {score}/100). "
                     f"No es para alarmarse, pero sí para tomárselo en serio. "
                     f"Esta semana sería un buen momento para reducir un poco las "
                     f"sesiones y ver cómo te sientes."),
            "acciones": [],
        })
    elif nivel == "Medio":
        recos.append({
            "id": "nivel", "type": "high", "tag": "Alerta",
            "icon": "Gauge",
            "title": "Tu rutina está al límite — vale la pena ajustar algo",
            "desc": (f"El modelo detecta un riesgo MEDIO (score {score}/100). "
                     f"Estás en un punto donde un pequeño cambio de hábitos puede "
                     f"hacer la diferencia. Aún hay tiempo de reencauzar la semana."),
            "acciones": [],
        })
    else:  # Bajo o sin prediccion
        recos.append({
            "id": "nivel", "type": "info", "tag": "Estado",
            "icon": "Check",
            "title": "Todo bien por aquí — sigue así",
            "desc": (f"El modelo ve un riesgo BAJO (score {score}/100). "
                     f"Tu patrón de juego está dentro de un rango saludable. "
                     f"Mantener esos hábitos es todo lo que hace falta."),
            "acciones": [],
        })

    # 2) HPD frente a la meta diaria (usa HPD de la semana ISO) -----------
    if HPD > hpd_lim * 1.5:
        recos.append({
            "id": "hpd", "type": "critical", "tag": "Crítica",
            "icon": "Clock",
            "title": "Llevas varios días con sesiones bastante largas",
            "desc": (f"Esta semana promedias {HPD} h/día — más del doble de tu meta "
                     f"de {hpd_max} h/día. No es un juicio, es solo un dato. "
                     f"Reducir gradualmente las próximas sesiones ayuda a evitar la "
                     f"fatiga que no se nota en el momento pero se acumula."),
            "acciones": [],
        })
    elif HPD > hpd_lim:
        recos.append({
            "id": "hpd", "type": "high", "tag": "Alerta",
            "icon": "Clock",
            "title": "Superaste tu meta de horas por día esta semana",
            "desc": (f"Esta semana llevas {HPD} h/día cuando te propusiste no pasar "
                     f"de {hpd_max} h/día. No pasa nada — lo importante es notarlo. "
                     f"¿Qué tal si la próxima sesión la acortas un poco?"),
            "acciones": [],
        })

    # 3) DCJ — racha de dias consecutivos esta semana ---------------------
    if DCJ > dcj_lim:
        recos.append({
            "id": "dcj", "type": "high", "tag": "Alerta",
            "icon": "Activity",
            "title": f"Llevas {int(DCJ)} días seguidos jugando esta semana",
            "desc": (f"Tu límite de días consecutivos es {int(dcj_max)} y esta semana "
                     f"ya llevas {int(DCJ)}. Un día de descanso no es rendirse — es "
                     f"parte de jugar bien a largo plazo. Tu cuerpo y tu concentración "
                     f"te lo agradecerán."),
            "acciones": [],
        })

    # 4) TTS — horas acumuladas esta semana frente al tope semanal --------
    if tts_estimado > tts_lim and tts_lim > 0:
        exceso = round((tts_estimado / tts_lim - 1) * 100, 1)
        if TTS_real > 0:
            desc_tts = (f"Ya acumulaste {TTS_real} h esta semana — un {exceso}% "
                        f"por encima de tu tope de {tts_max} h. Distribuir mejor "
                        f"las sesiones hace que el juego sea más sostenible.")
        else:
            desc_tts = (f"Si mantienes tu ritmo de {HPD} h/día, cerrarías la semana "
                        f"con ~{tts_estimado} h — un {exceso}% más de tu tope de "
                        f"{tts_max} h. Distribuir mejor las sesiones lo soluciona.")
        recos.append({
            "id": "tts", "type": "high", "tag": "Alerta",
            "icon": "Calendar",
            "title": "Esta semana te estás pasando de tu límite semanal",
            "desc": desc_tts,
            "acciones": [],
        })

    # 5) Prevencion — tips que se muestran siempre ------------------------
    recos.append({
        "id": "pausa", "type": "info", "tag": "Prevención",
        "icon": "Coffee",
        "title": "Un descanso de 10 minutos vale más de lo que parece",
        "desc": ("Cada 2 horas de juego continuo, tu concentración baja y tu cuerpo "
                 "lo acusa aunque no lo notes. Una pausa corta — levantarte, mover los "
                 "ojos, tomar agua — reseta la mente y mejora el siguiente tramo."),
        "acciones": [],
    })
    recos.append({
        "id": "sueno", "type": "info", "tag": "Prevención",
        "icon": "Moon",
        "title": "El juego nocturno te cobra la factura al día siguiente",
        "desc": (f"Iniciar sesiones entre las "
                 f"{c.get('sleepStart', '23:00')} y las "
                 f"{c.get('sleepEnd', '07:00')} interrumpe el sueño, aunque no lo "
                 f"notes de inmediato. El cansancio acumulado es uno de los factores "
                 f"que más empuja hacia el uso excesivo."),
        "acciones": [],
    })

    return recos


def calcular_cumplimiento(variables, extras, config):
    """Porcentaje de indicadores clave dentro del rango saludable.

    Usa los valores de la semana ISO (extras.hpdSemana / dcjSemana / ttsSemana)
    como fuente principal, con fallback al histórico si no están disponibles.
    Devuelve también los valores concretos y umbrales para el frontend.
    """
    e = extras or {}
    c = config or {}

    HPD = _semana_val(extras, "hpdSemana", variables, "HPD")
    DCJ = _semana_val(extras, "dcjSemana", variables, "DCJ")
    TTS_real = _f(e.get("ttsSemana"))
    # TTS proyectado: horas reales si están disponibles; si no, HPD × 7.
    TTS_proy = TTS_real if TTS_real > 0 else round(HPD * 7, 1)

    hpd_max = _f(c.get("hpdMax"), 4.0)
    dcj_max = _f(c.get("dcjMax"), 5.0)
    tts_max = _f(c.get("ttsMax"), 21.0)

    hpd_ok  = HPD <= hpd_max
    dcj_ok  = DCJ <= dcj_max
    tts_ok  = TTS_proy <= tts_max

    checks = {"HPD": hpd_ok, "DCJ": dcj_ok, "TTS": tts_ok}
    dentro = sum(1 for ok in checks.values() if ok)
    total  = len(checks)

    return {
        "dentroDeRango": dentro,
        "total": total,
        "porcentaje": round(dentro / total * 100) if total else 0,
        "detalle": checks,
        # Valores concretos para que el frontend muestre contexto real.
        "valores": {
            "HPD": {
                "actual":  round(HPD, 2),
                "umbral":  round(hpd_max, 1),
                "ok":      hpd_ok,
                "unidad":  "h/día",
                "desc":    "Promedio de horas jugadas por día activo esta semana.",
                "desde":   e.get("desde"),
                "hasta":   e.get("hasta"),
            },
            "DCJ": {
                "actual":  int(DCJ),
                "umbral":  int(dcj_max),
                "ok":      dcj_ok,
                "unidad":  "días",
                "desc":    "Racha más larga de días consecutivos con actividad esta semana.",
            },
            "TTS": {
                "actual":    round(TTS_real, 1) if TTS_real > 0 else None,
                "proyectado": round(TTS_proy, 1),
                "umbral":    round(tts_max, 1),
                "ok":        tts_ok,
                "unidad":    "h/semana",
                "desc":      ("Horas totales acumuladas esta semana. "
                              "TTS = Tiempo Total de Sesión semanal."),
                "desde":     e.get("desde"),
                "hasta":     e.get("hasta"),
            },
        },
    }
